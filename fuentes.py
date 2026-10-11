# -*- coding: utf-8 -*-
"""
Descarga de datos para el IFG.

Principio de diseño: NINGUNA fuente puede tumbar el cálculo. Toda función de
descarga devuelve o bien una serie/DataFrame válido, o bien None, y deja
constancia en el registro. El módulo `indice` reparte el peso de lo que falte.

Todo se cachea en disco para no repetir descargas durante el desarrollo.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime

import pandas as pd

import config

log = logging.getLogger("ifg.fuentes")

DIR_CACHE = "datos"


# ---------------------------------------------------------------------------
# Utilidades de caché
# ---------------------------------------------------------------------------
def _ruta_cache(nombre: str) -> str:
    os.makedirs(DIR_CACHE, exist_ok=True)
    return os.path.join(DIR_CACHE, f"{nombre}.csv")


def _leer_cache(nombre: str, dias_validez: int = 1) -> pd.DataFrame | None:
    """Devuelve el caché si existe y no ha caducado."""
    ruta = _ruta_cache(nombre)
    if not os.path.exists(ruta):
        return None
    edad = (datetime.now().timestamp() - os.path.getmtime(ruta)) / 86400
    if edad > dias_validez:
        log.info("Caché de %s caducado (%.1f días)", nombre, edad)
        return None
    df = pd.read_csv(ruta, index_col=0, parse_dates=True)
    log.info("Caché leído: %s (%d filas)", nombre, len(df))
    return df


def _escribir_cache(nombre: str, df: pd.DataFrame) -> None:
    df.to_csv(_ruta_cache(nombre))


def _parsear_fechas(col: pd.Series) -> pd.Series:
    """
    Convierte a fecha una columna que puede venir en cualquiera de los formatos
    que usan las fuentes externas.

    Sin esto, una columna de enteros tipo 20220224 se interpreta como
    nanosegundos desde 1970 y TODAS las filas acaban el 1 de enero de 1970,
    duplicadas. El fallo no avisa: el índice se calcularía con basura si el
    reventón posterior no lo parase.
    """
    s = pd.Series(col)
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce")
    if pd.api.types.is_numeric_dtype(s):
        mediana = pd.to_numeric(s, errors="coerce").dropna().median()
        if pd.notna(mediana):
            if 19000101 <= mediana <= 21001231:          # AAAAMMDD
                return pd.to_datetime(s.astype("Int64").astype(str),
                                      format="%Y%m%d", errors="coerce")
            if 1000 <= mediana <= 100000:                # número de serie de Excel
                return pd.to_datetime(s, unit="D", origin="1899-12-30",
                                      errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def _validar_serie(serie: pd.Series, nombre: str,
                   min_anio: int = 2000) -> pd.Series | None:
    """
    Descarta índices duplicados y comprueba que las fechas tienen sentido.

    Más vale desactivar un componente que alimentar el índice con fechas mal
    interpretadas: un componente ausente se ve y su peso se reparte; uno
    corrupto no se ve y contamina la serie entera.
    """
    serie = serie[serie.index.notna()]
    duplicadas = int(serie.index.duplicated().sum())
    if duplicadas:
        log.warning("%s: %d fechas duplicadas, se conserva la última",
                    nombre, duplicadas)
        serie = serie[~serie.index.duplicated(keep="last")]
    serie = serie.sort_index()
    if serie.empty:
        log.warning("%s: serie vacía tras validar. Se desactiva.", nombre)
        return None
    if serie.index.max().year < min_anio:
        log.warning("%s: la fecha más reciente es %s. Las fechas están mal "
                    "interpretadas. Se desactiva.", nombre, serie.index.max().date())
        return None
    return serie


# ---------------------------------------------------------------------------
# Yahoo Finance
# ---------------------------------------------------------------------------
def descargar_precios(tickers: dict[str, str],
                      inicio: str,
                      fin: str | None = None,
                      usar_cache: bool = True) -> pd.DataFrame:
    """
    Descarga cierres ajustados de Yahoo Finance.

    Devuelve un DataFrame con una columna por clave del diccionario `tickers`.
    Los tickers que fallen simplemente no aparecen como columna: es
    responsabilidad del módulo `indice` decidir qué hacer con la ausencia.
    """
    if usar_cache:
        cacheado = _leer_cache("precios")
        if cacheado is not None:
            faltan = set(tickers) - set(cacheado.columns)
            if not faltan:
                return cacheado

    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "Falta yfinance. Instálalo con: pip install yfinance"
        ) from exc

    series: dict[str, pd.Series] = {}
    for nombre, ticker in tickers.items():
        try:
            datos = yf.download(
                ticker, start=inicio, end=fin,
                auto_adjust=True, progress=False, threads=False,
            )
            if datos is None or datos.empty:
                log.warning("Sin datos para %s (%s)", nombre, ticker)
                continue
            # yfinance devuelve columnas MultiIndex cuando hay un solo ticker
            cierre = datos["Close"]
            if isinstance(cierre, pd.DataFrame):
                cierre = cierre.iloc[:, 0]
            cierre = cierre.dropna()
            if len(cierre) < 100:
                log.warning("Histórico insuficiente para %s: %d sesiones",
                            nombre, len(cierre))
            series[nombre] = cierre
            log.info("Descargado %-14s %-10s  %d sesiones  desde %s",
                     nombre, ticker, len(cierre), cierre.index[0].date())
        except Exception as exc:                      # noqa: BLE001
            log.warning("Fallo al descargar %s (%s): %s", nombre, ticker, exc)

    if not series:
        raise RuntimeError("No se ha podido descargar ningún precio.")

    df = pd.DataFrame(series).sort_index()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")]
    _escribir_cache("precios", df)
    return df


# ---------------------------------------------------------------------------
# GPR de Caldara & Iacoviello
# ---------------------------------------------------------------------------
def descargar_gpr(usar_cache: bool = True) -> pd.Series | None:
    """
    Índice GPR diario. Devuelve None si la fuente no está accesible.

    ATENCIÓN LEGAL: verificar en la web de los autores los términos de uso
    vigentes antes de publicar. La cita debe incluir autores y fecha de
    descarga.
    """
    if usar_cache:
        cacheado = _leer_cache("gpr", dias_validez=7)
        if cacheado is not None:
            return cacheado.iloc[:, 0]

    try:
        import requests
        resp = requests.get(config.URL_GPR, timeout=60)
        resp.raise_for_status()
        bruto = pd.read_excel(io.BytesIO(resp.content))
    except Exception as exc:                          # noqa: BLE001
        log.warning("GPR no disponible (%s). El componente se desactiva.", exc)
        return None

    # La hoja trae una columna de fecha y varias de índice. Buscamos por nombre
    # sin asumir mayúsculas ni posición exacta.
    cols = {c.lower().strip(): c for c in bruto.columns}
    col_fecha = next((cols[c] for c in cols if c in ("date", "day", "fecha")), None)
    col_valor = next((cols[c] for c in cols if c in ("gprd", "gpr", "gpr_daily")), None)
    if col_fecha is None or col_valor is None:
        log.warning("Estructura inesperada del fichero GPR: %s",
                    list(bruto.columns)[:10])
        return None

    fechas = _parsear_fechas(bruto[col_fecha])
    serie = pd.Series(pd.to_numeric(bruto[col_valor], errors="coerce").values,
                      index=fechas.dt.normalize()).dropna()
    serie.name = "gpr"
    serie = _validar_serie(serie, "GPR")
    if serie is None:
        return None
    _escribir_cache("gpr", serie.to_frame())
    log.info("GPR: %d días de %s a %s (columnas '%s' / '%s')",
             len(serie), serie.index[0].date(), serie.index[-1].date(),
             col_fecha, col_valor)
    return serie


# ---------------------------------------------------------------------------
# Prima de riesgo España-Alemania (API del BCE)
# ---------------------------------------------------------------------------
def _serie_bce(clave: str) -> pd.Series | None:
    import requests
    url = config.BCE_BASE + clave
    try:
        resp = requests.get(
            url,
            params={"format": "csvdata", "detail": "dataonly"},
            timeout=60,
        )
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as exc:                          # noqa: BLE001
        log.warning("BCE %s no disponible: %s", clave, exc)
        return None

    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        log.warning("Respuesta del BCE con formato inesperado: %s",
                    list(df.columns)[:10])
        return None
    serie = (df.assign(TIME_PERIOD=pd.to_datetime(df["TIME_PERIOD"]))
               .set_index("TIME_PERIOD")["OBS_VALUE"]
               .sort_index())
    return serie


def _prima_stooq() -> pd.Series | None:
    """
    Rendimientos de deuda a 10 años desde Stooq, que publica series de bonos
    en CSV abierto. HIPÓTESIS POR VALIDAR: los identificadores son los que usa
    Stooq para España y Alemania, pero no se han podido comprobar.
    """
    import requests
    series = {}
    for pais, ticker in (("es", config.STOOQ_BONO_ES), ("de", config.STOOQ_BONO_DE)):
        try:
            resp = requests.get("https://stooq.com/q/d/l/",
                                params={"s": ticker, "i": "d"}, timeout=60)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            if "Date" not in df.columns or "Close" not in df.columns:
                log.info("Stooq %s: respuesta sin datos utilizables.", ticker)
                return None
            series[pais] = (df.assign(Date=pd.to_datetime(df["Date"]))
                              .set_index("Date")["Close"].sort_index())
        except Exception as exc:                      # noqa: BLE001
            log.info("Stooq %s no disponible: %s", ticker, exc)
            return None
    prima = ((series["es"] - series["de"]) * 100).dropna()
    log.info("Prima de riesgo obtenida de Stooq.")
    return prima


def _prima_bce_curva() -> pd.Series | None:
    """
    Aproximación con las curvas de tipos del BCE: rendimiento a 10 años de
    todos los bonos soberanos de la zona euro menos el de los de máxima
    calificación. No es el diferencial España-Alemania, sino un diferencial de
    crédito de la zona euro en conjunto, y hay que declararlo como tal si se
    acaba usando. HIPÓTESIS POR VALIDAR.
    """
    todos = _serie_bce(config.BCE_CURVA_TODOS)
    aaa = _serie_bce(config.BCE_CURVA_AAA)
    if todos is None or aaa is None:
        return None
    prima = ((todos - aaa) * 100).dropna()
    log.info("Prima aproximada con las curvas de tipos del BCE "
             "(diferencial de la zona euro, NO España-Alemania).")
    return prima


def _prima_manual() -> pd.Series | None:
    """
    Fichero puesto a mano por el usuario: dos columnas, fecha y valor en
    puntos básicos. Vale una descarga del Banco de España o del Tesoro.
    """
    ruta = config.RUTA_PRIMA_MANUAL
    if not os.path.exists(ruta):
        return None
    try:
        df = pd.read_csv(ruta)
        serie = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                          index=_parsear_fechas(df.iloc[:, 0])).dropna()
        log.info("Prima de riesgo leída del fichero manual %s.", ruta)
        return serie
    except Exception as exc:                          # noqa: BLE001
        log.warning("No se ha podido leer %s: %s", ruta, exc)
        return None


def descargar_prima_riesgo(usar_cache: bool = True) -> pd.Series | None:
    """
    Diferencial España-Alemania a 10 años, en puntos básicos.

    Se intentan varias fuentes en orden y se registra cuál ha funcionado. Si
    ninguna responde, el componente se desactiva y su peso se reparte: es
    preferible a inventarse una aproximación silenciosa.

    Nota sobre el BCE: su portal publica la curva agregada de la zona euro a
    diario, pero el rendimiento diario del bono español a 10 años no está ahí,
    y por eso las claves del intento anterior devolvían 404. Para el dato
    exacto, la fuente natural es el Banco de España.
    """
    if usar_cache:
        cacheado = _leer_cache("prima", dias_validez=1)
        if cacheado is not None:
            return cacheado.iloc[:, 0]

    for intento in (_prima_manual, _prima_stooq, _prima_bce_curva):
        prima = intento()
        if prima is None or prima.empty:
            continue
        prima.index = pd.to_datetime(prima.index).normalize()
        prima.name = "prima"
        prima = _validar_serie(prima, "Prima de riesgo")
        if prima is None:
            continue
        _escribir_cache("prima", prima.to_frame())
        log.info("Prima de riesgo: %d días de %s a %s",
                 len(prima), prima.index[0].date(), prima.index[-1].date())
        return prima

    log.warning("Prima de riesgo no disponible por ninguna vía. "
                "El componente se desactiva y su peso se reparte.")
    return None


# ---------------------------------------------------------------------------
# GDELT
# ---------------------------------------------------------------------------
def cargar_gdelt() -> pd.Series | None:
    """
    Proporción diaria de eventos de conflicto material (QuadClass == 4).

    El backfill histórico NO se hace aquí: son ~4.500 ficheros diarios desde
    2013 y descargarlos requiere una pasada larga y unos 30-60 GB de tráfico.
    Se ejecuta una sola vez con `backfill_gdelt.py` y queda cacheado en
    parquet. Si el fichero no existe, el componente se desactiva.
    """
    ruta = config.RUTA_CACHE_GDELT
    if not os.path.exists(ruta):
        log.warning("Sin caché de GDELT en %s. El componente se desactiva.", ruta)
        return None
    try:
        df = pd.read_parquet(ruta)
    except Exception as exc:                          # noqa: BLE001
        log.warning("No se ha podido leer el caché de GDELT: %s", exc)
        return None
    serie = df.iloc[:, 0]
    serie.index = pd.to_datetime(serie.index).normalize()
    serie.name = "gdelt"
    return _validar_serie(serie, "GDELT")
