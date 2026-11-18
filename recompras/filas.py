"""Recompras (indicador 17), fase 0: lector genérico de las filas de operaciones de los informes
semanales de recompra que las empresas del IBEX 35 envían a la CNMV (Otra Información Relevante,
art. 5 del Reglamento 596/2014 y arts. 2.2 y 2.3 del Reglamento Delegado 2016/1052).

Cada empresa maqueta su PDF a su manera (orden de columnas, idioma, separadores), pero todas las
filas de operaciones comparten tres señas: una fecha, un centro de negociación y al menos dos
cifras (número de acciones y precio medio). Este lector busca esas señas línea a línea sobre el
texto de `pdftotext -layout`, sin depender del orden de las columnas.

Funciones:
- leer_filas(texto): filas de operaciones (lista de dict) del texto de un PDF.
- resumen(filas): agregado por documento (acciones, precio medio ponderado, fechas, centros).
- totales_declarados(texto): las líneas «Total» del propio documento, para contrastar.
"""

import re

VERSION = "0.1.0"

# Centros de negociación que aparecen en los informes (códigos MIC o abreviaturas de la empresa).
CENTROS = {
    "XMAD": "XMAD", "CEUX": "CEUX", "TQEX": "TQEX", "AQEU": "AQEU", "XLON": "XLON", "BATE": "BATE",
    "CHIX": "CHIX", "TRQX": "TRQX", "XPAR": "XPAR", "XETR": "XETR", "XAMS": "XAMS", "XNAS": "XNAS",
    "LON": "XLON", "MAD": "XMAD",
}
CENTRO_TEXTO = [
    (re.compile(r"centros? de negociaci[oó]n estadounidenses?", re.I), "EEUU"),
    (re.compile(r"\bUS trading venues?\b", re.I), "EEUU"),
]
MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12}

FECHA_ES = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
FECHA_EN = re.compile(r"\b(\d{2})-([A-Za-z]{3})-(\d{2,4})\b")
HORA = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
CIFRA = re.compile(r"(?<![\w/,.:-])([£$€]\s*)?(\d[\d.,]*\d|\d)(?![\w/:-])")
OPERACION = re.compile(r"\b(compra|comprar|purchase|buy|venta|vender|sale|sell)\b", re.I)
MONEDA = {"£": "GBP", "$": "USD", "€": "EUR"}


def _fecha(linea):
    """(fecha ISO, tramo, estilo numérico de la línea) o (None, None, None)."""
    m = FECHA_ES.search(linea)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mes <= 12 and 1 <= d <= 31:
            return f"{a:04d}-{mes:02d}-{d:02d}", m.span(), "es"
        return None, None, None
    m = FECHA_EN.search(linea)
    if m and m.group(2).lower() in MESES_EN:
        d, mes, a = int(m.group(1)), MESES_EN[m.group(2).lower()], int(m.group(3))
        if a < 100:
            a += 2000
        if 1 <= d <= 31:
            return f"{a:04d}-{mes:02d}-{d:02d}", m.span(), "en"
    return None, None, None


def _centro(linea):
    for patron, codigo in CENTRO_TEXTO:
        m = patron.search(linea)
        if m:
            return codigo, m.span()
    for palabra in re.finditer(r"\b([A-Z]{3,4})\b", linea):
        if palabra.group(1) in CENTROS:
            return CENTROS[palabra.group(1)], palabra.span()
    return None, None


def _numero(texto, estilo="es"):
    """Convierte una cifra según el estilo de la línea. Español: el punto separa miles y la coma decimales
    ('763.405' -> 763405, '29,3857' -> 29.3857, '89,648' -> 89.648). Inglés (la fecha va como 09-Nov-26):
    la coma separa miles y el punto decimales ('391,656' -> 391656, '4.448' -> 4.448)."""
    t = texto.strip()
    if estilo == "en":
        return float(t.replace(",", ""))
    return float(t.replace(".", "").replace(",", "."))


MARCA_ANEXO = re.compile(r"^\s*(anexo|annex|appendix|se acompaña|detalle (de|sobre) (las|cada)|"
                         r"transaction details|individual trade)", re.I)


def primera_tabla(texto):
    """Texto hasta la primera marca de anexo (los informes resumen por día y centro en la primera tabla y
    detallan cada operación después). Si no hay marca, el texto entero."""
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        if MARCA_ANEXO.match(linea):
            return "\n".join(lineas[:i])
    return texto


def leer_filas(texto, solo_primera_tabla=True):
    """Filas de operaciones del texto de un informe. Cada fila: fecha, centro, operacion, acciones,
    precio, moneda, detalle (True si la fila lleva hora: operación individual del anexo, no el
    resumen diario), linea (texto original, para auditar). Por defecto solo la primera tabla (el
    resumen diario); si esa parte no tiene filas, se lee el texto entero y se descartan las de detalle."""
    if solo_primera_tabla:
        filas = _filas(primera_tabla(texto))
        if filas:
            return filas
        return [f for f in _filas(texto) if not f["detalle"]]
    return _filas(texto)


def _filas(texto):
    filas = []
    for cruda in texto.splitlines():
        linea = cruda.strip()
        if not linea:
            continue
        fecha, tramo_fecha, estilo = _fecha(linea)
        if not fecha:
            continue
        centro, tramo_centro = _centro(linea)
        if not centro:
            continue
        resto = linea[:tramo_fecha[0]] + " " + linea[tramo_fecha[1]:]
        hora = HORA.search(resto)
        detalle = bool(hora)
        if hora:
            resto = resto.replace(hora.group(0), " ")
        # Quitar el centro en forma de texto largo para que no aporte cifras.
        for patron, _ in CENTRO_TEXTO:
            resto = patron.sub(" ", resto)
        cifras, moneda = [], "EUR"
        for m in CIFRA.finditer(resto):
            simbolo = (m.group(1) or "").strip()
            if simbolo:
                moneda = MONEDA.get(simbolo, moneda)
            try:
                cifras.append(_numero(m.group(2), estilo))
            except ValueError:
                continue
        if len(cifras) < 2:
            continue
        acciones, precio = cifras[0], cifras[1]
        if acciones != int(acciones) or acciones <= 0 or precio <= 0:
            continue
        op = OPERACION.search(linea)
        operacion = "compra"
        if op and op.group(1).lower() in ("venta", "vender", "sale", "sell"):
            operacion = "venta"
        filas.append({"fecha": fecha, "centro": centro, "operacion": operacion, "acciones": int(acciones),
                      "precio": round(precio, 6), "moneda": moneda, "detalle": detalle, "linea": linea})
    return filas


def resumen(filas, solo_resumen_diario=True):
    """Agregado de un documento: acciones compradas, precio medio ponderado por moneda, fechas y centros.
    Por defecto ignora las filas de detalle (con hora), que repiten lo que ya resume la tabla diaria."""
    base = [f for f in filas if f["operacion"] == "compra" and (not solo_resumen_diario or not f["detalle"])]
    if not base:
        return {"filas": 0, "acciones": 0, "precio_medio": {}, "desde": None, "hasta": None, "centros": [], "dias": 0}
    acciones = sum(f["acciones"] for f in base)
    medios = {}
    for moneda in sorted({f["moneda"] for f in base}):
        grupo = [f for f in base if f["moneda"] == moneda]
        n = sum(f["acciones"] for f in grupo)
        medios[moneda] = round(sum(f["acciones"] * f["precio"] for f in grupo) / n, 4) if n else None
    fechas = sorted({f["fecha"] for f in base})
    return {"filas": len(base), "acciones": acciones, "precio_medio": medios, "desde": fechas[0], "hasta": fechas[-1],
            "centros": sorted({f["centro"] for f in base}), "dias": len(fechas)}


TOTAL = re.compile(r"^\s*total\b.*?(\d[\d.,]*\d)", re.I | re.M)


def totales_declarados(texto):
    """Primera cifra de cada línea que empieza por «Total» (número de acciones del propio documento)."""
    salida = []
    for m in TOTAL.finditer(texto):
        try:
            salida.append(int(_numero(m.group(1), "en" if re.search(r"\d,\d{3}\b", m.group(1)) else "es")))
        except ValueError:
            continue
    return salida
