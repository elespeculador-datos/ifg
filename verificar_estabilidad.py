# -*- coding: utf-8 -*-
"""
Verificación de estabilidad: lo publicado no cambia.

QUÉ COMPRUEBA Y POR QUÉ ESTA VERSIÓN ES DISTINTA DE LA ANTERIOR.

La primera versión simulaba el paso del tiempo: recalculaba el índice
recortando todas las fuentes a una fecha pasada y comparaba. Servía para
cazar un look-ahead y cazó uno (la interpolación de GDELT). Pero daba por
supuesto algo falso: que el recálculo de hoy reproduce lo publicado ayer.

No lo reproduce, y no por un fallo. backfill_gdelt.py recorre todo el rango
y recupera los ficheros que en su día no estaban disponibles, así que una
ejecución puede insertar una muestra de GDELT con fecha pasada que mueve los
valores diarios desde ahí. El 12 de octubre de 2026 se vio en vivo: el valor
del viernes 9 pasó de 63,41 a 63,69 entre dos ejecuciones del mismo día. La
simulación nunca lo habría detectado, porque solo miraba más allá de 45 días.

La respuesta a eso no es una comprobación más fina, es una regla:
publicar_diario.py conserva intactas las filas ya publicadas y solo añade
fechas nuevas. Lo que este archivo verifica, entonces, es que esa regla se
cumple de verdad, y lo hace sobre el dato real en vez de sobre una
simulación: compara la serie que acaba de escribirse con la que está
confirmada en el repositorio.

TOLERANCIA CERO Y SIN UMBRALES INVENTADOS. Aquí no hay ningún número
elegido a ojo. Una fila publicada o es idéntica o no lo es. La deriva entre
el recálculo y lo publicado —que sí es un continuo— no se juzga aquí: se
mide en publicar_diario.py y se publica en docs/revisiones.csv para que
cualquiera la audite.

CUÁNDO FALLA:
  - una fecha que estaba publicada ha desaparecido de la serie;
  - una fecha que estaba publicada tiene ahora otro valor, otro tramo u
    otra variación.

Se ejecuta DESPUÉS de publicar_diario.py y ANTES del commit, de modo que si
la regla se rompe, el flujo falla con ruido y no se guarda nada.

Uso:
    python verificar_estabilidad.py
    python verificar_estabilidad.py --ref HEAD~1
"""

from __future__ import annotations

import argparse
import io
import logging
import subprocess
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("estabilidad")

RUTA_SERIE = "docs/ifg_serie.csv"

# Campos que, una vez publicados, no pueden cambiar jamás.
CAMPOS_CONGELADOS = ["ifg", "ifg_suavizado", "variacion", "tramo"]

# Cero de verdad. El epsilon es solo por el redondeo a dos decimales del CSV.
TOLERANCIA = 0.005


def serie_confirmada(ref: str) -> pd.DataFrame | None:
    """
    La serie tal y como está guardada en el repositorio, sin los cambios que
    esta ejecución acaba de escribir en el disco. Es la última publicación
    de verdad, la que ya han podido leer terceros.
    """
    try:
        salida = subprocess.run(
            ["git", "show", f"{ref}:{RUTA_SERIE}"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not salida.strip():
        return None
    return pd.read_csv(io.StringIO(salida), index_col=0, parse_dates=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ref", default="HEAD",
                   help="referencia de git con la que comparar")
    args = p.parse_args()

    antes = serie_confirmada(args.ref)
    if antes is None:
        log.info("No hay serie confirmada en %s. Primera publicación: nada "
                 "que verificar.", args.ref)
        return 0

    try:
        ahora = pd.read_csv(RUTA_SERIE, index_col=0, parse_dates=True)
    except FileNotFoundError:
        log.error("No existe %s. La publicación no ha escrito la serie.",
                  RUTA_SERIE)
        return 1

    # --- 1. Ninguna fecha publicada puede desaparecer -----------------------
    perdidas = antes.index.difference(ahora.index)
    if len(perdidas):
        log.error("HAN DESAPARECIDO %d sesiones ya publicadas. La primera es "
                  "%s.", len(perdidas), perdidas[0].date())
        log.error("No se publica. Una serie de la que se borran fechas no es "
                  "citable.")
        return 1

    # --- 2. Ninguna fecha publicada puede cambiar de valor ------------------
    comunes = antes.index.intersection(ahora.index)
    movidas = []

    for campo in CAMPOS_CONGELADOS:
        if campo not in antes.columns or campo not in ahora.columns:
            continue
        a, b = antes.loc[comunes, campo], ahora.loc[comunes, campo]
        if campo == "tramo":
            dif = a.fillna("") != b.fillna("")
        else:
            dif = (pd.to_numeric(a, errors="coerce")
                   - pd.to_numeric(b, errors="coerce")).abs() > TOLERANCIA
        for fecha in comunes[dif.fillna(False)]:
            movidas.append((fecha, campo, a.loc[fecha], b.loc[fecha]))

    if movidas:
        log.error("SE HAN MODIFICADO %d valores ya publicados:", len(movidas))
        for fecha, campo, viejo, nuevo in movidas[:15]:
            log.error("   %s  %-14s  %s -> %s", fecha.date(), campo, viejo, nuevo)
        if len(movidas) > 15:
            log.error("   ... y %d más.", len(movidas) - 15)
        log.error("No se publica. La serie publicada es inmutable: el "
                  "recálculo solo puede añadir fechas nuevas.")
        return 1

    nuevas = ahora.index.difference(antes.index)
    log.info("ESTABLE: %d sesiones publicadas siguen idénticas, %d nuevas se "
             "añaden%s.", len(comunes), len(nuevas),
             f" (desde {nuevas[0].date()})" if len(nuevas) else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
