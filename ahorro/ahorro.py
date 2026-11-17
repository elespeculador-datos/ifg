"""Rentabilidad real del ahorro: cuánto gana o pierde el dinero en el banco después de la inflación.

Indicador 4 del catálogo de Datos de El Especulador. Junta tres fuentes públicas con licencia
verificada y publica, una vez por semana:

  - tipos de interés de los depósitos de los hogares en España (BCE, estadísticas de tipos de
    interés de las IFM, conjunto MIR): a la vista (saldos vivos) y a plazo hasta un año (nuevas
    operaciones), y los mismos de la zona euro;
  - inflación: IPC general de España, variación anual (INE, API Tempus3);
  - euríbor a un año, media mensual, tal como lo publica el Banco de España en el BOE cada mes
    (Resolución «por la que se publican determinados tipos de interés oficiales de referencia del
    mercado hipotecario»), leído por la API de datos abiertos del BOE;
  - y, si la salida de letras/ está al lado, el tipo marginal de la última subasta de Letras a 12
    meses (D. G. del Tesoro y Política Financiera), como alternativa sin riesgo.

Salida en <salida>/: fragmento-wp.html (entre <!-- ahorro:inicio HUELLA --> y <!-- ahorro:fin -->),
index.html, datos/serie.csv (mensual, formato largo), datos/ultima.json y datos/euribor_boe.csv
(el euríbor acumulado mes a mes desde el BOE, que es el estado que este colector conserva).

Rentabilidad real: (1 + tipo) / (1 + inflación) - 1, con el tipo y la inflación del mismo mes.
Sin predicción ni recomendación: describe el presente frente al pasado desde 2003.

Uso:
  python ahorro/ahorro.py --salida docs/ahorro                      descarga y publica
  python ahorro/ahorro.py --salida docs/ahorro --meses-atras 36     además, rellena 36 meses de euríbor del BOE
  python ahorro/ahorro.py --salida docs/ahorro --local carpeta      usa respuestas ya descargadas (mir.csv, ipc.json, euribor.csv)
  python ahorro/ahorro.py --salida docs/ahorro --fecha 2026-11-17   fija el día (pruebas)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

VERSION = "1.0.1"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
ESPERAS = [15, 30, 60, 120]

# --- BCE, conjunto MIR (tipos de interés de las IFM). Clave: frecuencia, área, sector informante,
# partida, vencimiento, tipo de dato (R = tipo anualizado acordado), importe, sector contraparte
# (2250 = hogares), moneda, cobertura (N = nuevas operaciones, O = saldos vivos).
BCE_API = "https://data-api.ecb.europa.eu/service/data/MIR/"
BCE_PORTAL = "https://data.ecb.europa.eu/data/datasets/MIR"
SERIES_BCE = {  # nombre interno -> (área, partida, vencimiento, cobertura). Comprobado en el portal el 17/11/2026:
    # los depósitos a la vista (L21) solo existen con cobertura N; los de plazo hasta un año (L22, F) con N.
    "es_vista": ("ES", "L21", "A", "N"), "es_plazo_1a": ("ES", "L22", "F", "N"),
    "ea_vista": ("U2", "L21", "A", "N"), "ea_plazo_1a": ("U2", "L22", "F", "N"),
}
CLAVE_BCE = "M.ES+U2.B.L21+L22.A+F.R.A.2250.EUR.N"
NOMBRES = {"es_vista": "Depósitos a la vista (España)", "es_plazo_1a": "Depósitos a plazo hasta 1 año (España)",
           "ea_vista": "Depósitos a la vista (zona euro)", "ea_plazo_1a": "Depósitos a plazo hasta 1 año (zona euro)"}

# --- INE, API Tempus3. IPC general nacional, variación anual. El nombre de la serie se comprueba
# en cada pasada: si el INE renumera, el script se para en vez de publicar otra cosa.
INE_SERIE = "IPC251856"
INE_API = f"https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{INE_SERIE}"
INE_META = f"https://servicios.ine.es/wstempus/js/ES/SERIE/{INE_SERIE}"
# Si la serie se queda antigua (el INE cambia de base cada cinco años y renumera), se busca en la tabla
# de grupos especiales la serie «Índice general · Variación anual» y se avisa para actualizar el código.
INE_TABLA = "67260"
INE_TABLA_API = f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{INE_TABLA}"
INE_PORTAL = "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176802&menu=ultiDatos&idp=1254735976607"
INE_NOMBRE_DEBE = ("índice general", "variación anual")

# --- BOE, API de datos abiertos: sumario del día; la resolución mensual del Banco de España con los
# tipos oficiales de referencia del mercado hipotecario sale los primeros días de cada mes.
BOE_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/"
BOE_XML = "https://www.boe.es/diario_boe/xml.php?id="
BOE_TITULO = re.compile(r"tipos de inter[eé]s oficiales de referencia del mercado hipotecario", re.I)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

PAGINA_WP = "https://elespeculador.com/rentabilidad-real-del-ahorro/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/ahorro/"
DESDE = "2003-01"
MESES_MINIMOS = 120  # historia mínima para publicar percentil, racha y mejor/peor mes
AVISOS: list[str] = []


class DatosRaros(Exception):
    """Una fuente no responde o cambia de forma: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga común
def _get(url: str, params=None, aceptar: str = "*/*", esperas: list[int] | None = None, dormir=time.sleep,
         valido=lambda r: r.status_code == 200) -> requests.Response:
    esperas = ESPERAS if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(url, params=params, timeout=(20, 120), headers={**CABECERAS, "Accept": aceptar})
            if valido(r):
                return r
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:80]!r}"
            if r.status_code == 404:
                break  # un 404 es una respuesta, no un corte: no se reintenta
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga {url.split('/')[2]}, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar {url}: {ultimo}")


# --------------------------------------------------------------------------- BCE (depósitos)
def descargar_bce() -> str:
    r = _get(BCE_API + CLAVE_BCE, params={"format": "csvdata", "startPeriod": DESDE}, aceptar="text/csv",
             valido=lambda r: r.status_code == 200 and "TIME_PERIOD" in r.text[:3000])
    return r.text


def leer_bce(texto: str) -> pd.DataFrame:
    """CSV del portal del BCE -> DataFrame largo (mes, serie, valor). Localiza cada serie por el valor de sus claves."""
    df = pd.read_csv(io.StringIO(texto), dtype=str)
    for col in ("KEY", "TIME_PERIOD", "OBS_VALUE"):
        if col not in df.columns:
            raise DatosRaros(f"El CSV del BCE no trae la columna {col}; columnas: {list(df.columns)[:12]}")
    inverso = {v: k for k, v in SERIES_BCE.items()}

    def nombre(clave: str) -> str | None:
        p = clave.split(".")
        if len(p) < 10:
            return None
        p = p[-10:]  # por si la clave viene con el conjunto delante
        return inverso.get((p[1], p[3], p[4], p[9]))

    out = pd.DataFrame({"mes": df["TIME_PERIOD"].str.slice(0, 7), "serie": df["KEY"].map(nombre),
                        "valor": pd.to_numeric(df["OBS_VALUE"], errors="coerce")})
    out = out.dropna().drop_duplicates(["serie", "mes"], keep="last").sort_values(["serie", "mes"]).reset_index(drop=True)
    faltan = [n for n in SERIES_BCE if n not in set(out["serie"])]
    if faltan:
        raise DatosRaros(f"El BCE no ha devuelto {', '.join(faltan)}; claves recibidas: {df['KEY'].unique()[:6].tolist()}")
    if ((out["valor"] < -2) | (out["valor"] > 25)).any():
        raise DatosRaros("Tipos de depósito fuera del rango -2 % a 25 %: el conjunto ha cambiado de unidad")
    if (out["serie"] == "es_plazo_1a").sum() < 100:
        raise DatosRaros("La serie de depósitos a plazo de España trae menos de 100 meses: debería empezar en 2003")
    return out


# --------------------------------------------------------------------------- INE (inflación)
def descargar_ine(hoy: date | None = None) -> tuple[str, str]:
    """Serie configurada y, si se ha quedado antigua (más de 75 días desde su último mes), la tabla de respaldo."""
    meta = _get(INE_META, params={"det": "2"}, aceptar="application/json").text
    datos = _get(INE_API, params={"date": DESDE.replace("-", "") + "01:"}, aceptar="application/json").text
    if hoy is not None:
        try:
            ultimo = leer_ine(meta, datos)["mes"].iloc[-1]
        except DatosRaros:
            ultimo = None
        if ultimo is None or (hoy - date(int(ultimo[:4]), int(ultimo[5:7]), 28)).days > 75:
            AVISOS.append(f"La serie {INE_SERIE} del INE se queda en {ultimo}: se usa la tabla {INE_TABLA} de respaldo (actualizar INE_SERIE)")
            tabla = _get(INE_TABLA_API, params={"date": DESDE.replace("-", "") + "01:"}, aceptar="application/json").text
            return meta, serie_de_tabla(tabla)
    return meta, datos


def serie_de_tabla(texto: str) -> str:
    """De la tabla del INE, la serie «Índice general · Variación anual», devuelta como si fuera DATOS_SERIE."""
    try:
        filas = json.loads(texto)
    except json.JSONDecodeError as e:
        raise DatosRaros(f"La tabla del INE no es JSON: {e}") from None
    candidatas = [f for f in (filas if isinstance(filas, list) else []) if isinstance(f, dict)
                  and all(t in str(f.get("Nombre", "")).lower() for t in INE_NOMBRE_DEBE)]
    if not candidatas:
        raise DatosRaros(f"En la tabla {INE_TABLA} del INE no hay ninguna serie «índice general, variación anual»")
    f = candidatas[0]
    return json.dumps({"COD": f.get("COD"), "Nombre": f.get("Nombre"), "Data": f.get("Data", [])})


def leer_ine(meta: str, datos: str) -> pd.DataFrame:
    """JSON del INE -> DataFrame (mes, valor) de la variación anual del IPC general. Comprueba el nombre de la serie."""
    try:
        m = json.loads(meta)
        d = json.loads(datos)
    except json.JSONDecodeError as e:
        raise DatosRaros(f"La respuesta del INE no es JSON: {e}") from None
    nombre = str((d if isinstance(d, dict) else {}).get("Nombre") or (m if isinstance(m, dict) else {}).get("Nombre") or "")
    bajo = nombre.lower()
    if not all(t in bajo for t in INE_NOMBRE_DEBE):
        raise DatosRaros(f"La serie {INE_SERIE} del INE se llama «{nombre}»: no es el índice general en variación anual")
    filas = d.get("Data") if isinstance(d, dict) else d
    if not isinstance(filas, list) or not filas:
        raise DatosRaros("El INE no ha devuelto datos")
    out = []
    for fila in filas:
        try:
            anyo, periodo, valor = int(fila["Anyo"]), int(fila["FK_Periodo"]), float(fila["Valor"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= periodo <= 12:
            out.append((f"{anyo:04d}-{periodo:02d}", valor))
    df = pd.DataFrame(out, columns=["mes", "valor"]).drop_duplicates("mes", keep="last").sort_values("mes").reset_index(drop=True)
    if len(df) < 100:
        raise DatosRaros(f"El IPC del INE trae {len(df)} meses: demasiado pocos desde 2003")
    if ((df["valor"] < -5) | (df["valor"] > 30)).any():
        raise DatosRaros("Inflación fuera del rango -5 % a 30 %: la serie no es la variación anual")
    return df


# --------------------------------------------------------------------------- BOE (euríbor)
def _items(obj) -> list[dict]:
    """Recorre el sumario (JSON) y devuelve los elementos con identificador y título, estén donde estén."""
    out = []
    if isinstance(obj, dict):
        if "identificador" in obj and "titulo" in obj:
            out.append(obj)
        for v in obj.values():
            out.extend(_items(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_items(v))
    return out


def _items_xml(texto: str) -> list[dict]:
    out = []
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        return out
    for it in raiz.iter("item"):
        ident = it.findtext("identificador") or it.get("id")
        tit = it.findtext("titulo")
        if ident and tit:
            out.append({"identificador": ident, "titulo": tit})
    return out


def buscar_resolucion(dia: date, descargar=None) -> str | None:
    """Identificador BOE de la resolución mensual de tipos de referencia publicada ese día, o None."""
    descargar = descargar or (lambda d: _get(BOE_SUMARIO + d.strftime("%Y%m%d"), aceptar="application/json",
                                             valido=lambda r: r.status_code in (200, 404)).text)
    texto = descargar(dia)
    if not texto:
        return None
    items = []
    try:
        items = _items(json.loads(texto))
    except json.JSONDecodeError:
        items = _items_xml(texto)
    for it in items:
        if BOE_TITULO.search(str(it["titulo"])) and "banco de españa" in str(it["titulo"]).lower():
            return str(it["identificador"])
    return None


def leer_resolucion(xml_texto: str) -> dict:
    """Del XML de la resolución: euríbor a un año (media mensual) y el mes al que se refiere."""
    # Solo el cuerpo (<texto>): los metadatos llevan la fecha de la resolución, que es del mes siguiente.
    cuerpo = xml_texto.split("<texto>", 1)[1] if "<texto>" in xml_texto else xml_texto
    texto = html.unescape(re.sub(r"<[^>]+>", " | ", cuerpo))
    texto = re.sub(r"\s+", " ", texto)
    # El BOE lo publica por grupos: «1. Euríbor. Plazos:» y debajo las filas «– Una semana. | | 2,289», ...,
    # «– Un año. | | 3,247»; luego «2. Permuta de intereses...», «€STR», «Míbor». Se toma el «Un año» del grupo
    # del euríbor, es decir, antes del siguiente grupo (las celdas quedan separadas por « | »).
    m_eur = re.search(r"Eur[ií]bor", texto, re.I)
    if not m_eur:
        raise DatosRaros("No aparece el euríbor en la resolución del BOE: " + texto[:200])
    resto = texto[m_eur.end():]
    m_fin = re.search(r"\|\s*\d{1,2}\.\s|Permuta|\bIRS\b|€STR|\bSTR\b|M[ií]bor", resto, re.I)
    grupo = resto[: m_fin.start()] if m_fin else resto
    m = re.search(r"(?:un\s+a[ñn]o|1\s+a[ñn]o|12\s+meses)[^0-9|]*[\s|]*([-]?\d{1,2},\d{1,4})", grupo, re.I)
    if not m:
        raise DatosRaros("No se encuentra el plazo de un año en el grupo del euríbor de la resolución del BOE: " + grupo[:200])
    valor = float(m.group(1).replace(",", "."))
    if not -2 <= valor <= 20:
        raise DatosRaros(f"Euríbor a un año fuera de rango en el BOE: {valor}")
    # El mes al que se refiere la tabla: la última mención «mes de año» antes del dato del euríbor.
    pos_dato = m_eur.end() + m.start()
    menciones = [x for x in re.finditer(r"\b(" + "|".join(MESES) + r")\s+de\s+(\d{4})", texto, re.I) if x.start() < pos_dato]
    m_mes = menciones[-1] if menciones else re.search(r"\b(" + "|".join(MESES) + r")\s+de\s+(\d{4})", texto, re.I)
    mes = f"{int(m_mes.group(2)):04d}-{MESES.index(m_mes.group(1).lower()) + 1:02d}" if m_mes else None
    return {"mes": mes, "euribor_12m": valor}


def euribor_del_mes(mes: str, descargar_sumario=None, descargar_xml=None, hoy: date | None = None) -> dict | None:
    """Busca en los primeros doce días del mes siguiente la resolución que publica el euríbor del mes dado."""
    a, m = int(mes[:4]), int(mes[5:7])
    primero = date(a + (m == 12), 1 if m == 12 else m + 1, 1)
    descargar_xml = descargar_xml or (lambda ident: _get(BOE_XML + ident, aceptar="application/xml").text)
    for i in range(12):
        dia = primero + timedelta(days=i)
        if hoy and dia > hoy:
            return None
        if dia.weekday() == 6:
            continue  # el BOE no sale los domingos
        ident = buscar_resolucion(dia, descargar_sumario)
        if ident:
            r = leer_resolucion(descargar_xml(ident))
            # El mes es el anterior al de publicación, por construcción: la resolución de los primeros días de
            # un mes publica las medias del mes que acaba de terminar. El mes que se lee del texto solo sirve de
            # contraste (en el texto aparecen otras fechas: la de la resolución, citas de normas antiguas).
            if r["mes"] and r["mes"] != mes:
                AVISOS.append(f"La resolución {ident} menciona {r['mes']} antes del dato; se guarda como {mes}, el mes anterior a su publicación")
            return {"mes": mes, "euribor_12m": r["euribor_12m"], "boe": ident, "fecha_boe": dia.isoformat()}
    return None


def mes_de_publicacion(fecha_boe: str) -> str:
    """Mes al que corresponde una resolución publicada en `fecha_boe`: el anterior."""
    f = date.fromisoformat(fecha_boe)
    return (f.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def actualizar_euribor(ruta: Path, hoy: date, meses_atras: int = 0, **descargas) -> pd.DataFrame:
    """Lee el CSV acumulado, añade los meses que faltan (el anterior al actual y, si se pide, hacia atrás) y lo guarda."""
    cols = ["mes", "euribor_12m", "boe", "fecha_boe"]
    previo = pd.read_csv(ruta, dtype={"mes": str, "boe": str, "fecha_boe": str}).astype({"mes": str, "boe": str, "fecha_boe": str}) if ruta.exists() else pd.DataFrame(columns=cols)
    if len(previo):
        # Saneamiento: el mes de cada fila sale de su fecha de publicación (el anterior). Repara lo que
        # guardó la versión 1.0.0, que fechaba por el texto de la resolución y mezclaba meses.
        correcto = previo["fecha_boe"].map(mes_de_publicacion)
        mal = previo["mes"] != correcto
        if mal.any():
            AVISOS.append(f"{int(mal.sum())} filas del euríbor acumulado tenían el mes mal fechado y se han corregido por su fecha de publicación")
            previo["mes"] = correcto
        previo = previo.drop_duplicates("mes", keep="last")
    tengo = set(previo["mes"]) if len(previo) else set()
    ultimo_mes = (hoy.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")  # el mes anterior al actual
    # Pendientes: el mes anterior, los que se pidan hacia atrás y los huecos de los últimos 36 meses
    # (como mucho 12 descargas por pasada, para no abusar de la API del BOE).
    pendientes = [ultimo_mes]
    mes_i = ultimo_mes
    for i in range(max(meses_atras, 35)):
        mes_i = _mes_menos(mes_i, 1)
        if i < meses_atras or mes_i not in tengo:
            pendientes.append(mes_i)
    nuevos, descargados = [], 0
    for mes in pendientes:
        if mes in tengo or descargados >= 12:
            continue
        descargados += 1
        r = euribor_del_mes(mes, hoy=hoy, **descargas)
        if r:
            nuevos.append(r)
            tengo.add(r["mes"])
    if nuevos:
        previo = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True)
    previo = previo.drop_duplicates("mes", keep="last").sort_values("mes").reset_index(drop=True)
    if not len(previo):
        return pd.DataFrame(columns=cols)
    previo = previo[cols].astype({"mes": str, "euribor_12m": float, "boe": str, "fecha_boe": str})
    ruta.parent.mkdir(parents=True, exist_ok=True)
    previo.to_csv(ruta, index=False)
    return previo


# --------------------------------------------------------------------------- Letras (Tesoro)
def leer_letras(carpeta: Path | None) -> dict | None:
    if carpeta is None:
        return None
    ruta = carpeta / "letras" / "datos" / "ultima.json"
    if not ruta.exists():
        return None
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        u = (d.get("ultimas") or {}).get("12")
        if u and u.get("marginal") is not None and u.get("fecha"):
            return {"fecha": u["fecha"], "marginal": float(u["marginal"]), "fuente": d.get("fuente")}
    except (OSError, ValueError, TypeError) as e:
        AVISOS.append(f"No se ha podido leer la salida de letras: {e}")
    return None


# --------------------------------------------------------------------------- cálculos
def real(tipo: float, inflacion: float) -> float:
    """Rentabilidad real, en %: (1 + tipo) / (1 + inflación) - 1."""
    return ((1 + tipo / 100) / (1 + inflacion / 100) - 1) * 100


def percentil(serie: pd.Series, valor: float) -> float:
    s = serie.dropna()
    return float((s <= valor).mean() * 100) if len(s) else float("nan")


def racha(s: pd.Series) -> tuple[str, int]:
    """Signo del último valor y cuántos meses seguidos lleva con ese signo (cero cuenta como no positivo)."""
    s = s.dropna()
    if s.empty:
        return "—", 0
    positivo = s.iloc[-1] > 0
    n = 0
    for v in reversed(s.tolist()):
        if (v > 0) == positivo:
            n += 1
        else:
            break
    return ("positiva" if positivo else "negativa"), n


def _r(x, dec=2):
    return None if x is None or pd.isna(x) else round(float(x), dec)


def calcular(bce: pd.DataFrame, ipc: pd.DataFrame, euribor: pd.DataFrame, letras: dict | None, hoy: date) -> dict:
    tabla = bce.pivot(index="mes", columns="serie", values="valor")
    tabla = tabla.join(ipc.set_index("mes")["valor"].rename("ipc"), how="outer")
    if len(euribor):
        tabla = tabla.join(euribor.set_index("mes")["euribor_12m"].astype(float), how="outer")
    tabla = tabla.sort_index()
    tabla = tabla[tabla.index >= DESDE]
    for n in SERIES_BCE:
        tabla[f"real_{n}"] = [real(t, p) if pd.notna(t) and pd.notna(p) else float("nan") for t, p in zip(tabla[n], tabla["ipc"])]
    if "euribor_12m" in tabla:
        tabla["real_euribor_12m"] = [real(t, p) if pd.notna(t) and pd.notna(p) else float("nan") for t, p in zip(tabla["euribor_12m"], tabla["ipc"])]
    comun = tabla.dropna(subset=["es_plazo_1a", "ipc"])
    if comun.empty:
        raise DatosRaros("No hay ningún mes con depósitos a plazo e IPC a la vez")
    mes = comun.index[-1]
    f = comun.loc[mes]
    res = {"mes": mes, "mes_ipc": ipc["mes"].iloc[-1], "mes_bce": bce[bce["serie"] == "es_plazo_1a"]["mes"].iloc[-1],
           "mes_euribor": euribor["mes"].iloc[-1] if len(euribor) else None, "ipc": _r(f["ipc"]), "ipc_ultimo": _r(ipc["valor"].iloc[-1]),
           "tipos": {}, "reales": {}}
    ultimo_dia_mes = (datetime.strptime(mes, "%Y-%m").date().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    res["desfase_dias"] = (hoy - ultimo_dia_mes).days
    if res["desfase_dias"] > 75:
        AVISOS.append(f"El último mes con depósitos e IPC es {mes}: {res['desfase_dias']} días desde su fin")
    if res["desfase_dias"] > 150:
        raise DatosRaros(f"El último mes completo es {mes}: alguna fuente lleva meses sin publicar")
    for n in list(SERIES_BCE) + (["euribor_12m"] if "euribor_12m" in tabla else []):
        s = tabla[n].dropna()
        if s.empty:
            continue
        sr = tabla[f"real_{n}"].dropna()
        m_n = s.index[-1]
        ficha = {"nombre": NOMBRES.get(n, "Euríbor a un año (media mensual)"), "mes": m_n, "tipo": _r(s.iloc[-1]),
                 "variacion_12m": _r(s.iloc[-1] - s[s.index <= _mes_menos(m_n, 12)].iloc[-1]) if (s.index <= _mes_menos(m_n, 12)).any() else None}
        if len(sr):
            mr = sr.index[-1]
            ficha.update({"mes_real": mr, "real": _r(sr.iloc[-1]), "meses_con_real": int(len(sr))})
            # Percentil, racha y mejor/peor mes solo con historia suficiente (diez años): el euríbor del BOE
            # se acumula desde la primera pasada y tarda en tenerla.
            if len(sr) >= MESES_MINIMOS:
                signo, n_meses = racha(sr)
                ficha.update({"percentil_real": _r(percentil(sr, sr.iloc[-1]), 1), "racha": signo, "racha_meses": n_meses,
                              "mejor": _r(sr.max()), "mes_mejor": sr.idxmax(), "peor": _r(sr.min()), "mes_peor": sr.idxmin()})
        res["tipos"][n] = ficha
    if letras:
        res["letras_12m"] = {**letras, "real": _r(real(letras["marginal"], res["ipc_ultimo"])), "ipc_usado": res["ipc_ultimo"]}
    res["grafico"] = tabla["real_es_plazo_1a"].dropna()
    res["tabla"] = tabla
    return res


def _mes_menos(mes: str, n: int) -> str:
    a, m = int(mes[:4]), int(mes[5:7]) - n
    while m <= 0:
        a, m = a - 1, m + 12
    return f"{a:04d}-{m:02d}"


def huella(res: dict) -> str:
    base = {n: [v["mes"], v["tipo"], v.get("real")] for n, v in res["tipos"].items()}
    base["ipc"] = [res["mes_ipc"], res["ipc_ultimo"]]
    base["letras"] = [res["letras_12m"]["fecha"], res["letras_12m"]["marginal"]] if res.get("letras_12m") else None
    base["version"] = VERSION
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _mes(m: str | None) -> str:
    return "—" if not m else f"{MESES[int(m[5:7]) - 1]} de {m[:4]}"


def _f(iso: str | None) -> str:
    return "—" if not iso else pd.Timestamp(iso).strftime("%d/%m/%Y")


def _v(x, dec: int = 2) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:.{dec}f}".replace(".", ",")


def _dif(x, dec: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    if abs(x) < 0.5 * 10 ** (-dec):
        return _v(0.0, dec)
    return ("+" if x > 0 else "") + f"{x:.{dec}f}".replace(".", ",")


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_svg(s: pd.Series) -> str:
    """Rentabilidad real de los depósitos a plazo, mes a mes desde 2003, con la línea del cero."""
    s = s.dropna()
    if len(s) < 12:
        return ""
    W, H, ml, mr, mt, mb = 720, 260, 44, 12, 10, 28
    x = pd.to_datetime(s.index, format="%Y-%m")
    x0, x1 = x.min(), x.max()
    y0, y1 = min(-1.0, float(s.min()) * 1.1), max(1.0, float(s.max()) * 1.1)
    def X(t): return ml + (t - x0) / max((x1 - x0), pd.Timedelta(days=1)) * (W - ml - mr)
    def Y(v): return mt + (1 - (v - y0) / (y1 - y0)) * (H - mt - mb)
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Rentabilidad real de los depósitos a plazo en España desde 2003" xmlns="http://www.w3.org/2000/svg">',
              '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
    for i in range(5):
        v = y0 + (y1 - y0) * i / 4
        etiqueta = f"{v:.0f}".replace("-0", "0")
        partes.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                      f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{etiqueta}</text>')
    partes.append(f'<line x1="{ml}" y1="{Y(0):.1f}" x2="{W - mr}" y2="{Y(0):.1f}" stroke="#9aa5b4" stroke-dasharray="4 3"/>')
    for a in range(x0.year, x1.year + 1, 2):
        t = pd.Timestamp(year=a, month=1, day=1)
        if x0 <= t <= x1:
            partes.append(f'<text class="eje" x="{X(t):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
    puntos = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(x, s))
    partes.append(f'<polyline class="lin" stroke="#1f4e8c" points="{puntos}"/>')
    partes.append(f'<text class="eje" x="{W - mr}" y="{mt + 14}" text-anchor="end">% anual, después de la inflación</text></svg>')
    return "".join(partes)


def fragmento(res: dict, fecha_pub: str) -> str:
    p = res["tipos"]["es_plazo_1a"]
    v = res["tipos"].get("es_vista")
    partes = [f"<!-- ahorro:inicio {huella(res)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)}. Último mes con todos los datos: {_mes(res["mes"])}.</p>']
    frase = (f"<p>Un depósito a plazo de hasta un año pagaba en España el <strong>{_v(p['tipo'])} %</strong> en {_mes(p['mes'])} "
             f"(media de las nuevas operaciones de los hogares, BCE). Con la inflación de ese mes en el {_v(res['ipc'])} % (INE), "
             f"su rentabilidad real fue del <strong>{_dif(p['real'])} %</strong>")
    if p.get("racha_meses"):
        frase += f": lleva {p['racha_meses']} {'mes' if p['racha_meses'] == 1 else 'meses'} {p['racha']}"
    if p.get("percentil_real") is not None:
        frase += (f". Es el percentil {_v(p['percentil_real'], 0)} desde 2003 (ha sido igual o peor el {_v(p['percentil_real'], 0)} % de los meses). "
                  f"El mejor momento fue {_mes(p['mes_mejor'])} ({_dif(p['mejor'])} %) y el peor, {_mes(p['mes_peor'])} ({_dif(p['peor'])} %).")
    else:
        frase += "."
    if v and v.get("real") is not None:
        frase += f" El dinero en cuenta a la vista rendía el {_v(v['tipo'])} %: {_dif(v['real'])} % real."
    if res["mes_ipc"] != res["mes"]:
        frase += f" El último IPC publicado, el de {_mes(res['mes_ipc'])}, es del {_v(res['ipc_ultimo'])} %."
    partes.append(frase + "</p>")
    orden = ["es_vista", "es_plazo_1a", "euribor_12m", "ea_vista", "ea_plazo_1a"]
    partes += ["<h2>Tipo nominal, inflación y rentabilidad real</h2>",
               "<p>Rentabilidad real = (1 + tipo) ÷ (1 + inflación) − 1, con el tipo y el IPC del mismo mes. En números pequeños es, "
               "aproximadamente, el tipo menos la inflación.</p>",
               _tabla(["Referencia", "Mes", "Tipo nominal", "Un año antes", "Real", "Percentil desde 2003", "Racha"],
                      [[t["nombre"], _mes(t["mes"]), _v(t["tipo"]) + " %", _dif(t.get("variacion_12m")) if t.get("variacion_12m") is not None else "—",
                        _dif(t.get("real")) + " %" if t.get("real") is not None else "—",
                        _v(t.get("percentil_real"), 0) if t.get("percentil_real") is not None else f"— (serie de {t.get('meses_con_real', 0)} meses)",
                        f"{t['racha_meses']} meses {t['racha']}" if t.get("racha_meses") else "—"]
                       for n in orden if (t := res["tipos"].get(n))])]
    if res.get("letras_12m"):
        l = res["letras_12m"]
        partes += ["<h2>La alternativa sin riesgo: Letras del Tesoro a 12 meses</h2>",
                   f"<p>La última subasta de Letras a 12 meses ({_f(l['fecha'])}) se adjudicó a un tipo marginal del <strong>{_v(l['marginal'], 3)} %</strong>, "
                   f"según el Tesoro. Frente al último IPC ({_v(l['ipc_usado'])} %), eso sería un {_dif(l['real'])} % real si la inflación se mantuviera; "
                   f"es un cálculo ilustrativo, no una previsión. Detalles en la página de Letras del Tesoro.</p>"]
    svg = grafico_svg(res["grafico"])
    if svg:
        partes += ["<h2>Desde 2003: la rentabilidad real de los depósitos a plazo</h2>", f'<figure class="wp-block-image">{svg}</figure>']
    partes += ['<h2 id="metodo">Cómo se hace</h2>',
               "<p>Los tipos de los depósitos son los que publica el Banco Central Europeo en sus estadísticas de tipos de interés de las "
               "entidades de crédito (conjunto MIR): el tipo medio de las nuevas operaciones de depósitos a plazo de hasta un año de los hogares, "
               "y el tipo medio de los saldos en cuentas a la vista, en España y en la zona euro. La inflación es la variación anual del IPC "
               "general del INE. El euríbor a un año es la media mensual que el Banco de España publica cada mes en el BOE como tipo oficial de "
               "referencia. El Especulador no modifica esas series; calcula la rentabilidad real de cada mes, el percentil desde 2003 (porcentaje "
               "de meses con una rentabilidad real igual o inferior), la racha de meses con el mismo signo y el mejor y el peor mes, solo cuando "
               "la serie tiene al menos diez años (el euríbor se va acumulando mes a mes desde el BOE). Lectura "
               "histórica, sin predicción: describe lo que ha pasado, no lo que viene. Cada ahorrador tiene su tipo y su cesta de consumo; estas "
               "cifras son medias.</p>",
               f'<p class="has-small-font-size">Fuentes: BCE, <a href="{BCE_PORTAL}">estadísticas de tipos de interés de las IFM (MIR)</a>; '
               f'INE, <a href="{INE_PORTAL}">IPC</a> (elaboración propia con datos extraídos del sitio web del INE: www.ine.es); Banco de España '
               f"a través del BOE (basado en datos de la Agencia Estatal Boletín Oficial del Estado, www.boe.es); Tesoro Público. Las series se "
               f"reproducen sin modificar, citando la fuente; la rentabilidad real, los percentiles y las rachas son cálculos de El Especulador "
               f"(CC BY 4.0). Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>",
               "<!-- ahorro:fin -->"]
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Rentabilidad real del ahorro en España: depósitos, euríbor e inflación desde 2003 (El Especulador)",
        "description": "Tipos de los depósitos a la vista y a plazo de los hogares (BCE), inflación (INE) y euríbor a un año (Banco de España, BOE), "
                       "con la rentabilidad real de cada mes, el percentil desde 2003 y las rachas, actualizado cada semana.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos del BCE (MIR), el INE (IPC) y el BOE", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": [BCE_PORTAL, INE_PORTAL, "https://www.boe.es/"], "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(res)
    cambia = antes.get("huella") != nueva
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    tabla = res["tabla"]
    with (dd / "serie.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["mes", "serie", "valor"])
        for col in tabla.columns:
            for mes, val in tabla[col].dropna().items():
                w.writerow([mes, col, f"{val:.4g}"])
    previo.write_text(json.dumps({
        "version": VERSION, "fecha_publicacion": fecha_pub, "mes": res["mes"], "mes_ipc": res["mes_ipc"], "mes_bce": res["mes_bce"],
        "mes_euribor": res["mes_euribor"], "desfase_dias": res["desfase_dias"],
        "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "ipc": res["ipc"], "ipc_ultimo": res["ipc_ultimo"], "tipos": res["tipos"], "letras_12m": res.get("letras_12m"),
        "fuente": "BCE (MIR), INE (IPC), Banco de España a través del BOE (euríbor), Tesoro Público (letras)",
        "condiciones": "Series reproducidas sin modificar, citando la fuente; rentabilidad real, percentiles y rachas son cálculos de "
                       "El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- ahorro:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rentabilidad real del ahorro en España: depósitos, euríbor e inflación | El Especulador</title>
<meta name="description" content="Cuánto gana o pierde el dinero en el banco después de la inflación: tipos de los depósitos (BCE), IPC (INE) y euríbor (BOE), con la rentabilidad real de cada mes desde 2003.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Rentabilidad real del ahorro en España: depósitos, euríbor e inflación</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/serie.csv">series mensuales</a> · <a href="datos/ultima.json">JSON</a> · <a href="datos/euribor_boe.csv">euríbor mes a mes con su referencia del BOE</a>. Las series son del BCE, el INE y el BOE y se reutilizan sin modificar, citando la fuente; la rentabilidad real, los percentiles y las rachas son cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="carpeta con mir.csv, ipc_meta.json, ipc.json y euribor.csv ya descargados (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en UTC)")
    ap.add_argument("--meses-atras", type=int, default=0, help="meses de euríbor del BOE que se rellenan hacia atrás si faltan")
    ap.add_argument("--tesoro", help="carpeta que contiene letras/ (por defecto, la carpeta madre de --salida)")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).date()
    salida = Path(a.salida)
    ruta_euribor = salida / "datos" / "euribor_boe.csv"
    if a.local:
        loc = Path(a.local)
        bce = leer_bce((loc / "mir.csv").read_text(encoding="utf-8"))
        ipc = leer_ine((loc / "ipc_meta.json").read_text(encoding="utf-8"), (loc / "ipc.json").read_text(encoding="utf-8"))
        euribor = pd.read_csv(loc / "euribor.csv", dtype={"mes": str, "boe": str, "fecha_boe": str}) if (loc / "euribor.csv").exists() \
            else pd.DataFrame(columns=["mes", "euribor_12m", "boe", "fecha_boe"])
    else:
        bce = leer_bce(descargar_bce())
        ipc = leer_ine(*descargar_ine(hoy))
        euribor = actualizar_euribor(ruta_euribor, hoy, meses_atras=a.meses_atras)
    if not len(euribor):
        AVISOS.append("Sin euríbor del BOE todavía: el bloque del euríbor no se publica")
    letras = leer_letras(Path(a.tesoro) if a.tesoro else salida.resolve().parent)
    res = calcular(bce, ipc, euribor, letras, hoy)
    cambia = escribir(res, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    p = res["tipos"]["es_plazo_1a"]
    print(f"Depósitos a plazo {p['tipo']} % ({p['mes']}), IPC {res['ipc']} %, real {p['real']} % (percentil {p['percentil_real']}, "
          f"{p.get('racha_meses')} meses {p.get('racha')}). Euríbor BOE hasta {res['mes_euribor']}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
