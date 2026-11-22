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
# Versión del lector. Si cambia, las filas leídas con otra se vuelven a leer (desde la caché, sin volver a descargar).
LECTOR = "2026-11-22d"
COLUMNAS = ["canal", "nreg", "fecha_comunicado", "isin", "empresa", "tipo", "importe_bruto", "moneda", "fecha_ex",
            "fecha_registro", "fecha_pago", "extraccion", "intentos", "enlace", "lector"]

MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
MESES.update({"setiembre": 9})
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c)).lower()
    return re.sub("[‐-―−]", "-", x)   # guiones tipográficos: «ex–date», «− Fecha de abono»


# --------------------------------------------------------------------------- lectura de fechas e importes
# pdftotext devuelve muchos comunicados sin espacios («15dediciembrede2026», «Fechadepago»), así que casi todo
# se busca sobre el texto compacto: minúsculas, sin acentos y sin espacios.
_MES = "|".join(sorted(list(MESES) + list(MONTHS), key=len, reverse=True))
RE_FECHA = re.compile(r"(?<!\d)(\d{1,2})(?:de)?(" + _MES + r")(?:de|,)?(20\d\d)"
                      r"|(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](20\d\d)"
                      r"|(" + "|".join(MONTHS) + r")(\d{1,2}),?(20\d\d)")
# «13 de julio», sin año (Rovi, Santander): el año se deduce de la fecha del comunicado (_ano_probable)
RE_FECHA_SIN_ANO = re.compile(r"(?<!\d)(\d{1,2})de(" + "|".join(sorted(MESES, key=len, reverse=True)) + r")(?!(?:de|,)?20\d\d)")


def _ano_probable(dia: int, mes: int, fecha_com: date) -> date | None:
    """Fecha sin año en el calendario de un dividendo: el año del comunicado si la fecha cae después de él; el
    siguiente solo en el cambio de año (comunicado de octubre a diciembre, fecha de enero a marzo). Si no, nada."""
    try:
        d = date(fecha_com.year, mes, dia)
        if d >= fecha_com:
            return d
        if fecha_com.month >= 10 and mes <= 3:
            return date(fecha_com.year + 1, mes, dia)
    except ValueError:
        pass
    return None


def _fechas(texto: str, fecha_com: date | None = None) -> list[tuple[int, int, date]]:
    """Todas las fechas del texto compacto: (inicio, fin, fecha). Con fecha_com, también las escritas sin año."""
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
    if fecha_com:
        for m in RE_FECHA_SIN_ANO.finditer(texto):
            d = _ano_probable(int(m.group(1)), MESES[m.group(2)], fecha_com)
            if d:
                out.append((m.start(), m.end(), d))
    return sorted(out)


ETIQUETAS = {
    "fecha_ex": ["fechaex-dividendo", "fechaexdividendo", "ex-dividenddate", "exdividenddate", "ex-date", "exdate",
                 "sinderechoaldividendo", "sinderechoapercibireldividendo", "cotizaranex-dividendo",
                 "cotizaranexdividendo", "fechadecotizacionexdividendo", "cotizacionexdividendo", "exdividendo",
                 "ex-dividendo"],   # «la acción cotizará ex-dividendo el 29 de octubre de 2026» (Santander)
    "fecha_registro": ["fechaderegistro", "recorddate"],
    "fecha_pago": ["fechadepago", "paymentdate", "sepagarael", "seabonarael", "seabonaraapartirdel", "fechadeabono",
                   "pagadero", "aabonar", "pagoserealizara", "seharaefectivo", "pagodeldividendoserealizara",
                   "pagodeldividendoseefectuara", "pagoseefectuara"],
}
# Entre la etiqueta y la fecha solo puede haber signos y estas palabras de enlace (sin espacios). Así no se
# toma una fecha que solo está cerca («en la fecha ex-dividendo, y se prevé anunciarlo el 3 de noviembre»).
ENLACE_OK = re.compile(r"(?:deldividendo)?(?:\(?[a-z-]*(?:date|day)\)?)?(?:sera|seran|seria|serian|es|sea)?"
                       r"(?:el|del|eldia|apartirdel|elproximo|delproximo|proximo|on)?")   # «Fecha de pago del dividendo: 17 de junio» (Puig)


def _fecha_tras(t: str, fechas: list[tuple[int, int, date]], etiquetas: list[str]) -> tuple[int, date] | None:
    """(posición, fecha) de la primera etiqueta del texto seguida de su fecha: «fecha de pago: 15 de diciembre»."""
    mejor = None
    for e in etiquetas:
        for m in re.finditer(re.escape(e), t):
            for ini, _, d in fechas:
                if ini < m.end():
                    continue
                entre = t[m.end():ini]
                # un punto, una viñeta o un punto y coma en medio: la fecha es de la línea siguiente
                if ini <= m.end() + 40 and not re.search(r"[.;•]", entre) \
                        and ENLACE_OK.fullmatch(re.sub(r"[^a-z-]", "", entre).strip("-")) \
                        and (mejor is None or m.start() < mejor[0]):
                    mejor = (m.start(), d)
                break   # solo cuenta la primera fecha tras la etiqueta
    return mejor


# Calendario escrito al revés: la fecha abre la viñeta y la descripción va detrás («- 12 de enero de 2026. Fecha
# desde la cual las acciones cotizan sin derecho a percibir el dividendo (ex-date).»: Repsol, Sacyr).
TRAS_FECHA = {
    "fecha_ex": ("ex-date", "exdate", "sinderecho"),
    "fecha_registro": ("recorddate", "fechaderegistro"),
    "fecha_pago": ("fechadepago", "fechadeabono", "paymentdate"),
}
_DIA_SEMANA = r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)?$"


def _fechas_delante(t: str, fechas: list[tuple[int, int, date]]) -> dict[str, tuple[int, date]]:
    out: dict[str, tuple[int, date]] = {}
    for ini, fin, d in fechas:
        antes = re.sub(_DIA_SEMANA, "", t[max(0, ini - 12):ini])
        if not re.search(r"[-•)]$", antes) or fin >= len(t) or t[fin] not in ":.":
            continue
        tramo = re.split(r"\.(?!\d)|\(\*\)", t[fin + 1:fin + 301])[0]   # hasta el final de la viñeta
        campos = [c for c, etq in TRAS_FECHA.items() if any(e in tramo for e in etq)]
        if len(campos) == 1 and "lasttradingdate" not in tramo and campos[0] not in out:
            out[campos[0]] = (ini, d)
    return out


# Tabla con la fila de cabeceras y debajo la de valores (Bankinter: «Euros por acción IMPORTE ÍNTEGRO IMPORTE NETO
# EX-DATE RECORD DATE FECHA DE PAGO 0,16093183 0,13035478 22/06/2026 23/06/2026 24/06/2026»). Va sobre el texto
# con espacios: en el compacto, «0,16093183 0,13035478» queda pegado y no se puede separar.
_CABECERAS = {"importe integro": "importe", "importe bruto": "importe", "importe neto": None, "ex-date": "fecha_ex",
              "ex date": "fecha_ex", "record date": "fecha_registro", "fecha de pago": "fecha_pago",
              "payment date": "fecha_pago"}
_RE_CAB = "|".join(re.escape(c) for c in _CABECERAS)
_RE_VALOR = r"\d+,\d+|\d{1,2}/\d{1,2}/20\d\d"
RE_TABLA = re.compile(rf"((?:(?:{_RE_CAB}) ){{3,8}})((?:(?:{_RE_VALOR}) ){{3,8}})")


def _tabla(plano: str) -> dict:
    for m in RE_TABLA.finditer(plano + " "):
        cabs, vals = re.findall(_RE_CAB, m.group(1)), m.group(2).split()
        if len(cabs) != len(vals):
            continue
        r: dict = {}
        for c, v in zip(cabs, vals):
            campo = _CABECERAS[c]
            if campo == "importe" and re.fullmatch(r"\d+,\d+", v):
                if re.search(EUR, plano[max(0, m.start() - 40):m.start()]):   # «euros por acción» encima
                    r["importe"] = float(v.replace(",", "."))
            elif campo and re.fullmatch(r"\d{1,2}/\d{1,2}/20\d\d", v):
                dd, mm, aa = map(int, v.split("/"))
                try:
                    r[campo] = date(aa, mm, dd)
                except ValueError:
                    return {}
            elif campo:
                return {}
        return r
    return {}


EUR = r"(?:euros?|eur|€)"
USD = r"(?:usd|us\$|dolares|dollars?|\$)"
# (patrón, divisor, moneda fija o None si se mira alrededor del número)
RE_IMPORTE = [
    (re.compile(r"importebruto(?:poraccion)?[^0-9]{0,30}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"(?:dividendo|importe|retribucion)?brutoporaccion[^0-9]{0,25}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"dividendo(?:total)?bruto[:]?(\d+[.,]\d+)" + EUR), 1, "EUR"),   # «Dividendo total bruto 0,05 €» (IAG, tabla)
    (re.compile(r"(\d+[.,]\d+)" + EUR + r"(?:brutos?|gross)"), 1, "EUR"),
    # «X euros por acción», «X € (brutos) por cada acción», «(0,20€) brutos por acción» (Merlin), «5,74867096 euros
    # por acción» (Acciona, importe ajustado por la autocartera)
    (re.compile(r"(\d+[.,]\d+)\)?" + EUR + r"\)?(?:brutos?)?\)?por(?:cada)?accion"), 1, "EUR"),
    # céntimos: «12,7 céntimos de euro por acción» (Santander), «8,44 céntimos brutos por acción» (Unicaja)
    (re.compile(r"(\d+[.,]\d+)centimos(?:deeuro)?(?:brutos)?(?:por(?:cada)?accion)?"), 100, "EUR"),
    (re.compile(r"dividendo(?:bruto)?(?:acuenta|complementario|extraordinario|ordinario|final)?(?:de|porimportede)(\d+[.,]\d+)" + EUR), 1, "EUR"),
    (re.compile(r"gross(?:amount|dividend)[^0-9]{0,30}?(\d+[.,]\d+)"), 1, None),
    (re.compile(r"(?:dividend|dividendo)(?:of|de)" + USD + r"(\d+[.,]\d+)"), 1, "USD"),
    # «dividendo a cuenta de los resultados del ejercicio 2026 de 0,15 euros por cada una de las acciones» (Grifols),
    # «dividendo bruto en efectivo a cuenta, con cargo a…, de 0,053 euros por acción» (IAG)
    (re.compile(r"dividendo[a-z0-9,()]{0,100}?de(\d+[.,]\d+)" + EUR + r"(?:brutos?)?(?:poraccion|porcada)"), 1, "EUR"),
]
# Una cifra que no es la del pago que se anuncia: lo ya pagado, el total del año, lo que se espera repartir o el
# objetivo de la política («hasta alcanzar los 0,87 euros por acción en 2029», Redeia). Se busca en la misma frase,
# antes de la cifra (ANTES_NO) o justo después (DESPUES_NO).
ANTES_NO = ("yarealizad", "yapagad", "yaabonad", "distribuyo", "percibirian", "retribuciontotal", "importetotal",
            "remuneraciontotal", "entotal", "ascendera", "ascendio", "sesuma", "elpasado",
            "esperadistribuir", "prevedistribuir", "alcanzar", "suelode", "minimode",   # «establece un suelo de 0,80 euros» (Redeia)
            "dividendoanual", "retencion", "importeneto", "dividendoneto", "netoporaccion",   # IAG: total del año, retención y neto
            "primadeemision")   # Merlin: la parte con cargo a la prima de emisión no es todo lo que se paga por acción
DESPUES_NO = ("yapagad", "yaabonad", "pagadaen", "pagadoen", "pagadosen", "pagadasen", "abonadaen", "abonadoen",
              "abonadosen", "abonadasen", "endospagos", "entrespagos", "endosplazos")
LARGO = 30_000   # caracteres del texto compacto: más es un informe de resultados o de estrategia, no un anuncio


def _moneda_cerca(t: str, ini: int, fin: int) -> str | None:
    """Moneda escrita justo antes o justo después de la cifra (en el texto compacto), con a lo sumo dos o tres
    signos en medio: «0,25€», «0,25(euros)», «(euros):0,25», «usd0.125»."""
    despues, antes = t[fin:fin + 14], t[max(0, ini - 12):ini]
    if re.match(r"[^a-z0-9]{0,2}" + EUR, despues) or re.search(EUR + r"[^a-z0-9]{0,3}$", antes):
        return "EUR"
    if re.match(r"[^a-z0-9]{0,2}" + USD, despues) or re.search(USD + r"[^a-z0-9]{0,3}$", antes):
        return "USD"
    return None


def _importe(t: str, fecha_com: date, fechas: list[tuple[int, int, date]]) -> tuple[float | None, str | None]:
    """Importe bruto por acción del pago que anuncia el comunicado, con su moneda. Sin moneda explícita no hay
    importe. Se descartan las cifras de otros pagos (ANTES_NO, DESPUES_NO, o pegadas a una fecha ya pasada); si
    quedan varias, solo se elige en dos casos seguros: el importe aprobado y el ajustado por la autocartera (vale
    el ajustado, con más decimales) y el total de un pago compuesto de varias partes que suman ese total. Si no,
    nada: la ficha remite al comunicado."""
    valores: dict[float, tuple[str, int]] = {}
    for r, div, moneda in RE_IMPORTE:
        for m in r.finditer(t):
            num, ini = m.group(1), m.start(1)
            v = round(float(num.replace(",", ".")) / div, 8)
            if not 0 < v < 50:          # por acción: nada razonable pasa de 50
                continue
            mon = moneda or _moneda_cerca(t, ini, m.end(1))
            if not mon:
                continue
            frase = t[max(0, ini - 150):ini]
            cortes = [x.end() for x in re.finditer(r"\.(?!\d)", frase)]
            antes = frase[cortes[-1]:] if cortes else frase
            despues = re.split(r"\.(?!\d)", t[m.end(1):m.end(1) + 80])[0]
            if any(w in antes for w in ANTES_NO) or any(w in despues for w in DESPUES_NO):
                continue
            # «primer pago – 14 de julio de 2026: importe bruto por acción a distribuir de 0,32 euros» (Fluidra)
            if any(f < fecha_com and ini - len(antes) <= a and fin_f <= ini and ini - fin_f <= 45 for a, fin_f, f in fechas):
                continue
            decimales = len(re.split(r"[.,]", num)[-1]) + (2 if div == 100 else 0)
            if v not in valores or decimales > valores[v][1]:
                valores[v] = (mon, decimales)
    if not valores or len({mon for mon, _ in valores.values()}) > 1:
        return None, None
    vs = sorted(valores)
    if len(vs) == 1:
        return vs[0], valores[vs[0]][0]
    # aprobado (hasta 3 decimales) y ajustado por la autocartera (4 o más), a menos de un 5 %: el ajustado
    precisos = [v for v in vs if valores[v][1] >= 4]
    if len(vs) == 2 and len(precisos) == 1 and vs[1] <= vs[0] * 1.05:
        return precisos[0], valores[precisos[0]][0]
    # «0,56 euros mediante el reparto de 0,53 con cargo a reservas y un dividendo a cuenta de 0,03» (Repsol)
    if len(vs) >= 3 and abs(vs[-1] - sum(vs[:-1])) < 5e-4 and \
            not any(w in t for w in ("dospagos", "dosplazos", "primerpago", "segundopago")):
        return vs[-1], valores[vs[-1]][0]
    return None, None


def extraer(texto_pdf: str, fecha_com: date, tipo: str = "Dividendo") -> dict:
    """Campos leídos del texto del comunicado. Valida coherencia; lo dudoso se deja vacío."""
    vacio = {"importe_bruto": None, "moneda": None, "fecha_ex": None, "fecha_registro": None, "fecha_pago": None}
    if tipo == "Dividendo flexible":
        return {**vacio, "extraccion": "flexible: ver comunicado"}
    if tipo != "Dividendo":   # política de dividendos y otros anuncios sin un pago concreto: no se lee importe
        return {**vacio, "extraccion": "sin pago: ver comunicado"}
    plano = re.sub(r"\s+", " ", _norm(texto_pdf))
    t = plano.replace(" ", "")
    if len(t) > LARGO:
        return {**vacio, "extraccion": "sin datos"}
    fechas = _fechas(t, fecha_com)
    r = dict(vacio)
    tabla = _tabla(plano)
    if tabla.get("importe"):
        r["importe_bruto"], r["moneda"] = tabla["importe"], "EUR"
    else:
        r["importe_bruto"], r["moneda"] = _importe(t, fecha_com, fechas)
    # Un calendario en viñetas con la fecha delante (dos campos o más) manda sobre las etiquetas sueltas del texto:
    # en Repsol, «fecha de pago a partir del 1 de enero» es el plazo de la junta y «el ex-date el 13 de enero», el
    # de los ADR. Si no, la primera etiqueta seguida de su fecha; y si tampoco, la tabla.
    delante = _fechas_delante(t, fechas)
    for campo, etq in ETIQUETAS.items():
        if len(delante) >= 2 and campo in delante:
            r[campo] = delante[campo][1]
            continue
        x = _fecha_tras(t, fechas, etq) or delante.get(campo)
        r[campo] = x[1] if x else tabla.get(campo)
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
    """Lee los comunicados de dividendo nuevos (o sin documento legible, hasta MAX_INTENTOS, o leídos con otra versión
    del lector) y reescribe datos/dividendos.csv. `texto_de(canal, nreg, enlace)` permite probar sin red."""
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
        # se relee si el lector cambia o si el colector clasifica de otra forma el comunicado (de «Dividendo» a
        # «Dividendo flexible», por ejemplo)
        if previa is not None and not todos and previa.lector == LECTOR and previa.tipo == c["etiqueta"] \
                and (previa.extraccion != "sin documento" or intentos >= MAX_INTENTOS):
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
                       "extraccion": r["extraccion"], "intentos": str(intentos + 1), "enlace": c["enlace"], "lector": LECTOR})
    # un comunicado que el colector ya no clasifica como dividendo (Ferrovial, OIR 37412: una nota de resultados) sale
    vigentes = set(zip(com["canal"], com["nreg"]))
    sobran = [(a, b) not in vigentes for a, b in zip(previas["canal"], previas["nreg"])]
    if nuevas or any(sobran):
        n = pd.DataFrame(nuevas, columns=COLUMNAS)
        clave = set(zip(n["canal"], n["nreg"]))
        resto = previas[[(a, b) not in clave and (a, b) in vigentes for a, b in zip(previas["canal"], previas["nreg"])]]
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
