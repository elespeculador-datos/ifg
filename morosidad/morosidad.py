"""Morosidad bancaria en España: la tasa de dudosos del crédito a hogares y empresas, mes a mes y por segmentos.

Indicador 20g del catálogo de Datos de El Especulador («Morosidad y crédito»). Lee tres cuadros del Boletín
Estadístico del Banco de España (ficheros CSV públicos) y publica en <salida>/ (en el servidor,
$ESPEC_DATOS_DIR/morosidad/):

  fragmento-wp.html    frase del mes, segmentos, serie desde 1980, episodios y método, entre
                       <!-- morosidad:inicio HUELLA --> y <!-- morosidad:fin -->
  index.html           página propia de la salida
  datos/serie.csv      mensual: crédito a otros sectores residentes, créditos dudosos y ratio de dudosidad (cuadro 4.3)
  datos/segmentos.csv  trimestral desde 1998: crédito, dudosos y tasa por finalidad y rama (cuadros 4.13 y 4.18;
                       la tasa por segmento es cálculo de El Especulador)
  datos/ultima.json    resumen versionado

Fuente: Banco de España, Boletín Estadístico, cuadros 4.3, 4.13 y 4.18. Términos de uso de las estadísticas del
Banco de España y aviso legal de bde.es, leídos el 22/11/2026: uso libre y gratuito citando la fuente con la fórmula
del Banco de España, sin alterar los datos ni sus metadatos, con la fecha de actualización, sin sugerir que el Banco
de España respalda el uso y, en productos de pago, avisando de que los datos son gratuitos en bde.es.

Sin predicción ni recomendación: describe el presente frente a la historia de la serie.

Uso:
  python morosidad/morosidad.py --salida $ESPEC_DATOS_DIR/morosidad
  python morosidad/morosidad.py --salida /tmp/m --local DIR --fecha 2026-11-22   (DIR con be0403.csv, be0413.csv y be0418.csv)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

VERSION = "1.0.0"
MADRID = ZoneInfo("Europe/Madrid")
URL_CSV = "https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/{cuadro}.csv"
TERMINOS = "https://www.bde.es/wbe/es/estadisticas/recursos/terminos/terminos-de-uso.html"
NOTAS_CAP4 = "https://www.bde.es/webbe/es/estadisticas/compartido/docs/notcp4.pdf"
PAGINA_WP = "https://elespeculador.com/morosidad-bancaria-espana/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/morosidad/"
CUADROS = {"be0403": "4.3", "be0413": "4.13", "be0418": "4.18"}
CODIFICACION = "iso-8859-15"  # los CSV del Banco de España (el «€» de los títulos es el 0xA4 de esta tabla)

# Cuadro 4.3, mensual: crédito a otros sectores residentes (OSR), dudosos y ratio de dudosidad publicada.
MENSUAL = {"credito": "D_BEEA1000", "dudosos": "D_BEEA1600", "ratio": "D_BEEA2020"}
# Cuadros 4.13 y 4.18, trimestrales: (clave, nombre, grupo, cuadro, crédito, dudosos). La tasa es dudosos / crédito.
SEGMENTOS = [
    ("total", "Total por finalidades", "total", "be0413", "D_MEE60000", "D_MEADU000"),
    ("hogares", "Hogares", "hogares", "be0413", "D_MEE62000", "D_MEADU201"),
    ("vivienda", "Compra de vivienda", "hogares", "be0413", "D_MEE62100", "D_MEADU210"),
    ("consumo", "Consumo", "hogares", "be0413", "D_MEE62300", "D_MEADU226"),
    ("hogares_resto", "Otros fines", "hogares", "be0413", "D_MEE62201", "D_MEADU225"),
    ("empresas", "Empresas y empresarios individuales", "empresas", "be0418", "D_MEE61000", "D_MEADU100"),
    ("agricultura", "Agricultura, ganadería y pesca", "empresas", "be0418", "D_MEE61029", "D_MEADU101"),
    ("industria", "Industria (sin construcción)", "empresas", "be0418", "D_MEE61033", "D_MEADU102"),
    ("construccion", "Construcción", "empresas", "be0418", "D_MEE61010", "D_MEADU103"),
    ("comercio", "Comercio y reparaciones", "empresas", "be0418", "D_MEE61011", "D_MEADU105"),
    ("hosteleria", "Hostelería", "empresas", "be0418", "D_MEE61021", "D_MEADU106"),
    ("transporte", "Transporte y almacenamiento", "empresas", "be0418", "D_MEE61012", "D_MEADU107"),
    ("inmobiliarias", "Actividades inmobiliarias", "empresas", "be0418", "D_MEE61013", "D_MEADU109"),
    ("financieras", "Intermediación financiera (sin entidades de crédito)", "empresas", "be0418", "D_MEE61032", "D_MEADU108"),
    ("otros_servicios", "Otros servicios", "empresas", "be0418", "D_MEE61024", "D_MEADU110"),
]
TOTALES = {"total", "hogares", "empresas"}
# Episodios de referencia: ventanas fijadas de antemano; el valor que se publica es el que da el dato.
EPISODIOS = [
    ("Crisis bancaria de los años ochenta (máximo)", "1980-12", "1987-12", "max"),
    ("Recesión de 1993 (máximo)", "1992-01", "1996-12", "max"),
    ("Antes de la crisis financiera (mínimo)", "2004-01", "2007-12", "min"),
    ("Crisis financiera y del euro (máximo)", "2008-01", "2015-12", "max"),
]
TRAMOS = [(90, "muy alto"), (75, "alto"), (50, "por encima de lo habitual"), (25, "habitual"), (0, "bajo")]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ABREV = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
MIN_MESES_RATIO = 400       # la ratio mensual empieza en diciembre de 1980 (549 meses en agosto de 2026)
MIN_TRIMESTRES = 40         # los segmentos empiezan en diciembre de 1998 (111 trimestres en junio de 2026)
DESFASE_AVISO = {"mensual": 4, "trimestral": 7}    # meses entre el último dato y hoy
DESFASE_ERROR = {"mensual": 6, "trimestral": 10}
AVISOS: list[str] = []


class DatosRaros(Exception):
    """El Banco de España no responde o los ficheros no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- meses
def _n(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:7]) - 1


def _mes(n: int) -> str:
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def mes_largo(mes: str) -> str:
    return f"{MESES[int(mes[5:7]) - 1]} de {mes[:4]}"


def mes_corto(mes: str) -> str:
    return f"{MESES[int(mes[5:7]) - 1][:3]}. {mes[:4]}"


# --------------------------------------------------------------------------- descarga
def descargar(cuadro: str, esperas: list[int] | None = None, dormir=time.sleep) -> tuple[str, str | None]:
    """Devuelve el texto del CSV del cuadro y la fecha (Madrid) de su cabecera Last-Modified, si la trae."""
    esperas = [15, 30, 60] if esperas is None else esperas
    url = URL_CSV.format(cuadro=cuadro)
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(url, timeout=(20, 90), headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"})
            texto = r.content.decode(CODIFICACION, errors="replace")
            if r.status_code == 200 and _norm(texto[:40].lstrip('﻿"')).startswith("CODIGO DE LA SERIE"):
                return texto, _fecha_cabecera(r.headers.get("Last-Modified"))
            ultimo = f"HTTP {r.status_code}, {len(r.content)} bytes, empieza por {texto[:60]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  {cuadro}, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar el cuadro {CUADROS.get(cuadro, cuadro)} del Banco de España ({url}): {ultimo}")


def _fecha_cabecera(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return parsedate_to_datetime(valor).astimezone(MADRID).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


# --------------------------------------------------------------------------- lectura
def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x or "")
    return "".join(c for c in x if not unicodedata.combining(c)).upper().strip()


def leer_cuadro(texto: str, cuadro: str) -> dict[str, dict[str, float]]:
    """CSV del Boletín Estadístico -> {código de serie: {AAAA-MM: valor}}. Las celdas «_» son datos que no existen."""
    filas = list(csv.reader(io.StringIO(texto)))
    if len(filas) < 8 or not _norm(filas[0][0]).startswith("CODIGO DE LA SERIE"):
        raise DatosRaros(f"cuadro {CUADROS[cuadro]}: el fichero no empieza por «CÓDIGO DE LA SERIE»")
    codigos = [c.strip() for c in filas[0]]
    salida: dict[str, dict[str, float]] = {c: {} for c in codigos[1:] if c}
    for fila in filas[1:]:
        if not fila or not fila[0].strip():
            continue
        cab = _norm(fila[0])
        if cab in ("NUMERO SECUENCIAL", "ALIAS DE LA SERIE", "DESCRIPCION DE LA SERIE", "DESCRIPCION DE LAS UNIDADES",
                   "FRECUENCIA", "FUENTE", "NOTAS"):
            continue
        m = re.fullmatch(r"([A-Z]{3}) (\d{4})", cab)
        if not m or m.group(1) not in ABREV:
            raise DatosRaros(f"cuadro {CUADROS[cuadro]}: fila inesperada «{fila[0][:40]}»")
        mes = f"{int(m.group(2)):04d}-{ABREV[m.group(1)]:02d}"
        for i, codigo in enumerate(codigos[1:], 1):
            if not codigo or i >= len(fila):
                continue
            celda = fila[i].strip()
            if celda in ("", "_"):
                continue
            try:
                salida[codigo][mes] = float(celda)
            except ValueError:
                raise DatosRaros(f"cuadro {CUADROS[cuadro]}: valor no numérico «{celda[:20]}» en {codigo}, {mes}") from None
    return salida


def leer(textos: dict[str, str]) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, float]]]]:
    """Devuelve la serie mensual (credito, dudosos, ratio) y, por segmento, {"credito": {...}, "dudosos": {...}}."""
    cuadros = {c: leer_cuadro(textos[c], c) for c in CUADROS}
    m403 = cuadros["be0403"]
    faltan = [c for c in MENSUAL.values() if not m403.get(c)]
    if faltan:
        raise DatosRaros(f"cuadro 4.3: faltan las series {faltan}")
    mensual = {k: m403[c] for k, c in MENSUAL.items()}
    if len(mensual["ratio"]) < MIN_MESES_RATIO:
        raise DatosRaros(f"cuadro 4.3: la ratio de dudosidad trae {len(mensual['ratio'])} meses; se esperaban más de {MIN_MESES_RATIO}")
    # La ratio publicada es dudosos / crédito x 100 redondeada a dos decimales (comprobado en los 549 meses el 22/11/2026).
    # Si deja de serlo, el Banco de España ha cambiado la definición: parar antes que publicar otra cosa.
    ultimos = sorted(mensual["ratio"])[-36:]
    for mes in ultimos:
        cr, du = mensual["credito"].get(mes), mensual["dudosos"].get(mes)
        if not cr or du is None:
            raise DatosRaros(f"cuadro 4.3: falta el crédito o los dudosos de {mes}")
        if abs(round(du / cr * 100, 2) - mensual["ratio"][mes]) > 0.011:
            raise DatosRaros(f"cuadro 4.3: la ratio de {mes} ({mensual['ratio'][mes]}) no es dudosos / crédito ({du / cr * 100:.3f})")
    segmentos = {}
    for clave, nombre, _, cuadro, c_cred, c_dud in SEGMENTOS:
        cred, dud = cuadros[cuadro].get(c_cred), cuadros[cuadro].get(c_dud)
        if not cred or not dud:
            raise DatosRaros(f"cuadro {CUADROS[cuadro]}: faltan las series de «{nombre}» ({c_cred}, {c_dud})")
        comunes = {m for m in set(cred) & set(dud) if cred[m] > 0}
        if len(comunes) < MIN_TRIMESTRES:
            raise DatosRaros(f"cuadro {CUADROS[cuadro]}: «{nombre}» trae {len(comunes)} trimestres; se esperaban más de {MIN_TRIMESTRES}")
        if any(dud[m] > cred[m] or dud[m] < 0 for m in sorted(comunes)[-8:]):
            raise DatosRaros(f"cuadro {CUADROS[cuadro]}: «{nombre}» tiene dudosos negativos o mayores que el crédito en los últimos dos años")
        segmentos[clave] = {"credito": {m: cred[m] for m in comunes}, "dudosos": {m: dud[m] for m in comunes}}
    return mensual, segmentos


# --------------------------------------------------------------------------- cálculos
def percentil(valores: list[float], valor: float) -> float:
    """Porcentaje de observaciones menores o iguales que el valor (definición «débil»)."""
    return sum(1 for x in valores if x <= valor) / len(valores) * 100 if valores else float("nan")


def tramo(p: float) -> str:
    for umbral, nombre in TRAMOS:
        if p >= umbral:
            return nombre
    return TRAMOS[-1][1]


def periodos(serie: dict[str, float], condicion, excluir: str | None = None) -> list[list[str]]:
    """Tramos de meses seguidos de la serie que cumplen la condición, como [desde, hasta]."""
    salida: list[list[str]] = []
    for mes in sorted(serie):
        if mes == excluir or not condicion(serie[mes]):
            continue
        if salida and _n(salida[-1][1]) == _n(mes) - 1:
            salida[-1][1] = mes
        else:
            salida.append([mes, mes])
    return salida


def _variacion(serie: dict[str, float], mes: str, meses: int) -> float | None:
    antes = _mes(_n(mes) - meses)
    return None if antes not in serie else round(serie[mes] - serie[antes], 2)


def _var_pct(serie: dict[str, float], mes: str, meses: int) -> float | None:
    antes = _mes(_n(mes) - meses)
    return None if not serie.get(antes) else round((serie[mes] / serie[antes] - 1) * 100, 1)


def _desfase(mes: str, hoy: date) -> int:
    return hoy.year * 12 + hoy.month - 1 - _n(mes)


def calcular(mensual: dict, segmentos: dict, hoy: date, actualizado: dict[str, str | None] | None = None) -> dict:
    ratio = mensual["ratio"]
    meses = sorted(ratio)
    u = meses[-1]
    v = ratio[u]
    valores = [ratio[m] for m in meses]
    p = percentil(valores, v)
    previos = [m for m in meses[:-1]]
    menor = [m for m in previos if ratio[m] <= v]
    mayor = [m for m in previos if ratio[m] >= v]
    k_max = max(meses, key=lambda m: (ratio[m], m))
    k_min = min(meses, key=lambda m: (ratio[m], m))
    res = {
        "mes": u, "ratio": v, "credito": mensual["credito"][u], "dudosos": mensual["dudosos"][u],
        "var_1m": _variacion(ratio, u, 1), "var_12m": _variacion(ratio, u, 12),
        "dudosos_var_12m_pct": _var_pct(mensual["dudosos"], u, 12), "credito_var_12m_pct": _var_pct(mensual["credito"], u, 12),
        "desde": meses[0], "meses": len(meses), "percentil": round(p, 1), "tramo": tramo(p),
        "maximo": {"mes": k_max, "ratio": ratio[k_max]}, "minimo": {"mes": k_min, "ratio": ratio[k_min]},
        "ultima_vez_igual_o_menor": menor[-1] if menor else None, "ultima_vez_igual_o_mayor": mayor[-1] if mayor else None,
        "periodos_igual_o_menor": periodos(ratio, lambda x: x <= v, excluir=u),
        "episodios": [], "actualizado_bde": actualizado or {},
    }
    for nombre, desde, hasta, tipo in EPISODIOS:
        trozo = {m: ratio[m] for m in meses if desde <= m <= hasta}
        if not trozo:
            continue
        k = (max if tipo == "max" else min)(trozo, key=lambda m: (trozo[m], m))
        res["episodios"].append({"episodio": nombre, "desde": desde, "hasta": hasta, "tipo": tipo, "mes": k, "ratio": trozo[k],
                                 "diferencia_actual": round(v - trozo[k], 2)})
    # Segmentos: el último trimestre común a todos (los cuadros 4.13 y 4.18 se actualizan juntos; si no, manda el más atrasado).
    trimestre = min(max(s["credito"]) for s in segmentos.values())
    ultimos_de_cada = {max(s["credito"]) for s in segmentos.values()}
    if len(ultimos_de_cada) > 1:
        AVISOS.append(f"Los cuadros 4.13 y 4.18 no llegan al mismo trimestre ({sorted(ultimos_de_cada)}): se publica {trimestre}")
    hace_un_ano = _mes(_n(trimestre) - 12)
    filas = []
    for clave, nombre, grupo, cuadro, _, _ in SEGMENTOS:
        s = segmentos[clave]
        tasas = {m: s["dudosos"][m] / s["credito"][m] * 100 for m in s["credito"] if s["credito"][m] > 0}
        k_max = max(tasas, key=lambda m: (tasas[m], m))
        actual = tasas.get(trimestre)
        antes = tasas.get(hace_un_ano)
        filas.append({
            "segmento": clave, "nombre": nombre, "grupo": grupo, "cuadro": CUADROS[cuadro],
            "credito": s["credito"].get(trimestre), "dudosos": s["dudosos"].get(trimestre),
            "tasa": None if actual is None else round(actual, 2), "tasa_hace_un_ano": None if antes is None else round(antes, 2),
            "cambio_12m": None if actual is None or antes is None else round(round(actual, 2) - round(antes, 2), 2),
            "maximo": round(tasas[k_max], 2), "mes_maximo": k_max, "desde": min(s["credito"]),
        })
    res["segmentos"] = {"trimestre": trimestre, "hace_un_ano": hace_un_ano, "filas": filas}
    res["desfase_meses"] = {"mensual": _desfase(u, hoy), "trimestral": _desfase(trimestre, hoy)}
    for tipo, d in res["desfase_meses"].items():
        ultimo = u if tipo == "mensual" else trimestre
        if d > DESFASE_ERROR[tipo]:
            raise DatosRaros(f"el último dato {tipo} es de {ultimo}: {d} meses de desfase; comprobar el Boletín Estadístico del Banco de España")
        if d > DESFASE_AVISO[tipo]:
            AVISOS.append(f"El último dato {tipo} es de {ultimo}: {d} meses de desfase")
    res["grafico"] = {m: ratio[m] for m in meses}
    return res


def huella(mensual: dict, segmentos: dict) -> str:
    """Cambia si cambia cualquier dato publicado (también una revisión de meses antiguos) o la versión."""
    base = {"version": VERSION,
            "mensual": {k: sorted(s.items()) for k, s in mensual.items()},
            "segmentos": {k: {t: sorted(v.items()) for t, v in s.items()} for k, s in sorted(segmentos.items())}}
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return "—" if not iso else f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _p(x: float | None, dec: int = 2) -> str:
    return "—" if x is None else f"{x:.{dec}f}".replace(".", ",")


def _dif(x: float | None) -> str:
    if x is None:
        return "—"
    if abs(x) < 0.005:
        return "0,00"
    return ("+" if x > 0 else "") + f"{x:.2f}".replace(".", ",")


def _millones(miles: float | None) -> str:
    return "—" if miles is None else f"{miles / 1000:,.0f}".replace(",", ".")


def _billones(miles: float) -> str:
    return f"{miles / 1e9:.2f}".replace(".", ",")


def _comparado(d: float | None, referencia: str) -> str:
    if d is None:
        return ""
    if abs(d) < 0.005:
        return f"igual que en {referencia}"
    return f"{_p(abs(d))} puntos {'más' if d > 0 else 'menos'} que en {referencia}"


def _enumerar(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _periodo(desde: str, hasta: str) -> str:
    return f"en {mes_largo(desde)}" if desde == hasta else f"entre {mes_largo(desde)} y {mes_largo(hasta)}"


def _enlace(url: str, texto: str) -> str:
    # El aviso legal del Banco de España pide que los enlaces a bde.es se abran en otra ventana.
    return f'<a href="{url}" target="_blank" rel="noopener">{texto}</a>'


def frase(res: dict) -> str:
    u, v = res["mes"], res["ratio"]
    antes_1m, antes_12m = _mes(_n(u) - 1), _mes(_n(u) - 12)
    partes = [f"En {mes_largo(u)}, el <strong>{_p(v)} %</strong> del crédito de bancos y financieras a hogares y empresas en España "
              f"era dudoso: {_millones(res['dudosos'])} millones de euros de {_billones(res['credito'])} billones."]
    comparaciones = [c for c in (_comparado(res["var_1m"], MESES[int(antes_1m[5:]) - 1] if antes_1m[:4] == u[:4] else mes_largo(antes_1m)),
                                 _comparado(res["var_12m"], mes_largo(antes_12m))) if c]
    if comparaciones:
        partes.append("Es " + " y ".join(comparaciones) + ".")
    if res["dudosos_var_12m_pct"] is not None and res["credito_var_12m_pct"] is not None:
        d, c = res["dudosos_var_12m_pct"], res["credito_var_12m_pct"]
        partes.append(f"En un año, los créditos dudosos han {'bajado' if d < 0 else 'subido'} un {_p(abs(d), 1)} % y el crédito total "
                      f"ha {'bajado' if c < 0 else 'subido'} un {_p(abs(c), 1)} %.")
    # «La más baja desde…»: solo si hace al menos un año que no estaba tan baja (o tan alta).
    menor, mayor = res["ultima_vez_igual_o_menor"], res["ultima_vez_igual_o_mayor"]
    if menor is None:
        partes.append("Es la tasa más baja de toda la serie.")
    elif mayor is None:
        partes.append("Es la tasa más alta de toda la serie.")
    elif _n(u) - _n(menor) >= 12:
        partes.append(f"Es la tasa más baja desde {mes_largo(menor)}.")
    elif _n(u) - _n(mayor) >= 12:
        partes.append(f"Es la tasa más alta desde {mes_largo(mayor)}.")
    texto = "<p>" + " ".join(partes) + "</p>"
    hist = [f"En la serie del Banco de España, que empieza en {mes_largo(res['desde'])}, la tasa ha estado igual o más baja en el "
            f"{_p(res['percentil'], 0)} % de los meses (percentil {_p(res['percentil'], 0)}): un nivel {res['tramo']} en términos históricos."]
    pers = res["periodos_igual_o_menor"]
    if pers:
        recientes = [_periodo(a, b) for a, b in pers[-3:]]
        extra = f", además de otros {len(pers) - 3} periodos anteriores" if len(pers) > 3 else ""
        hist.append(f"Estuvo igual o por debajo {_enumerar(recientes)}{extra}.")
    hist.append(f"El máximo fue el {_p(res['maximo']['ratio'])} % de {mes_largo(res['maximo']['mes'])}, y el mínimo, "
                f"el {_p(res['minimo']['ratio'])} % de {mes_largo(res['minimo']['mes'])}.")
    texto += "\n<p>" + " ".join(hist) + "</p>"
    detalle = [f for f in res["segmentos"]["filas"] if f["segmento"] not in TOTALES and f["tasa"] is not None]
    if detalle:
        bajo = min(detalle, key=lambda f: (f["tasa"], f["nombre"]))
        alto = max(detalle, key=lambda f: (f["tasa"], f["nombre"]))
        filas = {f["segmento"]: f for f in res["segmentos"]["filas"]}
        resto = [f"en la {filas[k]['nombre'].lower()}, del {_p(filas[k]['tasa'])} %" if k == "vivienda" else
                 f"en el {filas[k]['nombre'].lower()}, del {_p(filas[k]['tasa'])} %"
                 for k in ("vivienda", "consumo") if k in filas and filas[k]["tasa"] is not None and k not in (bajo["segmento"], alto["segmento"])]
        t = (f"Por segmentos, con el último dato trimestral ({mes_largo(res['segmentos']['trimestre'])}), la tasa va del "
             f"{_p(bajo['tasa'])} % {_de(bajo['nombre'])} al {_p(alto['tasa'])} % {_de(alto['nombre'])}")
        texto += "\n<p>" + t + ("; " + " y ".join(resto) if resto else "") + ".</p>"
    return texto


def _corto(nombre: str) -> str:
    return nombre.replace(" (sin entidades de crédito)", " no bancaria")


def _de(nombre: str) -> str:
    """«Construcción» -> «de la construcción»; «Comercio y reparaciones» -> «del comercio y reparaciones»."""
    nombre = _corto(nombre)
    n = nombre[0].lower() + nombre[1:]
    primera = n.split()[0]
    if primera in ("actividades",):
        return "de las " + n
    if primera in ("otros", "otras"):
        return "de " + n
    femeninos = ("construcción", "hostelería", "industria", "intermediación", "agricultura", "compra")
    return ("de la " if primera.rstrip(",") in femeninos else "del ") + n


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_linea(serie: dict[str, float], ultimo: str) -> str:
    """Tasa mensual desde 1980 en SVG sin dependencias, en una sola línea (wpautop no la rompe)."""
    if not serie:
        return ""
    W, H, ml, mr, mt, mb = 720, 270, 38, 14, 14, 26
    meses = sorted(serie)
    x0, x1 = _n(meses[0]), _n(meses[-1])
    tope = max(serie.values())
    paso = 3 if tope <= 18 else 5
    y1 = paso * (int(tope * 1.08 // paso) + 1)
    def X(m): return ml + (_n(m) - x0) / max(x1 - x0, 1) * (W - ml - mr)
    def Y(v): return mt + (1 - v / y1) * (H - mt - mb)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Tasa de morosidad del crédito a hogares y empresas en España, '
         f'mensual desde {mes_largo(meses[0])}" xmlns="http://www.w3.org/2000/svg">',
         '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke:#1f4e8c;stroke-width:1.6}</style>']
    for v in range(0, int(y1) + 1, paso):
        p.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                 f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v} %</text>')
    for a in range(int(meses[0][:4]) + 1, int(meses[-1][:4]) + 1):
        if a % 5 == 0:
            p.append(f'<text class="eje" x="{X(f"{a}-01"):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
    p.append('<polyline class="lin" points="' + " ".join(f"{X(m):.1f},{Y(serie[m]):.1f}" for m in meses) + '"/>')
    k = max(meses, key=lambda m: (serie[m], m))
    p.append(f'<circle cx="{X(k):.1f}" cy="{Y(serie[k]):.1f}" r="3" fill="#1f4e8c"/>'
             f'<text class="eje" x="{X(k) + 6:.1f}" y="{Y(serie[k]) + 4:.1f}">{_p(serie[k])} % ({mes_corto(k)})</text>')
    p.append(f'<circle cx="{X(ultimo):.1f}" cy="{Y(serie[ultimo]):.1f}" r="3.5" fill="#e0a44c"/>'
             f'<text class="eje" x="{X(ultimo) - 6:.1f}" y="{Y(serie[ultimo]) + 16:.1f}" text-anchor="end">{_p(serie[ultimo])} % ({mes_corto(ultimo)})</text>')
    p.append("</svg>")
    return "".join(p)


def _x_etiqueta(fin_barra: float, marca: float | None) -> float:
    """La cifra va tras la barra; si la marca de un año antes cae donde iría la cifra, tras la marca."""
    if marca is not None and fin_barra - 2 <= marca <= fin_barra + 46:
        return marca + 6
    return fin_barra + 6


def grafico_barras(filas: list[dict]) -> str:
    """Tasa por segmento (barra) y la de un año antes (marca), en SVG sin dependencias."""
    filas = [f for f in filas if f["segmento"] != "total" and f["tasa"] is not None]
    if not filas:
        return ""
    W, ml, mr, fila, mt = 720, 300, 70, 22, 22
    H = mt + fila * len(filas) + 8
    tope = max(max(f["tasa"], f["tasa_hace_un_ano"] or 0) for f in filas) * 1.05
    def X(v): return ml + v / tope * (W - ml - mr)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Tasa de morosidad por segmento y la de un año antes" '
         'xmlns="http://www.w3.org/2000/svg"><style>.eje{font:11px sans-serif;fill:#5b6675}.tot{font:bold 11px sans-serif;fill:#1d2733}</style>',
         f'<rect x="{ml}" y="6" width="10" height="8" fill="#1f4e8c"/><text class="eje" x="{ml + 14}" y="14">dato actual</text>'
         f'<rect x="{ml + 100}" y="4" width="2.5" height="12" fill="#e0a44c"/><text class="eje" x="{ml + 108}" y="14">un año antes</text>']
    for i, f in enumerate(filas):
        y = mt + i * fila
        total = f["segmento"] in TOTALES
        sangria = 0 if total else 14
        nombre = _corto(f["nombre"])
        p.append(f'<text class="{"tot" if total else "eje"}" x="{sangria + 4}" y="{y + 14}">{nombre}</text>'
                 f'<rect x="{ml}" y="{y + 4}" width="{X(f["tasa"]) - ml:.1f}" height="13" fill="{"#173a69" if total else "#1f4e8c"}"/>'
                 f'<text class="eje" x="{_x_etiqueta(X(f["tasa"]), None if f["tasa_hace_un_ano"] is None else X(f["tasa_hace_un_ano"])):.1f}" '
                 f'y="{y + 14}">{_p(f["tasa"])} %</text>')
        if f["tasa_hace_un_ano"] is not None:
            p.append(f'<rect x="{X(f["tasa_hace_un_ano"]) - 1.2:.1f}" y="{y + 1}" width="2.5" height="19" fill="#e0a44c"/>')
    p.append("</svg>")
    return "".join(p)


def fragmento(res: dict, marca: str, fecha_pub: str) -> str:
    seg = res["segmentos"]
    act = res["actualizado_bde"] or {}
    fechas_bde = ""
    if act.get("be0403"):
        fechas_bde = f" Fichero del cuadro 4.3 del Banco de España actualizado el {_f(act['be0403'])}"
        otros = sorted({act[c] for c in ("be0413", "be0418") if act.get(c)})
        if otros:
            fechas_bde += f"; cuadros 4.13 y 4.18, el {_enumerar([_f(x) for x in otros])}"
        fechas_bde += "."
    partes = [f"<!-- morosidad:inicio {marca} -->",
              (f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con el dato de {mes_largo(res["mes"])}. Datos del Banco de '
               f"España, mensuales para el total y trimestrales por segmento; la página se revisa cada día hábil y cambia cuando hay un "
               f"dato nuevo.{fechas_bde}</p>"),
              frase(res)]
    filas_tabla = []
    for f in seg["filas"]:
        nombre = f"<strong>{f['nombre']}</strong>" if f["segmento"] in TOTALES else f"· {f['nombre']}"
        filas_tabla.append([nombre, f"{_p(f['tasa'])} %", f"{_p(f['tasa_hace_un_ano'])} %", _dif(f["cambio_12m"]),
                            f"{_p(f['maximo'])} % ({mes_corto(f['mes_maximo'])})", _millones(f["dudosos"]), _millones(f["credito"])])
    partes += [f"<h2>Por segmentos: hogares y empresas ({mes_largo(seg['trimestre'])})</h2>",
               ("<p>Tasa de morosidad de cada finalidad del crédito a los hogares y de cada rama de actividad de las empresas, con el último "
                f"dato trimestral, la de un año antes ({mes_largo(seg['hace_un_ano'])}) y el máximo de cada serie desde 1998. "
                "Importes en millones de euros.</p>"),
               _tabla(["Segmento", "Tasa", "Un año antes", "Cambio (puntos)", "Máximo de la serie", "Dudosos", "Crédito"], filas_tabla)]
    barras = grafico_barras(seg["filas"])
    if barras:
        partes.append(f'<figure class="wp-block-image">{barras}</figure>')
    linea = grafico_linea(res["grafico"], res["mes"])
    if linea:
        partes += [f"<h2>La serie desde {res['desde'][:4]}</h2>", f'<figure class="wp-block-image">{linea}</figure>']
    if res["episodios"]:
        partes += ["<h2>Los episodios de referencia</h2>",
                   ("<p>Máximo o mínimo de la tasa dentro de cada episodio, con su mes. Las ventanas están fijadas de antemano; "
                    "el valor es el que da el dato.</p>"),
                   _tabla(["Episodio", "Tasa", "Mes", "Dato actual frente a ese valor (puntos)"],
                          [[e["episodio"], f"{_p(e['ratio'])} %", mes_largo(e["mes"]), _dif(e["diferencia_actual"])] for e in res["episodios"]])]
    partes.append(
        '<h2 id="metodo">De dónde sale y cómo se lee</h2>'
        "<p>La tasa de morosidad es la que el Banco de España publica como ratio de dudosidad: créditos dudosos entre el crédito total de "
        "las entidades de crédito (bancos, cajas y cooperativas) y los establecimientos financieros de crédito a los «otros sectores "
        "residentes», es decir, hogares, empresas e instituciones financieras que no son entidades de crédito, residentes en España; no "
        "incluye a las administraciones públicas. Un crédito es dudoso cuando hay dudas razonables de que se devuelva entero; los morosos, "
        "con algún importe vencido hace más de tres meses, son una parte de los dudosos (" + _enlace(NOTAS_CAP4, "notas del capítulo 4 del "
        "Boletín Estadístico") + "; normativa contable del Banco de España, Circular 4/2017).</p>"
        "<p>El Especulador toma la serie mensual tal como la publica el Banco de España y calcula sobre ella el percentil histórico "
        "(porcentaje de meses desde diciembre de 1980 con una tasa igual o inferior a la actual), las variaciones en puntos, los periodos "
        "en que estuvo igual o por debajo y el máximo o mínimo de cada episodio. Los tramos («bajo», «habitual», «por encima de lo "
        "habitual», «alto», «muy alto») corresponden a los percentiles 25, 50, 75 y 90 de la serie. Las tasas por segmento las calcula "
        "El Especulador dividiendo los créditos dudosos entre el crédito de cada finalidad o rama, con los datos trimestrales de los "
        "cuadros 4.13 y 4.18; la del total por finalidades coincide con la mensual del mismo mes salvo por redondeos. «Empresas y "
        "empresarios individuales» es la financiación de actividades productivas.</p>"
        "<p>Lectura histórica, sin predicción: la tasa describe el presente frente al pasado, no lo que viene, y no dice nada de una "
        "entidad concreta.</p>"
        '<p class="has-small-font-size">Fuente: Sitio web del Banco de España (www.bde.es), Boletín Estadístico, '
        + _enlace(URL_CSV.format(cuadro="be0403"), "cuadro 4.3") + " (tasa de morosidad, créditos dudosos y crédito). Fuente: Elaboración "
        "propia con datos extraídos del sitio web del Banco de España (www.bde.es), cuadros 4.3, "
        + _enlace(URL_CSV.format(cuadro="be0413"), "4.13") + " y " + _enlace(URL_CSV.format(cuadro="be0418"), "4.18")
        + " (percentiles, variaciones, periodos, episodios y tasas por segmento). Los datos se reutilizan según los "
        + _enlace(TERMINOS, "términos de uso de las estadísticas del Banco de España") + ", que no participa en esta página ni la respalda; "
        "son gratuitos en bde.es. Los cálculos de El Especulador se publican con licencia "
        '<a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>. '
        "Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>")
    partes.append("<!-- morosidad:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Morosidad bancaria en España: tasa de dudosos del crédito a hogares y empresas (El Especulador)",
        "description": "Tasa de morosidad (ratio de dudosidad) del crédito de las entidades de crédito y establecimientos financieros de "
                       "crédito a hogares y empresas residentes en España, mensual desde 1980, con percentil histórico y episodios, y por "
                       "segmentos (vivienda, consumo y ramas de actividad), trimestral desde 1998.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "Elaboración propia con datos extraídos del sitio web del Banco de España (www.bde.es)",
        "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": URL_CSV.format(cuadro="be0403"), "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/segmentos.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


# --------------------------------------------------------------------------- escritura
def _atomico(ruta: Path, texto: str) -> None:
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def escribir(mensual: dict, segmentos: dict, res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    """Escribe los cinco ficheros si cambia la huella (o falta alguno, o se fuerza). Devuelve si cambió."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    try:
        antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    except ValueError:
        antes = {}
    nueva = huella(mensual, segmentos)
    cambia = antes.get("huella") != nueva
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv", "datos/segmentos.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    if not cambia and antes.get("actualizado_bde"):
        res["actualizado_bde"] = antes["actualizado_bde"]   # misma información, misma fecha de actualización
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["mes", "credito_miles_eur", "dudosos_miles_eur", "ratio_dudosidad_pct"])
    for mes in sorted(set(mensual["credito"]) | set(mensual["dudosos"]) | set(mensual["ratio"])):
        w.writerow([mes, _num(mensual["credito"].get(mes)), _num(mensual["dudosos"].get(mes)), _num(mensual["ratio"].get(mes))])
    _atomico(dd / "serie.csv", buf.getvalue())
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["trimestre", "segmento", "nombre", "cuadro", "credito_miles_eur", "dudosos_miles_eur", "tasa_pct_calculada"])
    for clave, nombre, _, cuadro, _, _ in SEGMENTOS:
        s = segmentos[clave]
        for mes in sorted(s["credito"]):
            w.writerow([mes, clave, nombre, CUADROS[cuadro], _num(s["credito"][mes]), _num(s["dudosos"][mes]),
                        f"{s['dudosos'][mes] / s['credito'][mes] * 100:.4f}"])
    _atomico(dd / "segmentos.csv", buf.getvalue())
    resumen = {k: v for k, v in res.items() if k != "grafico"}
    _atomico(previo, json.dumps({
        **resumen, "version": VERSION, "fecha_publicacion": fecha_pub, "huella": nueva,
        "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "Banco de España, Boletín Estadístico, cuadros 4.3, 4.13 y 4.18 (" + ", ".join(URL_CSV.format(cuadro=c) for c in CUADROS) + ")",
        "cita": {"sin_tratar": "Fuente: Sitio web del Banco de España (www.bde.es)",
                 "tratados": "Fuente: Elaboración propia con datos extraídos del sitio web del Banco de España (www.bde.es)"},
        "condiciones": "Términos de uso de las estadísticas del Banco de España: datos sin alterar, citando la fuente con su fórmula y la fecha "
                       "de actualización, sin sugerir respaldo del Banco de España; en productos de pago, avisar de que son gratuitos en bde.es. "
                       "Percentiles, variaciones, episodios y tasas por segmento son cálculos de El Especulador (CC BY 4.0). "
                       "Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1, allow_nan=False))
    frag = fragmento(res, nueva, fecha_pub)
    marca = "\n<!-- morosidad:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    _atomico(salida / "fragmento-wp.html", frag.replace(marca, "\n" + ld + marca))
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    _atomico(salida / "index.html", f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morosidad bancaria en España, mes a mes | El Especulador</title>
<meta name="description" content="Tasa de morosidad del crédito de bancos y financieras a hogares y empresas en España, mensual desde 1980, con su percentil histórico, y por segmentos: vivienda, consumo y ramas de actividad.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Morosidad bancaria en España, mes a mes</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/serie.csv">serie mensual</a> · <a href="datos/segmentos.csv">segmentos trimestrales</a> · <a href="datos/ultima.json">JSON</a>. Fuente: Elaboración propia con datos extraídos del sitio web del Banco de España (www.bde.es); los datos del Banco de España se reutilizan sin alterar y son gratuitos en bde.es; los cálculos de El Especulador, con licencia CC BY 4.0. Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""")
    return cambia


def _num(x: float | None) -> str:
    if x is None:
        return ""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="carpeta con be0403.csv, be0413.csv y be0418.csv ya descargados (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en Madrid)")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie (tras cambiar el código)")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(MADRID).date()
    textos, actualizado = {}, {}
    for cuadro in CUADROS:
        if a.local:
            ruta = Path(a.local) / f"{cuadro}.csv"
            if not ruta.exists():
                raise DatosRaros(f"falta {ruta}")
            textos[cuadro], actualizado[cuadro] = ruta.read_bytes().decode(CODIFICACION, errors="replace"), None
        else:
            textos[cuadro], actualizado[cuadro] = descargar(cuadro)
    mensual, segmentos = leer(textos)
    res = calcular(mensual, segmentos, hoy, actualizado)
    cambia = escribir(mensual, segmentos, res, hoy, Path(a.salida), forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::morosidad: {av}")
    print(f"Morosidad de {res['mes']}: {res['ratio']} % (percentil {res['percentil']}, {res['tramo']}); segmentos de "
          f"{res['segmentos']['trimestre']}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::morosidad: {e}")
        sys.exit(1)
