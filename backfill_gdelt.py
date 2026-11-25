# -*- coding: utf-8 -*-
"""
Backfill de GDELT: proporción diaria de eventos de conflicto material.

QUÉ MIDE. De todos los sucesos que GDELT codifica cada día a partir de la
prensa mundial, la fracción clasificada como conflicto material (QuadClass 4
en la taxonomía CAMEO: asaltos, combates, uso de fuerza). Se usa la
PROPORCIÓN y no el recuento porque el volumen bruto de GDELT crece con los
años al incorporar más fuentes: un recuento mediría el crecimiento de GDELT,
no el del conflicto.

POR QUÉ IMPORTA. Es el único componente, junto al GPR, que lee
acontecimientos en vez de cotizaciones. En la calibración de la versión 2 el
GPR salió como el mejor discriminante con diferencia. Los precios dicen que
hay tensión; solo estas dos series dicen de qué.

MUESTREO SEMANAL. El histórico completo son unos 4.900 ficheros diarios desde
abril de 2013, decenas de gigabytes y varias horas. Como esta es una capa
lenta que además se suaviza con media móvil, basta un día por semana: unos
700 ficheros, que con descargas en paralelo bajan a unos veinte minutos. Los
días intermedios se interpolan.

LÍMITE DECLARABLE. GDELT 1.0 publica ficheros diarios solo desde el 1 de
abril de 2013. Antes son mensuales y anuales con otro esquema, que este
script no trata. El componente no existe en 2010-2013 y su peso se reparte;
es una discontinuidad que debe figurar en la metodología.

Uso:
    python backfill_gdelt.py                     # muestreo semanal desde 2013
    python backfill_gdelt.py --cada 1            # todos los días (horas)
    python backfill_gdelt.py --incremental       # solo lo que falte
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

import config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("gdelt")

URL_BASE = "http://data.gdeltproject.org/events/{fecha}.export.CSV.zip"
PRIMER_DIA = date(2013, 4, 1)
COL_QUADCLASS = 29        # posición de QuadClass en el esquema de GDELT 1.0
GUARDAR_CADA = 40         # sesiones entre guardados parciales


def _localizar_quadclass(df: pd.DataFrame) -> pd.Series | None:
    """
    Devuelve la columna QuadClass, comprobando que lo es.

    No se da por buena la posición 29 sin verificar: si GDELT cambiara el
    esquema, el script seguiría calculando una proporción de algo distinto
    sin avisar, y eso contamina el índice en silencio. Se exige que los
    valores estén en {1,2,3,4} y que haya más de dos distintos, lo que
    descarta columnas binarias como IsRootEvent.
    """
    candidatas = [COL_QUADCLASS] + [c for c in df.columns if c != COL_QUADCLASS]
    for c in candidatas:
        if c not in df.columns:
            continue
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if v.empty:
            continue
        unicos = set(v.unique())
        if unicos <= {1, 2, 3, 4} and len(unicos) > 2:
            return v
    return None


def descargar_dia(d: date) -> tuple[date, float] | None:
    """Proporción de eventos de conflicto material de un día, o None."""
    url = URL_BASE.format(fecha=d.strftime("%Y%m%d"))
    try:
        resp = requests.get(url, timeout=240)
        if resp.status_code == 404:
            return None                   # hueco de GDELT, no es un error
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            with z.open(z.namelist()[0]) as fh:
                df = pd.read_csv(fh, sep="\t", header=None,
                                 on_bad_lines="skip", low_memory=False,
                                 dtype=str)
    except Exception as exc:              # noqa: BLE001
        log.debug("%s: %s", d, exc)
        return None

    q = _localizar_quadclass(df)
    if q is None or len(q) < 100:
        log.warning("%s: no se reconoce la columna QuadClass. Día omitido.", d)
        return None
    return d, float((q == 4).mean())


def dias_a_descargar(desde: date, hasta: date, cada: int,
                     ya_tengo: set[date]) -> list[date]:
    dias, d = [], max(desde, PRIMER_DIA)
    while d <= hasta:
        if d not in ya_tengo:
            dias.append(d)
        d += timedelta(days=cada)
    return dias


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--desde", default=PRIMER_DIA.isoformat())
    p.add_argument("--hasta", default=date.today().isoformat())
    p.add_argument("--cada", type=int, default=7,
                   help="días entre muestras (7 = semanal)")
    p.add_argument("--hilos", type=int, default=8)
    p.add_argument("--incremental", action="store_true")
    args = p.parse_args()

    ruta = config.RUTA_CACHE_GDELT
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)

    previo = pd.Series(dtype=float)
    if args.incremental and os.path.exists(ruta):
        previo = pd.read_parquet(ruta).iloc[:, 0]
        log.info("Caché previo: %d días hasta %s", len(previo), previo.index.max().date())

    ya = {d.date() for d in previo.index}
    pendientes = dias_a_descargar(date.fromisoformat(args.desde),
                                  date.fromisoformat(args.hasta),
                                  args.cada, ya)
    log.info("A descargar: %d ficheros (uno cada %d días, %d hilos)",
             len(pendientes), args.cada, args.hilos)

    filas, hechos, fallos = {}, 0, 0
    with ThreadPoolExecutor(max_workers=args.hilos) as pool:
        futuros = {pool.submit(descargar_dia, d): d for d in pendientes}
        for fut in as_completed(futuros):
            hechos += 1
            r = fut.result()
            if r is None:
                fallos += 1
            else:
                filas[pd.Timestamp(r[0])] = r[1]
            if hechos % GUARDAR_CADA == 0:
                parcial = pd.concat([previo, pd.Series(filas)]).sort_index()
                parcial[~parcial.index.duplicated(keep="last")] \
                    .to_frame("prop_conflicto").to_parquet(ruta)
                log.info("%d/%d procesados (%d sin dato) — guardado parcial",
                         hechos, len(pendientes), fallos)

    serie = pd.concat([previo, pd.Series(filas)]).sort_index()
    serie = serie[~serie.index.duplicated(keep="last")]
    if serie.empty:
        log.error("No se ha podido descargar nada de GDELT.")
        return 1

    serie.to_frame("prop_conflicto").to_parquet(ruta)
    log.info("Guardado %s: %d días de %s a %s (%d sin dato)",
             ruta, len(serie), serie.index.min().date(),
             serie.index.max().date(), fallos)
    log.info("Proporción media de conflicto material: %.3f  (rango %.3f-%.3f)",
             serie.mean(), serie.min(), serie.max())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
