"""Dividendos del IBEX 35 a partir de los comunicados de la CNMV (sin BME).

Para cada comunicado de una empresa del IBEX 35 que el colector `cnmv` clasifica en la caja «dividendos»
(`<salida>/cnmv/datos/ibex35.csv`), abre su ficha en la CNMV, descarga el PDF del comunicado, lo pasa a texto y
busca el importe bruto por acción con su moneda, la fecha ex-dividendo, la fecha de registro y la fecha de pago.

- Fuente: CNMV (nota legal verificada el 02/11/2026: reproducción fiel; se permiten cálculos; gratuito en
  cnmv.es). Cada fila lleva el enlace al comunicado original.
- Solo se rellenan los campos que se leen con seguridad; un importe sin moneda explícita no se publica. Si falta
  algo, la fila queda «parcial» y la ficha remite al comunicado. Nada se inventa ni se completa a mano.
- Dividendos flexibles (scrip), desde el 24/11/2026: solo el efectivo fijo por acción para quien elige cobrar en
  efectivo y su fecha de pago, con las frases exactas de RE_FLEX_ACCION, RE_FLEX_DERECHO y RE_FLEX_PAGO (revisadas
  contra el PDF de Iberdrola, ACS, Ferrovial y Sacyr). Se descargan solo los comunicados cuyo título anuncia un
  documento que puede traerlos (FLEX_TITULOS). Quien elige acciones nuevas cobra en acciones: lo dice la ficha.
- Dividendos anunciados dentro de los resultados (24/11/2026): solo las empresas de la lista cerrada
  `cnmv/dividendo_en_resultados.csv` (Inditex, Logista y Naturgy), con el formato revisado de su nota (`extraer_resultados`); una
  fila por pago en `<salida>/cnmv/datos/dividendos_resultados.csv`. Las remisiones de información financiera periódica
  (informe financiero anual e informes semestrales) no se piden: su ficha de la CNMV no tiene documento. Una nota sin
  texto no tapa a las demás (25/11/2026): primero se piden las que nunca se han pedido y las que fallaron se repiten
  una vez al día, hasta MAX_INTENTOS.
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
from datetime import date, timedelta
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
LIMITE_RESULTADOS = 5   # notas de resultados nuevas por pasada (dividendos anunciados en los resultados)
# Versión del lector. Si cambia, las filas leídas con otra se vuelven a leer (desde la caché, sin volver a descargar).
LECTOR = "2026-11-24a"
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


# Dividendos flexibles (24/11/2026). Solo el efectivo fijo por acción para quien elige cobrar en efectivo y la fecha en
# que se paga, con estas frases exactas, revisadas contra el PDF (texto compacto: minúsculas, sin acentos ni espacios):
#   Iberdrola, complemento al documento informativo de cada edición: «El importe del Dividendo a Cuenta bruto por acción
#     es de 0,253 euros» (OIR 38415); con dividendo de ajuste vale el total: «El importe del Dividendo Complementario
#     Total bruto por acción es de 0,427 euros» (OIR 41685, frente al 0,425 sin el ajuste).
#   Ferrovial: «el importe del dividendo en efectivo asciende a 0,8350 euros por cada acción existente» (OIR 43459).
#   ACS y Sacyr, precio fijo por derecho, con un derecho por acción («un derecho de asignación gratuita por cada
#     acción»): «El precio del Compromiso de Compra de derechos asumido por ACS es de 1,866 euros brutos por derecho»
#     (OIR 41519); «a un precio fijo de 0,049 euros brutos por cada derecho» (OIR 38419).
#   Fecha de pago, la línea del calendario: «1 de febrero de 2027 • Pago del Dividendo a Cuenta a quienes hubieran
#     optado por recibir efectivo» (Iberdrola), «15 de julio de 2026: Pago de efectivo a los accionistas que hayan
#     solicitado retribución en efectivo» (ACS), «29 de enero de 2026 Pago de efectivo a los accionistas que hubieran
#     optado por recibir efectivo» (Sacyr), «A partir del 10 de diciembre de 2026 : Pago del dividendo en efectivo y
#     entrega de las acciones» (Ferrovial).
# Los importes «como mínimo», «objetivo» o «máximo» de los términos y condiciones no casan con estas frases; dos
# importes distintos o dos fechas distintas en el mismo comunicado, tampoco: se queda sin leer.
RE_FLEX_ACCION = re.compile(r"elimportedeldividendo(?:(?:acuenta|complementario)(total)?brutoporaccionesde|enefectivoasciendea)"
                            r"(\d+[.,]\d+)euros")
RE_FLEX_DERECHO = re.compile(r"(?:elpreciodelcompromisodecompra(?:dederechos)?(?:asumidopor[a-z]{2,30})?esde|aunpreciofijode)"
                             r"(\d+[.,]\d+)eurosbrutospor(?:cada)?derecho")
UN_DERECHO_POR_ACCION = "underechodeasignaciongratuitaporcadaaccion"
RE_FLEX_PAGO = re.compile(r"(?<!\d)(\d{1,2})de(" + "|".join(sorted(MESES, key=len, reverse=True)) + r")de(20\d\d)[^a-z0-9]{0,6}"
                          r"pago(?:deldividendo(?:acuenta|complementario|enefectivo)|deefectivo)"
                          r"(?:aquieneshubieranoptadoporrecibirefectivo|alosaccionistasque(?:hayansolicitadoretribucionenefectivo"
                          r"|hubieranoptadoporrecibirefectivo)|yentrega)")
# Títulos de los comunicados de flexible que pueden traer el importe o el calendario (el resto no se descarga):
# «Complemento al documento informativo…», «Términos y condiciones…» (Iberdrola), «Primera ejecución del dividendo
# flexible…» (ACS), «Ejecución del acuerdo de ampliación de capital (scrip dividend)…» (Sacyr), «Ferrovial anuncia el
# importe del dividendo en efectivo…» y «…dividendo flexible (scrip dividend) pagadero en acciones o en efectivo».
FLEX_TITULOS = ("documento informativo", "terminos y condiciones", "ejecucion", "importe del dividendo", "pagadero")


def flexible_con_documento(titulo: str) -> bool:
    t = " " + re.sub(r"\s+", " ", _norm(titulo)) + " "
    return any(p in t for p in FLEX_TITULOS)


def _extraer_flexible(t: str, fecha_com: date) -> dict:
    """Efectivo fijo por acción y fecha de pago de un dividendo flexible, sobre el texto compacto."""
    r = {"importe_bruto": None, "moneda": None, "fecha_ex": None, "fecha_registro": None, "fecha_pago": None}
    por_accion = [(bool(m.group(1)), round(float(m.group(2).replace(",", ".")), 8)) for m in RE_FLEX_ACCION.finditer(t)]
    valores = {v for total, v in por_accion if total} or {v for _, v in por_accion}
    if not valores and UN_DERECHO_POR_ACCION in t:
        valores = {round(float(m.group(1).replace(",", ".")), 8) for m in RE_FLEX_DERECHO.finditer(t)}
    if len(valores) == 1 and 0 < min(valores) < 50:
        r["importe_bruto"], r["moneda"] = min(valores), "EUR"
    pagos = set()
    for d, mes, a in RE_FLEX_PAGO.findall(t):
        try:
            f = date(int(a), MESES[mes], int(d))
        except ValueError:
            continue
        if fecha_com <= f <= date(fecha_com.year + 1, 12, 31):
            pagos.add(f)
    if len(pagos) == 1:
        r["fecha_pago"] = pagos.pop()
    r["extraccion"] = ("flexible: completa" if r["importe_bruto"] and r["fecha_pago"]
                       else "flexible: parcial" if r["importe_bruto"] or r["fecha_pago"] else "flexible: ver comunicado")
    return r


def extraer(texto_pdf: str, fecha_com: date, tipo: str = "Dividendo") -> dict:
    """Campos leídos del texto del comunicado. Valida coherencia; lo dudoso se deja vacío."""
    vacio = {"importe_bruto": None, "moneda": None, "fecha_ex": None, "fecha_registro": None, "fecha_pago": None}
    if tipo == "Dividendo flexible":
        if not texto_pdf.strip():
            return {**vacio, "extraccion": "flexible: ver comunicado"}
        return _extraer_flexible(re.sub(r"\s+", "", _norm(texto_pdf)), fecha_com)
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
        # política de dividendos y flexibles cuyo título no anuncia importe ni calendario: no se descarga nada
        if c["etiqueta"] != "Dividendo" and not (c["etiqueta"] == "Dividendo flexible" and flexible_con_documento(c["texto"])):
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
    # dividendos anunciados dentro de los resultados (lista cerrada), después de lo anterior y con su propio límite
    res = actualizar_resultados(datos, limite=LIMITE_RESULTADOS, texto_de=texto_de)
    return {"leidos": len(nuevas), "pendientes": pendientes, "total": len(todo), "resumen": resumen, "resultados": res}


# --------------------------------------------------------------------------- dividendos anunciados en los resultados
# Algunas empresas del IBEX 35 no envían a la CNMV un comunicado propio de dividendo: lo anuncian en su nota de
# resultados. Solo se leen las de la lista cerrada cnmv/dividendo_en_resultados.csv, cada una con el formato revisado
# de su nota. Formato «pagos» (Inditex, OIR 39667 del 11/03/2026): «… propondrá a la Junta General de Accionistas un
# dividendo de 1,75€ por acción … El dividendo se abonará en dos pagos iguales: El 4 mayo 2026 un pago de 0,875€ por
# acción, correspondiente al dividendo ordinario. El 2 noviembre 2026 un pago de 0,875€ por acción (0,325€ ordinario +
# 0,550€ extraordinario)», y una tabla «Fecha de pago Record date Ex-date» con una fila de tres fechas por pago.
# Reglas: la suma de los pagos tiene que ser el dividendo anunciado; cada fecha de pago, posterior al comunicado y como
# mucho dos años después; ex y registro solo si la tabla trae la fila de esa fecha de pago, y ex ≤ registro ≤ pago. Si
# algo no cuadra, ese comunicado no da nada. Un mismo pago anunciado en varios comunicados (nota y presentación) sale una
# vez, del primero. Salida: datos/dividendos_resultados.csv, una fila por pago; la leen la ficha integrada y el calendario.
#
# Formato «politica» (Logista: apartado «D. Política de dividendos» de sus notas de resultados; OIR 37569, 38742, 40562
# y 43515, revisadas el 25/11/2026). Tres frases:
#  - propuesto: «… tiene la intención de proponer a la Junta General de Accionistas la distribución de un dividendo bruto
#    complementario del ejercicio 2026 de 211 millones de euros (1,59 euros por acción), que se pagará en el primer
#    trimestre del año natural 2027» → importe sin fechas: «anunciado: pago previsto en el primer trimestre de 2027»;
#  - a cuenta: «el Consejo de Administración aprobó el 23 de julio de 2026, la distribución de un dividendo bruto a cuenta
#    del ejercicio 2026, que se desembolsó el 27 de agosto y alcanzó a 77 millones de euros (0,58 euros por acción)»: la
#    fecha de pago no trae año; se toma el de la aprobación (o, sin ella, el del ejercicio) y el pago tiene que caer
#    entre la aprobación y seis meses después;
#  - complementario aprobado: «La Junta General de Accionistas celebrada el 4 de febrero de 2026, aprobó la distribución
#    de un dividendo complementario del ejercicio 2025 de 203 millones de euros (1,53 euros por acción). Este dividendo
#    está compuesto por un dividendo complementario de 1,45 euros por acción más un dividendo extraordinario de 0,08
#    euros por acción, ambos desembolsados el pasado 26 de febrero de 2026» (o «ambos que se pagarán conjuntamente el
#    próximo …»): las dos partes tienen que sumar el total.
# Formato «efectivo» (Naturgy: IP 3095, 3290 y 3392 y OIR 40515, revisadas el 25/11/2026):
#  - «Naturgy pagó su dividendo final de 2025 de 0,57€/acción en efectivo el 31 de marzo de 2026», «pagará su primer
#    dividendo a cuenta de 2026 de 0,60€/acción en efectivo el 29 de julio de 2026», «… y pagará un segundo dividendo a
#    cuenta de 2026 de 0,60€ por acción en efectivo el 5 de noviembre de 2026», «El dividendo final de Naturgy para
#    2024 de 0,60€/acción se pagó en efectivo el 9 de abril de 2025»;
#  - propuesto: «un dividendo final para 2025 de 0,57€/acción, sujeto a aprobación por la JGA, a pagar en marzo de 2026».
#  No se lee «El primer y segundo dividendo a cuenta de 2025 de 0,60€/acción se pagaron en efectivo el 30 de julio y el 5
#  de noviembre, respectivamente» (dos pagos en una frase y sin año).
# En los dos formatos: ninguna nota da fecha ex ni de registro, así que un pago fechado sale «solo pago»; un pago puede
# ser anterior a la nota (lo cuenta después), como mucho 400 días; un dividendo propuesto sale sin fechas («anunciado:
# …») y se descarta si otra nota da la fecha del mismo dividendo (misma empresa, ejercicio y tipo). Nunca se deduce una
# fecha que la nota no da, salvo el año del pago a cuenta de Logista, que sale de la fecha de aprobación de la frase.
EN_RESULTADOS = Path(__file__).resolve().parent / "dividendo_en_resultados.csv"
# Remisiones de información financiera periódica: el informe financiero anual y los semestrales están en el registro
# de información periódica de la CNMV, y su ficha de «Otra información relevante» no enlaza ningún documento
# (/webservices/verdocumento/). Comprobado el 25/11/2026 con las once de Inditex, Logista y Naturgy de los trece meses
# anteriores: ninguna lo tiene. No se piden.
RE_PERIODICA = re.compile(r"remite (?:el )?informe financiero anual|remite informacion financiera del (?:primer|segundo) semestre")
COLUMNAS_RES = ["canal", "nreg", "pago", "fecha_comunicado", "isin", "empresa", "concepto", "importe_bruto", "moneda",
                "fecha_ex", "fecha_registro", "fecha_pago", "extraccion", "dividendo_anunciado", "enlace", "lector"]
_F = r"(\d{1,2})(?:de)?(" + "|".join(sorted(MESES, key=len, reverse=True)) + r")(?:de)?(20\d\d)"
RE_RES_ANCLA = re.compile(r"eldividendoseabonaraen(dos|tres|cuatro)pagos")
NUM_PAGOS = {"dos": 2, "tres": 3, "cuatro": 4}
RE_RES_TOTAL = re.compile(r"undividendode(\d+[.,]\d+)(?:€|euros)(?:brutos)?poraccion")
RE_RES_PAGO = re.compile(r"(?<![a-z])el" + _F + r"unpagode(\d+[.,]\d+)(?:€|euros)(?:brutos)?poraccion")
RES_TABLA = "fechadepagorecorddateex-date"
RE_RES_FILA = re.compile(_F + _F + _F)
_MESR = "(" + "|".join(sorted(MESES, key=len, reverse=True)) + ")"
TRIMESTRE = {"primer": "primer", "segundo": "segundo", "tercer": "tercer", "cuarto": "cuarto"}
RE_POL_PROPUESTO = re.compile(
    r"proponeralajuntageneraldeaccionistasladistribuciondeundividendo(?:bruto)?complementariodelejercicio(?P<ej>20\d\d)"
    r"de[\d.,]+millonesdeeuros\((?P<imp>\d+,\d+)eurosporaccion\),quesepagaraenel(?P<tri>primer|segundo|tercer|cuarto)"
    r"trimestredelanonatural(?P<a>20\d\d)")
RE_POL_CUENTA = re.compile(
    r"(?:aproboel(?P<ad>\d{1,2})de(?P<am>" + _MESR[1:-1] + r")de(?P<aa>20\d\d),?)?ladistribuciondeundividendo(?:bruto)?"
    r"acuentadelejercicio(?P<ej>20\d\d),quese(?:desembolso|abono)el(?P<d>\d{1,2})de(?P<m>" + _MESR[1:-1] + r")(?:de(?P<a>20\d\d))?"
    r"y(?:alcanzo|ascendio)a[\d.,]+millonesdeeuros\((?P<imp>\d+,\d+)(?:€|euros)poraccion\)")
RE_POL_COMPLEMENTARIO = re.compile(
    r"lajuntageneraldeaccionistascelebradael(?:pasado)?\d{1,2}de(?:" + _MESR[1:-1] + r")(?:de20\d\d)?,aproboladistribucion"
    r"deundividendocomplementariodelejercicio(?P<ej>20\d\d)de[\d.,]+millonesdeeuros\((?P<imp>\d+,\d+)eurosporaccion\)\."
    r"estedividendoestacompuestoporundividendocomplementariode(?P<c>\d+,\d+)eurosporaccionmasundividendoextraordinario"
    r"de(?P<x>\d+,\d+)eurosporaccion[.,]ambos(?:quesepagaranconjuntamenteelproximo|desembolsadoselpasado)"
    r"(?P<d>\d{1,2})de(?P<m>" + _MESR[1:-1] + r")de(?P<a>20\d\d)")
RE_EF_VERBO = re.compile(
    r"(?:pago|pagara)(?:enefectivo)?(?:su|un)(?:primer|segundo)?dividendo(?P<tipo>final|acuenta)de(?P<ej>20\d\d)"
    r"de(?P<imp>\d+,\d+)€(?:/accion|poraccion)(?:enefectivo)?el(?P<d>\d{1,2})de(?P<m>" + _MESR[1:-1] + r")de(?P<a>20\d\d)")
RE_EF_PASIVA = re.compile(
    r"eldividendo(?P<tipo>final|acuenta)denaturgypara(?P<ej>20\d\d)de(?P<imp>\d+,\d+)€(?:/accion|poraccion)"
    r"sepagoenefectivoel(?P<d>\d{1,2})de(?P<m>" + _MESR[1:-1] + r")de(?P<a>20\d\d)")
RE_EF_PROPUESTO = re.compile(
    r"undividendo(?P<tipo>final|acuenta|complementario)para(?P<ej>20\d\d)de(?P<imp>\d+,\d+)€(?:/accion|poraccion),"
    r"sujetoaaprobacionporlajga,apagaren(?P<m>" + _MESR[1:-1] + r")de(?P<a>20\d\d)")
CONCEPTO_EF = {"final": "final", "acuenta": "a cuenta", "complementario": "complementario"}


def _fecha_res(d: str, mes: str, a: str) -> date | None:
    try:
        return date(int(a), MESES[mes], int(d))
    except (ValueError, KeyError):
        return None


def extraer_resultados(texto_pdf: str, fecha_com: date, formato: str = "pagos") -> list[dict]:
    """Pagos de dividendo anunciados en una nota de resultados con el formato revisado. Lista vacía si no cuadra."""
    if formato == "politica":
        return _extraer_politica(texto_pdf, fecha_com)
    if formato == "efectivo":
        return _extraer_efectivo(texto_pdf, fecha_com)
    if formato != "pagos":
        return []
    t = re.sub(r"\s+", "", _norm(texto_pdf))
    # La nota puede repetir el párrafo (resumen de la primera página y apartado «Dividendos»): todas las repeticiones
    # tienen que decir lo mismo, y la tabla de fechas puede ir detrás de cualquiera de ellas.
    pagos, total, filas = None, None, {}
    for ancla in RE_RES_ANCLA.finditer(t):
        totales = list(RE_RES_TOTAL.finditer(t[max(0, ancla.start() - 400):ancla.start()]))
        if not totales:
            return []
        este_total = float(totales[-1].group(1).replace(",", "."))
        cola = t[ancla.end():ancla.end() + 700]
        estos = []
        # tantos pagos como anuncia la frase («en dos pagos»): los siguientes ya son de otra repetición del párrafo
        coincidencias = list(RE_RES_PAGO.finditer(cola))[:NUM_PAGOS[ancla.group(1)]]
        if len(coincidencias) != NUM_PAGOS[ancla.group(1)]:
            return []
        for m in coincidencias:
            f = _fecha_res(m.group(1), m.group(2), m.group(3))
            if f is None or not (fecha_com < f <= date(fecha_com.year + 2, 12, 31)):
                return []
            resto = re.split(r"(?<![a-z])el\d|\.(?!\d)|\)", cola[m.end():m.end() + 120])[0]   # hasta el fin de la frase o del paréntesis
            extra, ordi = "extraordinario" in resto, "ordinario" in resto.replace("extraordinario", "")
            concepto = "ordinario y extraordinario" if extra and ordi else "extraordinario" if extra else "ordinario" if ordi else ""
            estos.append({"fecha_pago": f, "importe_bruto": round(float(m.group(4).replace(",", ".")), 8), "concepto": concepto})
        if (pagos is not None and (estos != pagos or este_total != total)) or len(estos) < 2 \
                or len({p["fecha_pago"] for p in estos}) != len(estos) or abs(sum(p["importe_bruto"] for p in estos) - este_total) > 5e-4:
            return []
        pagos, total = estos, este_total
        i = t.find(RES_TABLA, ancla.end())
        if 0 <= i - ancla.end() < 1500:
            resto = t[i + len(RES_TABLA):]
            while True:
                m = RE_RES_FILA.match(resto)
                if not m:
                    break
                pago, registro, ex = (_fecha_res(*m.groups()[k:k + 3]) for k in (0, 3, 6))
                if pago and registro and ex and ex <= registro <= pago:
                    if filas.get(pago, (ex, registro)) != (ex, registro):
                        return []
                    filas[pago] = (ex, registro)
                resto = resto[m.end():]
    if not pagos:
        return []
    out = []
    for n, p in enumerate(sorted(pagos, key=lambda x: x["fecha_pago"]), 1):
        ex, registro = filas.get(p["fecha_pago"], (None, None))
        out.append({**p, "pago": n, "moneda": "EUR", "fecha_ex": ex, "fecha_registro": registro, "dividendo_anunciado": total,
                    "extraccion": "completa" if ex else "parcial"})
    return out


def _num(x: str) -> float:
    return round(float(x.replace(",", ".")), 8)


def _pago_valido(f: date | None, fecha_com: date) -> bool:
    """Un pago que la nota cuenta (hasta 400 días antes) o anuncia (hasta el final del segundo año siguiente)."""
    return f is not None and fecha_com - timedelta(days=400) <= f <= date(fecha_com.year + 2, 12, 31)


def _fila_res(concepto: str, importe: float, fecha_pago: date | None, ejercicio: str, extraccion: str) -> dict:
    return {"concepto": concepto, "importe_bruto": importe, "moneda": "EUR", "fecha_ex": None, "fecha_registro": None,
            "fecha_pago": fecha_pago, "dividendo_anunciado": importe, "extraccion": extraccion, "ejercicio": ejercicio}


def _numerar(filas: list[dict]) -> list[dict]:
    """Un dividendo una vez por nota (la nota puede repetir la frase); fechados primero, por fecha; numerados."""
    vistos, out = set(), []
    for f in filas:
        clave = (f["fecha_pago"], f["concepto"], f["importe_bruto"], f["ejercicio"])
        if clave not in vistos:
            vistos.add(clave)
            out.append(f)
    out.sort(key=lambda f: (f["fecha_pago"] is None, f["fecha_pago"] or date.max))
    return [{**f, "pago": n} for n, f in enumerate(out, 1)]


def _extraer_politica(texto_pdf: str, fecha_com: date) -> list[dict]:
    """Formato «politica» (Logista): ver el comentario del bloque."""
    t = re.sub(r"\s+", "", _norm(texto_pdf))
    filas = []
    for m in RE_POL_PROPUESTO.finditer(t):
        a = int(m["a"])
        if not (int(m["ej"]) <= a <= int(m["ej"]) + 1 and fecha_com.year <= a <= fecha_com.year + 2):
            continue
        filas.append(_fila_res("complementario", _num(m["imp"]), None, m["ej"],
                               f"anunciado: pago previsto en el {m['tri']} trimestre de {a}"))
    for m in RE_POL_CUENTA.finditer(t):
        aprob = _fecha_res(m["ad"], m["am"], m["aa"]) if m["ad"] else None
        if m["a"]:
            f = _fecha_res(m["d"], m["m"], m["a"])
        else:
            ano = aprob.year if aprob else int(m["ej"])
            f = _fecha_res(m["d"], m["m"], str(ano))
            if f and aprob and f < aprob:
                f = _fecha_res(m["d"], m["m"], str(ano + 1))
        if not _pago_valido(f, fecha_com) or (aprob and not (aprob <= f <= aprob + timedelta(days=183))):
            continue
        filas.append(_fila_res("a cuenta", _num(m["imp"]), f, m["ej"], "solo pago"))
    for m in RE_POL_COMPLEMENTARIO.finditer(t):
        f = _fecha_res(m["d"], m["m"], m["a"])
        total, partes = _num(m["imp"]), _num(m["c"]) + _num(m["x"])
        if not _pago_valido(f, fecha_com) or abs(total - partes) > 5e-4:
            continue
        filas.append(_fila_res("complementario y extraordinario", total, f, m["ej"], "solo pago"))
    return _numerar(filas)


def _extraer_efectivo(texto_pdf: str, fecha_com: date) -> list[dict]:
    """Formato «efectivo» (Naturgy): ver el comentario del bloque."""
    t = re.sub(r"\s+", "", _norm(texto_pdf))
    filas = []
    for m in list(RE_EF_VERBO.finditer(t)) + list(RE_EF_PASIVA.finditer(t)):
        f = _fecha_res(m["d"], m["m"], m["a"])
        if _pago_valido(f, fecha_com):
            filas.append(_fila_res(CONCEPTO_EF[m["tipo"]], _num(m["imp"]), f, m["ej"], "solo pago"))
    for m in RE_EF_PROPUESTO.finditer(t):
        a = int(m["a"])
        if fecha_com.year <= a <= fecha_com.year + 2:
            filas.append(_fila_res(CONCEPTO_EF[m["tipo"]], _num(m["imp"]), None, m["ej"],
                                   f"anunciado: pago previsto en {m['m']} de {a}"))
    return _numerar(filas)


def _familia(concepto: str) -> str:
    return "complementario" if concepto.split(" ")[0] in ("complementario", "final") else concepto


def lista_en_resultados(ruta: Path = EN_RESULTADOS) -> dict[str, dict]:
    if not ruta.exists():
        return {}
    return {r["isin"].strip(): r for r in csv.DictReader(ruta.open(encoding="utf-8")) if r.get("isin", "").strip()}


def _sin_texto(marca: Path) -> tuple[date | None, int]:
    """Fecha del último intento fallido y número de intentos de una nota, de su marca «.sin-texto» en la caché."""
    try:
        f, n = marca.read_text(encoding="utf-8").split()
        return date.fromisoformat(f), int(n)
    except (OSError, ValueError):
        return None, 0


def actualizar_resultados(datos: Path = DATOS, limite: int = LIMITE, texto_de=None, lista: dict | None = None,
                          cache: Path | None = None, hoy: date | None = None) -> dict:
    """Relee las notas de resultados de las empresas de la lista cerrada y reescribe datos/dividendos_resultados.csv si
    cambia. Los textos salen de la caché; solo se descargan los comunicados nuevos (hasta `limite` por pasada).

    Cola de descargas (25/11/2026): primero las notas que nunca se han pedido, de la más antigua a la más reciente;
    después, las que se pidieron y no dieron texto, una vez al día y hasta MAX_INTENTOS (cada fallo deja en la caché
    `<canal>-<nreg>.sin-texto` con la fecha y los intentos). Antes, una nota sin documento se volvía a pedir la primera
    en cada pasada: cinco a la cabeza de la cola gastaban el límite y ninguna otra se leía."""
    lista = lista_en_resultados() if lista is None else lista
    cache = CACHE if cache is None else cache
    hoy = date.today() if hoy is None else hoy
    clasif, salida = datos / "ibex35.csv", datos / "dividendos_resultados.csv"
    if not clasif.exists():
        return {"pagos": 0, "pendientes": 0, "sin_texto": 0}
    com = pd.read_csv(clasif, dtype=str, keep_default_na=False)
    com = com[(com["caja"] == "resultados") & (com["etiqueta"] == "Resultados") & com["isin"].isin(list(lista))]
    com = com[com["texto"].map(lambda x: not RE_PERIODICA.search(_norm(x))).astype(bool)]
    com = com.sort_values(["fecha", "canal", "nreg"])
    if texto_de is None:
        sesion = requests.Session()
        texto_de = lambda canal, nreg, enlace: texto_comunicado(sesion, canal, int(nreg), enlace)  # noqa: E731

    # 1. qué se descarga en esta pasada
    nunca, fallidas, sin_texto = [], [], []
    for _, c in com.iterrows():
        if (cache / f"{c['canal']}-{c['nreg']}.txt").exists():
            continue
        ultimo, intentos = _sin_texto(cache / f"{c['canal']}-{c['nreg']}.sin-texto")
        if intentos >= MAX_INTENTOS:
            sin_texto.append(f"{c['canal']} {c['nreg']}")
        elif intentos == 0:
            nunca.append(c)
        elif ultimo is None or ultimo < hoy:
            fallidas.append(c)
    cola = nunca + fallidas
    pedir, pendientes = cola[:limite], max(len(cola) - limite, 0)
    textos = {}
    for c in pedir:
        texto = texto_de(c["canal"], c["nreg"], c["enlace"])
        marca = cache / f"{c['canal']}-{c['nreg']}.sin-texto"
        if texto:
            textos[(c["canal"], c["nreg"])] = texto
            marca.unlink(missing_ok=True)
        elif not (cache / f"{c['canal']}-{c['nreg']}.txt").exists():
            intentos = _sin_texto(marca)[1] + 1
            cache.mkdir(parents=True, exist_ok=True)
            marca.write_text(f"{hoy.isoformat()} {intentos}\n", encoding="utf-8")

    # 2. las filas, en orden de fecha, de todas las notas con texto (recién descargado o de la caché)
    filas, vistos, ejercicios = [], set(), []
    for _, c in com.iterrows():
        texto = textos.get((c["canal"], c["nreg"]))
        if texto is None and (cache / f"{c['canal']}-{c['nreg']}.txt").exists():
            texto = texto_de(c["canal"], c["nreg"], c["enlace"])
        if not texto:
            continue
        for p in extraer_resultados(texto, date.fromisoformat(c["fecha"][:10]), lista[c["isin"]].get("formato", "pagos")):
            # el mismo pago, ya leído de un comunicado anterior (la nota antes que la presentación); un dividendo
            # propuesto sin fecha, por su ejercicio y su tipo
            clave = (c["isin"], p["fecha_pago"] or ("propuesto", p.get("ejercicio"), _familia(p["concepto"])))
            if clave in vistos:
                continue
            vistos.add(clave)
            ejercicios.append((c["isin"], p.get("ejercicio"), _familia(p["concepto"]), p["fecha_pago"] is None))
            filas.append({"canal": c["canal"], "nreg": c["nreg"], "pago": str(p["pago"]), "fecha_comunicado": c["fecha"][:10],
                          "isin": c["isin"], "empresa": c["empresa"], "concepto": p["concepto"],
                          "importe_bruto": str(p["importe_bruto"]), "moneda": p["moneda"],
                          **{k: (p[k].isoformat() if p[k] else "") for k in ("fecha_ex", "fecha_registro", "fecha_pago")},
                          "extraccion": p["extraccion"], "dividendo_anunciado": str(p["dividendo_anunciado"]),
                          "enlace": c["enlace"], "lector": LECTOR})
    # Un dividendo propuesto sin fecha sobra si otra nota da la fecha del mismo (misma empresa, ejercicio y tipo).
    fechados = {(i, e, fam) for i, e, fam, sin_fecha in ejercicios if not sin_fecha and e}
    filas = [f for f, (i, e, fam, sin_fecha) in zip(filas, ejercicios) if not (sin_fecha and (i, e, fam) in fechados)]
    nuevo = pd.DataFrame(filas, columns=COLUMNAS_RES)
    previo = pd.read_csv(salida, dtype=str, keep_default_na=False) if salida.exists() else None
    if previo is None or list(previo.columns) != COLUMNAS_RES or not previo.equals(nuevo):
        datos.mkdir(parents=True, exist_ok=True)
        tmp = salida.with_suffix(".csv.tmp")
        nuevo.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
        tmp.replace(salida)
    if pendientes:
        print(f"Dividendos anunciados en resultados: {pendientes} notas pendientes de descargar en la pasada siguiente.")
    if sin_texto:
        print(f"Dividendos anunciados en resultados: {len(sin_texto)} notas sin texto tras {MAX_INTENTOS} intentos, "
              f"no se vuelven a pedir: {', '.join(sin_texto)}.")
    return {"pagos": len(filas), "pendientes": pendientes, "sin_texto": len(sin_texto)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todos", action="store_true", help="vuelve a leer también los ya guardados")
    ap.add_argument("--limite", type=int, default=LIMITE)
    a = ap.parse_args()
    actualizar(limite=a.limite, todos=a.todos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
