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
MESES = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
         "ene": 1, "abr": 4, "ago": 8, "sept": 9, "dic": 12}

FECHA_ES = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
FECHA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
FECHA_MES = re.compile(r"\b(\d{2})-([A-Za-z]{3,4})\.?-(\d{2,4})\b")  # 09-Nov-26 (inglés) o 28-oct.-26 (español)
HORA = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
# Una cifra: con separadores de miles por punto o coma, por espacio entre grupos de tres ('17 271') o sin ellos.
CIFRA = re.compile(r"(?<![\w/,.:-])([£$€]\s*)?(\d{1,3}(?: \d{3})+(?:[.,]\d+)?|\d[\d.,]*\d|\d)(?![\w/:-])")
OPERACION = re.compile(r"\b(compra|comprar|purchase|buy|venta|vender|sale|sell)\b", re.I)
MONEDA = {"£": "GBP", "$": "USD", "€": "EUR"}


def orden_fechas(texto, con_hora=None):
    """Orden de las fechas dd/dd/aaaa de un texto: «dm» (día/mes, como en España), «md» (mes/día, como en EE. UU.) o
    None si el texto no lo delata o se contradice. Si alguna fecha tiene el primer número mayor que 12, es día/mes; si
    alguna tiene el segundo mayor que 12, mes/día. `con_hora` mira solo las líneas con hora (True, el detalle) o sin
    ella (False, el resumen diario): ArcelorMittal escribe el resumen en mes/día y el detalle en día/mes (comunicado
    43205, 19/10/2026)."""
    primero = segundo = False
    for linea in texto.splitlines():
        if con_hora is not None and bool(HORA.search(linea)) != con_hora:
            continue
        for m in FECHA_ES.finditer(linea):
            primero |= int(m.group(1)) > 12
            segundo |= int(m.group(2)) > 12
    if primero != segundo:
        return "dm" if primero else "md"
    return None


def _fecha(linea, orden="dm"):
    """(fecha ISO, tramo, estilo numérico que sugiere la fecha) o (None, None, None). El estilo de la fecha solo se
    usa cuando las propias cifras de la fila no lo delatan (ver _estilo). `orden`: «dm» o «md» para dd/dd/aaaa."""
    m = FECHA_ES.search(linea)
    if m:
        a, b, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mes = (b, a) if orden == "md" else (a, b)
        if 1 <= mes <= 12 and 1 <= d <= 31:
            return f"{anio:04d}-{mes:02d}-{d:02d}", m.span(), ("en" if orden == "md" else "es")
        return None, None, None
    m = FECHA_ISO.search(linea)
    if m:
        a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mes <= 12 and 1 <= d <= 31 and 2000 <= a <= 2100:
            return f"{a:04d}-{mes:02d}-{d:02d}", m.span(), "es"
    m = FECHA_MES.search(linea)
    if m and m.group(2).lower() in MESES:
        d, mes, a = int(m.group(1)), MESES[m.group(2).lower()], int(m.group(3))
        if a < 100:
            a += 2000
        if 1 <= d <= 31:
            estilo = "es" if m.group(2).lower() in ("ene", "abr", "ago", "sept", "dic") or "." in m.group(0) else "en"
            return f"{a:04d}-{mes:02d}-{d:02d}", m.span(), estilo
    return None, None, None


def _estilo(acciones_txt, estilo_fecha):
    """Estilo numérico de la fila según la cifra de acciones (entera): '763.405' -> español; '391,656' -> inglés;
    sin separador o con espacios -> el que sugiere la fecha."""
    t = acciones_txt.strip()
    if "." in t and "," not in t:
        return "es"
    if "," in t and "." not in t:
        return "en"
    if "." in t and "," in t:
        return "es" if t.rfind(",") > t.rfind(".") else "en"
    return estilo_fecha


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
    """Convierte una cifra según el estilo de la fila. Español: el punto separa miles y la coma decimales
    ('763.405' -> 763405, '29,3857' -> 29.3857, '89,648' -> 89.648). Inglés: la coma separa miles y el punto
    decimales ('391,656' -> 391656, '4.448' -> 4.448). Los espacios entre grupos de tres son miles ('17 271').
    Un único separador seguido de un grupo que no es de tres cifras es decimal sea cual sea el estilo ('54.61',
    '42,9351'); dos separadores distintos: el último es el decimal ('1.143.996,50', '1,143,996.50')."""
    t = texto.strip().replace(" ", "")
    puntos, comas = t.count("."), t.count(",")
    if puntos and comas:
        return float(t.replace(".", "").replace(",", ".")) if t.rfind(",") > t.rfind(".") else float(t.replace(",", ""))
    sep = "." if puntos else ("," if comas else None)
    if sep is None:
        return float(t)
    grupos = t.split(sep)
    if len(grupos) == 2 and len(grupos[1]) != 3:
        return float(t.replace(",", "."))  # decimal evidente
    if len(grupos) > 2 or (estilo == "es" and sep == ".") or (estilo == "en" and sep == ","):
        return float(t.replace(sep, ""))  # miles
    return float(t.replace(",", "."))  # decimal con tres cifras ('4.448' en inglés, '89,648' en español)


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


def leer_filas(texto, solo_primera_tabla=True, orden=None):
    """Filas de operaciones del texto de un informe. Cada fila: fecha, centro, operacion, acciones,
    precio, moneda, detalle (True si la fila lleva hora: operación individual del anexo, no el
    resumen diario), linea (texto original, para auditar). Por defecto solo la primera tabla (el
    resumen diario); si esa parte no tiene filas, se lee el texto entero y se descartan las de detalle.
    `orden` fuerza «dm» o «md» en las fechas dd/dd/aaaa; si no se da, se deduce del propio texto leído
    (orden_fechas) y, si no lo delata, día/mes."""
    def _o(t):
        if orden:
            return orden, orden
        return orden_fechas(t, con_hora=False) or "dm", orden_fechas(t, con_hora=True) or "dm"
    if solo_primera_tabla:
        t1 = primera_tabla(texto)
        filas = [f for f in _filas(t1, *_o(t1)) if not f["detalle"]]
        if filas:
            return filas
        return [f for f in _filas(texto, *_o(texto)) if not f["detalle"]]
    return _filas(texto, *_o(texto))


def _filas(texto, orden="dm", orden_detalle="dm"):
    filas = []
    for cruda in texto.splitlines():
        linea = cruda.strip()
        if not linea:
            continue
        fecha, tramo_fecha, estilo_fecha = _fecha(linea, orden_detalle if HORA.search(linea) else orden)
        if not fecha:
            continue
        centro, tramo_centro = _centro(linea)
        if not centro:
            if not ISIN.search(linea):
                continue
            centro = "n/d"  # fila con ISIN pero sin centro (ArcelorMittal agrega por día y mercado sin código)
        resto = linea[:tramo_fecha[0]] + " " + linea[tramo_fecha[1]:]
        resto = ISIN.sub(" ", resto)
        hora = HORA.search(resto)
        detalle = bool(hora)
        if hora:
            resto = resto.replace(hora.group(0), " ")
        # Quitar el centro en forma de texto largo para que no aporte cifras.
        for patron, _ in CENTRO_TEXTO:
            resto = patron.sub(" ", resto)
        crudas, moneda = [], "EUR"
        for m in CIFRA.finditer(resto):
            simbolo = (m.group(1) or "").strip()
            if simbolo:
                moneda = MONEDA.get(simbolo, moneda)
            crudas.append(m.group(2))
        if len(crudas) < 2:
            continue
        estilo = _estilo(crudas[0], estilo_fecha)
        try:
            cifras = [_numero(c, estilo) for c in crudas]
        except ValueError:
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


TOTAL = re.compile(r"(?:^\s*[Tt]otal\b|\bTOTAL\b)[^\n]{0,80}?(\d{1,3}(?: \d{3})+|\d[\d.,]*\d)", re.M)
TOTAL_FRASE = re.compile(r"n[úu]mero total de acciones (?:compradas|adquiridas)[^.]{0,60}?asciende a\s+([\d.,]+)\s+acciones", re.I)
CONTEXTO_PROGRAMA = re.compile(r"programa|hasta la fecha|desde el inicio|acumulad|tramo", re.I)


def _entero(texto):
    t = texto.strip()
    estilo = "en" if re.search(r"^\d{1,3}(,\d{3})+$", t) else "es"
    return int(_numero(t, estilo))


def totales_declarados(texto):
    """Totales de acciones que declara el propio documento: la primera cifra de cada línea que empieza por «Total»
    y las frases «el número total de acciones compradas asciende a N acciones» que no hablan del programa entero."""
    salida = []
    for m in TOTAL.finditer(texto):
        try:
            salida.append(_entero(m.group(1)))
        except ValueError:
            continue
    plano = re.sub(r"\s+", " ", texto)
    for m in TOTAL_FRASE.finditer(plano):
        frase = plano[max(0, m.start() - 80):m.end() + 40]
        if CONTEXTO_PROGRAMA.search(frase):
            continue
        try:
            salida.append(_entero(m.group(1)))
        except ValueError:
            continue
    return salida
