"""Dividendos del IBEX 35 a partir de los comunicados de la CNMV (sin BME).

Para cada comunicado de una empresa del IBEX 35 que el colector `cnmv` clasifica en la caja «dividendos»
(`<salida>/cnmv/datos/ibex35.csv`), abre su ficha en la CNMV, descarga el PDF del comunicado, lo pasa a texto y
busca el importe bruto por acción con su moneda, la fecha ex-dividendo, la fecha de registro y la fecha de pago.

- Fuente: CNMV (nota legal verificada el 02/11/2026: reproducción fiel; se permiten cálculos; gratuito en
  cnmv.es). Cada fila lleva el enlace al comunicado original.
- Solo se rellenan los campos que se leen con seguridad; un importe sin moneda explícita no se publica. Si falta
  algo, la fila queda «parcial» y la ficha remite al comunicado. Nada se inventa ni se completa a mano.
- Dividendos flexibles (scrip): no se lee importe; el efectivo depende de la opción del accionista.
- El PDF y su texto se guardan en `$ESPEC_CACHE_DIR/cnmv/` (por defecto `cache/cnmv/` del repositorio, fuera de
  lo que sirve el servidor y fuera de git) para no volver a pedirlos.
- Salida: `<salida>/cnmv/datos/dividendos.csv` (escritura atómica); la lee la ficha integrada (`empresas/`).
- Desde el 22/11/2026 lo llama `cnmv/comunicados.py` al final de cada pasada (hasta LIMITE comunicados nuevos por
  pasada). Prototipo del IFG del 17/11 (escribía en `borrador/`), puesto en producción por Datos.

Uso a mano: python cnmv/dividendos_cnmv.py [--todos] [--limite N]
Dependencias: requests, pandas y `pdftotext` (poppler-utils).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("ESPEC_DATOS_DIR", RAIZ / "docs")) / "cnmv" / "datos"
CACHE = Path(os.environ.get("ESPEC_CACHE_DIR", RAIZ / "cache")) / "cnmv"
CAB = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
PAUSA = 2.0
LIMITE = 20          # comunicados nuevos por pasada
MAX_INTENTOS = 3     # un comunicado sin documento legible se vuelve a pedir hasta tres veces
COLUMNAS = ["canal", "nreg", "fecha_comunicado", "isin", "empresa", "tipo", "importe_bruto", "moneda", "fecha_ex",
            "fecha_registro", "fecha_pago", "extraccion", "intentos", "enlace"]

MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
MESES.update({"setiembre": 9})
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x)
    return "".join(c for c in x if not unicodedata.combining(c)).lower()


# --------------------------------------------------------------------------- lectura de fechas e importes
# pdftotext devuelve muchos comunicados sin espacios («15dediciembrede2026», «Fechadepago»), así que todo
# se busca sobre el texto compacto: minúsculas, sin acentos y sin espacios.
_MES = "|".join(sorted(list(MESES) + list(MONTHS), key=len, reverse=True))
RE_FECHA = re.compile(r"(?<!\d)(\d{1,2})(?:de)?(" + _MES + r")(?:de|,)?(20\d\d)"
                      r"|(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](20\d\d)"
                      r"|(" + "|".join(MONTHS) + r")(\d{1,2}),?(20\d\d)")


def _fechas(texto: str) -> list[tuple[int, int, date]]:
    """Todas las fechas del texto compacto: (inicio, fin, fecha)."""
    out = []
    for m in RE_FECHA.finditer(texto):
        try:
            if m.group(1):
                d = date(int(m.group(3)), MESES.get(m.group(2)) or MONTHS[m.group(2)], int(m.group(1)))
            elif m.group(4):
                d = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            else:
                d = date(int(m.group(9)), MONTHS[m.group(7)], int(m.group(8)))
        except ValueError:
            continue
        out.append((m.start(), m.end(), d))
    return out


ETIQUETAS = {
    "fecha_ex": ["fechaex-dividendo", "fechaexdividendo", "ex-dividenddate", "exdividenddate", "ex-date", "exdate",
                 "sinderechoaldividendo", "sinderechoapercibireldividendo", "cotizaranex-dividendo",
                 "cotizaranexdividendo", "fechadecotizacionexdividendo", "cotizacionexdividendo", "exdividendo"],
    "fecha_registro": ["fechaderegistro", "recorddate"],
    "fecha_pago": ["fechadepago", "paymentdate", "sepagarael", "seabonarael", "seabonaraapartirdel", "fechadeabono"],
}
# Entre la etiqueta y la fecha solo puede haber signos y estas palabras de enlace (sin espacios). Así no se
# toma una fecha que solo está cerca («en la fecha ex-dividendo, y se prevé anunciarlo el 3 de noviembre»).
ENLACE_OK = re.compile(r"(?:\(?[a-z-]*date\)?)?(?:sera|es|seran)?(?:el|del|eldia|apartirdel|elproximo|on)?")


def _fecha_tras(t: str, fechas: list[tuple[int, int, date]], etiquetas: list[str]) -> date | None:
    for e in etiquetas:
        for m in re.finditer(re.escape(e), t):
            for ini, _, d in fechas:
                if m.end() <= ini <= m.end() + 40:
                    letras = re.sub(r"[^a-z-]", "", t[m.end():ini].replace("(", "").replace(")", ""))
                    if ENLACE_OK.fullmatch(letras.strip("-")):
                        return d
                    break   # la primera fecha tras la etiqueta no está pegada a ella: no vale
    return None


EUR = r"(?:euros?|eur|€)"
USD = r"(?:usd|us\$|dolares|dollars?|\$)"
# (patrón, divisor, moneda fija o None si se mira alrededor del número)
RE_IMPORTE = [
    (re.compile(r"importebruto(?:poraccion)?[^0-9]{0,30}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"(?:dividendo|importe|retribucion)?brutoporaccion[^0-9]{0,25}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"(\d+[.,]\d+)" + EUR + r"(?:brutos?|gross)"), 1, "EUR"),
    (re.compile(r"(\d+[.,]\d+)centimosdeeurobrutos"), 100, "EUR"),
    (re.compile(r"dividendo(?:bruto)?(?:acuenta|complementario|extraordinario|ordinario)?(?:de|porimportede)(\d+[.,]\d+)" + EUR), 1, "EUR"),
    (re.compile(r"gross(?:amount|dividend)[^0-9]{0,30}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"(?:dividend|dividendo)(?:of|de)" + USD + r"(\d+[.,]\d+)"), 1, "USD"),
    # «dividendo a cuenta de los resultados del ejercicio 2026 de 0,15 euros por cada una de las acciones» (Grifols),
    # «dividendo bruto en efectivo a cuenta, con cargo a…, de 0,053 euros por acción» (IAG)
    (re.compile(r"dividendo[a-z0-9,()]{0,100}?de(\d+[.,]\d+)" + EUR + r"(?:brutos?)?(?:poraccion|porcada)"), 1, "EUR"),
]


def _moneda_cerca(t: str, ini: int, fin: int) -> str | None:
    """Moneda escrita justo antes o justo después de la cifra (en el texto compacto), con a lo sumo dos o tres
    signos en medio: «0,25€», «0,25(euros)», «(euros):0,25», «usd0.125»."""
    despues, antes = t[fin:fin + 14], t[max(0, ini - 12):ini]
    if re.match(r"[^a-z0-9]{0,2}" + EUR, despues) or re.search(EUR + r"[^a-z0-9]{0,3}$", antes):
        return "EUR"
    if re.match(r"[^a-z0-9]{0,2}" + USD, despues) or re.search(USD + r"[^a-z0-9]{0,3}$", antes):
        return "USD"
    return None


def _importe(t: str) -> tuple[float | None, str | None]:
    """Importe por acción y su moneda. Sin moneda explícita no hay importe."""
    for r, div, moneda in RE_IMPORTE:
        m = r.search(t)
        if not m:
            continue
        v = round(float(m.group(1).replace(",", ".")) / div, 6)
        if not 0 < v < 50:          # por acción: nada razonable pasa de 50
            continue
        mon = moneda or _moneda_cerca(t, m.start(1), m.end(1))
        if mon:
            return v, mon
    return None, None


def extraer(texto_pdf: str, fecha_com: date, tipo: str = "Dividendo") -> dict:
    """Campos leídos del texto del comunicado. Valida coherencia; lo dudoso se deja vacío."""
    vacio = {"importe_bruto": None, "moneda": None, "fecha_ex": None, "fecha_registro": None, "fecha_pago": None}
    if tipo == "Dividendo flexible":
        return {**vacio, "extraccion": "flexible: ver comunicado"}
    if tipo != "Dividendo":   # política de dividendos y otros anuncios sin un pago concreto: no se lee importe
        return {**vacio, "extraccion": "sin pago: ver comunicado"}
    t = re.sub(r"\s+", "", _norm(texto_pdf))
    fechas = _fechas(t)
    r = dict(vacio)
    r["importe_bruto"], r["moneda"] = _importe(t)
    for campo, etq in ETIQUETAS.items():
        r[campo] = _fecha_tras(t, fechas, etq)
    # coherencia: fechas entre el comunicado y el 31/12 del año siguiente; ex <= registro <= pago
    for campo in ("fecha_ex", "fecha_registro", "fecha_pago"):
        d = r[campo]
        if d and not (fecha_com <= d <= date(fecha_com.year + 1, 12, 31)):
            r[campo] = None
    if r["fecha_ex"] and r["fecha_pago"] and r["fecha_ex"] > r["fecha_pago"]:
        r.update({"fecha_ex": None, "fecha_registro": None, "fecha_pago": None})
    reg = r["fecha_registro"]
    if reg and ((r["fecha_ex"] and reg < r["fecha_ex"]) or (r["fecha_pago"] and reg > r["fecha_pago"])):
        r["fecha_registro"] = None
    completos = all(r[k] for k in ("importe_bruto", "moneda", "fecha_ex", "fecha_pago"))
    r["extraccion"] = "completa" if completos else ("parcial" if any(r[k] for k in ("importe_bruto", "fecha_ex", "fecha_pago")) else "sin datos")
    return r


# --------------------------------------------------------------------------- descargas
def texto_comunicado(s: requests.Session, canal: str, nreg: int, enlace: str, cache: Path = CACHE) -> str | None:
    """Texto del PDF del comunicado (ficha pública de la CNMV → documento → pdftotext), con caché."""
    cache.mkdir(parents=True, exist_ok=True)
    txt = cache / f"{canal}-{nreg}.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    try:
        h = s.get(enlace, headers=CAB, timeout=120)  # sigue la redirección de la CNMV a la ficha del portal
        h.raise_for_status()
        m = re.search(r"(?:https?:)?//www\.cnmv\.es/webservices/verdocumento/ver\?t=[^\"'<> ]+", h.text)
        if not m:
            return None
        url = m.group(0).replace("&amp;", "&")
        url = "https:" + url if url.startswith("//") else url
        time.sleep(PAUSA)
        p = s.get(url, headers=CAB, timeout=120)
        p.raise_for_status()
        if "pdf" not in p.headers.get("content-type", ""):
            return None
        pdf = cache / f"{canal}-{nreg}.pdf"
        pdf.write_bytes(p.content)
        texto = subprocess.run(["pdftotext", "-raw", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
        txt.write_text(texto, encoding="utf-8")
        return texto
    except (requests.RequestException, subprocess.SubprocessError, OSError):
        return None
    finally:
        time.sleep(PAUSA)


def leer(ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    d = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    for c in COLUMNAS:
        if c not in d.columns:
            d[c] = ""
    return d[COLUMNAS]


def actualizar(datos: Path = DATOS, limite: int = LIMITE, todos: bool = False, texto_de=None) -> dict:
    """Lee los comunicados de dividendo nuevos (o sin documento legible, hasta MAX_INTENTOS) y reescribe
    datos/dividendos.csv. `texto_de(canal, nreg, enlace)` permite probar sin red."""
    clasif = datos / "ibex35.csv"
    if not clasif.exists():
        return {"leidos": 0, "pendientes": 0, "total": 0}
    com = pd.read_csv(clasif, dtype=str, keep_default_na=False)
    com = com[com["caja"] == "dividendos"].sort_values(["fecha", "canal", "nreg"], ascending=False)
    salida = datos / "dividendos.csv"
    previas = leer(salida)
    hechas = {(r.canal, r.nreg): r for r in previas.itertuples()}
    if texto_de is None:
        sesion = requests.Session()
        texto_de = lambda canal, nreg, enlace: texto_comunicado(sesion, canal, int(nreg), enlace)  # noqa: E731
    nuevas, pendientes = [], 0
    for _, c in com.iterrows():
        previa = hechas.get((c["canal"], c["nreg"]))
        intentos = int(previa.intentos or 0) if previa is not None else 0
        if previa is not None and not todos and (previa.extraccion != "sin documento" or intentos >= MAX_INTENTOS):
            continue
        if len(nuevas) >= limite:
            pendientes += 1
            continue
        fecha_com = date.fromisoformat(c["fecha"][:10])
        if c["etiqueta"] != "Dividendo":  # flexibles y política de dividendos: no se descarga nada
            r = extraer("", fecha_com, c["etiqueta"])
        else:
            texto = texto_de(c["canal"], c["nreg"], c["enlace"])
            # el título del registro de la CNMV va delante: a veces dice el importe con todas las letras
            # («0,053 euros brutos por acción») y el PDF no
            r = extraer(c["texto"] + "\n" + texto, fecha_com, c["etiqueta"]) if texto else {"extraccion": "sin documento"}
        nuevas.append({"canal": c["canal"], "nreg": c["nreg"], "fecha_comunicado": c["fecha"][:10], "isin": c["isin"],
                       "empresa": c["empresa"], "tipo": c["etiqueta"],
                       **{k: ("" if r.get(k) is None else str(r.get(k))) for k in ("importe_bruto", "moneda", "fecha_ex", "fecha_registro", "fecha_pago")},
                       "extraccion": r["extraccion"], "intentos": str(intentos + 1), "enlace": c["enlace"]})
    if nuevas:
        n = pd.DataFrame(nuevas, columns=COLUMNAS)
        clave = set(zip(n["canal"], n["nreg"]))
        resto = previas[[(a, b) not in clave for a, b in zip(previas["canal"], previas["nreg"])]]
        todo = pd.concat([resto, n], ignore_index=True).sort_values(["fecha_comunicado", "canal", "nreg"])
        datos.mkdir(parents=True, exist_ok=True)
        tmp = salida.with_suffix(".csv.tmp")
        todo.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
        tmp.replace(salida)
    else:
        todo = previas
    resumen = todo["extraccion"].value_counts().to_dict() if len(todo) else {}
    if nuevas or pendientes:
        print(f"Dividendos de la CNMV: {len(nuevas)} comunicados leídos, {pendientes} pendientes para la pasada siguiente; "
              f"en total {len(todo)}: {resumen}")
    return {"leidos": len(nuevas), "pendientes": pendientes, "total": len(todo), "resumen": resumen}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todos", action="store_true", help="vuelve a leer también los ya guardados")
    ap.add_argument("--limite", type=int, default=LIMITE)
    a = ap.parse_args()
    actualizar(limite=a.limite, todos=a.todos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
