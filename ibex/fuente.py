"""Cierres diarios del IBEX 35 desde la API pública de BME (la que usa su propia web)."""
from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/HistoricalIndicesPrices"
ISIN_IBEX35 = "ES0SI0000005"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)",
             "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}


def _tramo(desde: str, hasta: str) -> list[dict]:
    ultimo_error = None
    for intento in range(4):
        try:
            r = requests.get(API, params={"pageSize": 0, "page": 0, "ISIN": ISIN_IBEX35, "from": desde, "to": hasta, "type": "V"},
                             headers=CABECERAS, timeout=90)
            if r.status_code == 200:
                j = r.json()
                if j.get("hasMoreResults"):
                    raise RuntimeError(f"la API pagina el tramo {desde}-{hasta}")
                return j.get("data", [])
            ultimo_error = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo_error = str(e)
        time.sleep(15 * (intento + 1))
    raise RuntimeError(f"No se pudo descargar {desde}-{hasta}: {ultimo_error}")


def descargar() -> pd.DataFrame:
    filas = []
    hoy = date.today()
    for a in range(1989, hoy.year + 1, 5):
        filas += _tramo(f"{a}0101", f"{min(a + 4, hoy.year)}1231")
    df = pd.DataFrame(filas)
    if df.empty or not {"date", "close"} <= set(df.columns):
        raise RuntimeError(f"Respuesta inesperada de BME: columnas {list(df.columns)}")
    df["fecha"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df["cierre"] = pd.to_numeric(df["close"], errors="coerce").round(2)
    df["maximo"] = pd.to_numeric(df.get("high"), errors="coerce").where(lambda x: x > 0).round(2)
    return df[["fecha", "cierre", "maximo"]]
