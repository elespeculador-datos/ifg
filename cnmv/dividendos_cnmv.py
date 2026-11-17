"""Dividendos del IBEX 35 a partir de los comunicados de la CNMV (sustituye a los datos de BME).

Para cada comunicado de una empresa del IBEX 35 que el colector `cnmv` clasifica en la caja «dividendos»
(docs/cnmv/datos/ibex35.csv), abre su ficha en la CNMV, descarga el PDF del comunicado, lo pasa a texto y busca:
importe bruto por acción, fecha ex-dividendo, fecha de registro y fecha de pago.

- Fuente: CNMV (reproducción fiel, se permiten cálculos; ver Nota legal de la CNMV). Cada fila lleva
  el enlace al comunicado original.
- Solo se rellenan los campos que se leen con seguridad. Si falta alguno, la fila queda «parcial» y la
  web debe remitir al comunicado. Nada se inventa ni se completa a mano.
- El PDF y su texto se guardan en `cache/oir/` (no se publican) para no volver a pedirlos.
- Salida: `docs/cnmv/datos/dividendos_cnmv.csv` (escritura atómica). No borra filas ya extraídas.

Uso (como smpro, desde /home/smpro/apps/colectores):
    /home/smpro/venv/bin/python cnmv/dividendos_cnmv.py            # comunicados nuevos
    /home/smpro/venv/bin/python cnmv/dividendos_cnmv.py --todos    # vuelve a leer también los ya vistos
Dependencias: requests, pandas y `pdftotext` (poppler-utils).
"""
from __future__ import annotations

import argparse
import csv
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
# Comunicados del IBEX 35 ya identificados y clasificados por cnmv/comunicados.py (misma lógica que la web)
CLASIFICADOS = RAIZ / "docs" / "cnmv" / "datos" / "ibex35.csv"
CACHE = RAIZ / "cache" / "oir"
SALIDA = RAIZ / "borrador" / "dividendos_cnmv.csv"  # prototipo: fuera de lo publicado
CAB = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
FICHA = "https://www.cnmv.es/portal/Otra-Informacion-Relevante/Resultado-OIR?nreg={}"
PAUSA = 2.0
COLUMNAS = ["nreg", "fecha_comunicado", "isin", "empresa", "tipo", "importe_bruto_eur", "fecha_ex", "fecha_registro",
            "fecha_pago", "extraccion", "enlace"]

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


RE_IMPORTE = [
    (re.compile(r"importebruto(?:poraccion)?[^0-9]{0,30}?(\d+[.,]\d+)"), 1),
    (re.compile(r"(?:dividendo|importe|retribucion)?brutoporaccion[^0-9]{0,25}?(\d+[.,]\d+)"), 1),
    (re.compile(r"(\d+[.,]\d+)(?:euros?|eur|€)(?:brutos?|gross)"), 1),
    (re.compile(r"(\d+[.,]\d+)centimosdeeurobrutos"), 100),
    (re.compile(r"dividendo(?:bruto)?(?:acuenta|complementario|extraordinario|ordinario)?(?:de|porimportede)(\d+[.,]\d+)(?:euros?|eur|€)"), 1),
    (re.compile(r"gross(?:amount|dividend)[^0-9]{0,30}?(\d+[.,]\d+)"), 1),
]


def _importe(t: str) -> float | None:
    for r, div in RE_IMPORTE:
        m = r.search(t)
        if m:
            v = round(float(m.group(1).replace(",", ".")) / div, 6)
            if 0 < v < 50:          # por acción: nada razonable pasa de 50 €
                return v
    return None


def extraer(texto_pdf: str, fecha_com: date, tipo: str = "Dividendo") -> dict:
    """Campos leídos del texto del comunicado. Valida coherencia; lo dudoso se deja vacío.
    Los dividendos flexibles (scrip) no se leen: el importe en efectivo depende de la opción del accionista."""
    vacio = {"importe_bruto_eur": None, "fecha_ex": None, "fecha_registro": None, "fecha_pago": None}
    if tipo != "Dividendo":
        return {**vacio, "extraccion": "flexible: ver comunicado"}
    t = re.sub(r"\s+", "", _norm(texto_pdf))
    fechas = _fechas(t)
    r = {"importe_bruto_eur": _importe(t)}
    for campo, etq in ETIQUETAS.items():
        r[campo] = _fecha_tras(t, fechas, etq)
    # coherencia: fechas entre el comunicado y el 31/12 del año siguiente; ex <= registro <= pago
    for campo in ("fecha_ex", "fecha_registro", "fecha_pago"):
        d = r[campo]
        if d and not (fecha_com <= d <= date(fecha_com.year + 1, 12, 31)):
            r[campo] = None
    # ex <= registro <= pago: si ex y pago se contradicen, fuera las tres; si solo falla el registro, fuera el registro
    if r["fecha_ex"] and r["fecha_pago"] and r["fecha_ex"] > r["fecha_pago"]:
        r.update({"fecha_ex": None, "fecha_registro": None, "fecha_pago": None})
    reg = r["fecha_registro"]
    if reg and ((r["fecha_ex"] and reg < r["fecha_ex"]) or (r["fecha_pago"] and reg > r["fecha_pago"])):
        r["fecha_registro"] = None
    completos = all(r[k] for k in ("importe_bruto_eur", "fecha_ex", "fecha_pago"))
    r["extraccion"] = "completa" if completos else ("parcial" if any(r.values()) else "sin datos")
    return r


# --------------------------------------------------------------------------- descargas
def _texto_pdf(s: requests.Session, nreg: int, enlace: str) -> str | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    txt = CACHE / f"{nreg}.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    try:
        h = s.get(enlace or FICHA.format(nreg), headers=CAB, timeout=120)  # sigue la redirección de la CNMV
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
        pdf = CACHE / f"{nreg}.pdf"
        pdf.write_bytes(p.content)
        texto = subprocess.run(["pdftotext", "-raw", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
        txt.write_text(texto, encoding="utf-8")
        return texto
    except (requests.RequestException, subprocess.SubprocessError, OSError):
        return None
    finally:
        time.sleep(PAUSA)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todos", action="store_true", help="vuelve a extraer también las filas ya guardadas")
    a = ap.parse_args()
    com = pd.read_csv(CLASIFICADOS, dtype={"nreg": int, "isin": str})
    com = com[com["caja"] == "dividendos"]
    previas = pd.read_csv(SALIDA, dtype={"nreg": int}) if SALIDA.exists() else pd.DataFrame(columns=COLUMNAS)
    hechas = set() if a.todos else set(previas["nreg"])
    filas, s = [], requests.Session()
    for _, c in com.sort_values("fecha").iterrows():
        if c["nreg"] in hechas:
            continue
        fecha_com = date.fromisoformat(c["fecha"][:10])
        texto = _texto_pdf(s, int(c["nreg"]), c["enlace"])
        r = extraer(texto, fecha_com, c["etiqueta"]) if texto else {"extraccion": "sin documento"}
        filas.append({"nreg": int(c["nreg"]), "fecha_comunicado": c["fecha"][:10], "isin": c["isin"],
                      "empresa": c["empresa"], "tipo": c["etiqueta"], **{k: r.get(k) for k in ("importe_bruto_eur", "fecha_ex", "fecha_registro", "fecha_pago")},
                      "extraccion": r["extraccion"], "enlace": c["enlace"]})
        print(f'{c["nreg"]} {c["empresa"][:24]:24s} {r["extraccion"]:13s} '
              f'{r.get("importe_bruto_eur")} ex={r.get("fecha_ex")} pago={r.get("fecha_pago")}')
    nuevas = pd.DataFrame(filas, columns=COLUMNAS)
    todo = pd.concat([previas[~previas["nreg"].isin(nuevas["nreg"])], nuevas]).sort_values(["fecha_comunicado", "nreg"])
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    tmp = SALIDA.with_suffix(".csv.tmp")
    todo.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    tmp.replace(SALIDA)
    resumen = todo["extraccion"].value_counts().to_dict()
    print(f"{len(nuevas)} comunicados leídos; en total {len(todo)} filas: {resumen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
