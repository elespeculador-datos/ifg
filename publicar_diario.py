# -*- coding: utf-8 -*-
"""
Publicación diaria del Índice de Fricción Global.

Lo ejecuta GitHub Actions cada día hábil de madrugada. Recalcula la serie
completa, escribe el valor del día en docs/ifg.json y añade la fila a
docs/ifg_serie.csv. GitHub Pages sirve esa carpeta, así que el JSON queda
en una URL pública que Make puede leer.

POR QUÉ DE MADRUGADA Y NO A LAS 8:30. La especificación original fijaba las
8:30 CET, pero el pipeline editorial que genera "Antes de la apertura" corre
sobre las 5:00. Publicando después, el texto de cada mañana citaría siempre
el valor de la víspera. Publicar a las 3:30 además es MÁS fiel al criterio
de la propia especificación —hora de corte coherente con el cierre de Wall
Street del día anterior—, porque el índice queda fijado antes de que abra
ningún mercado europeo y no mezcla sesiones.

POR QUÉ RECALCULA TODO CADA DÍA en vez de añadir solo la fila nueva: los
z-scores necesitan la ventana de 750 sesiones y la escala necesita la sigma
expansiva. Recalcular cuesta doce minutos y garantiza que la serie publicada
es siempre coherente consigo misma. Como no hay look-ahead, los valores
pasados no cambian al recalcular: eso está comprobado.

GUARDIA HORARIA. GitHub Actions solo entiende UTC y España cambia de hora dos
veces al año, así que el flujo se dispara dos veces y este script se planta
salvo que en Madrid sea la madrugada. Se acepta una VENTANA de dos horas en
vez de una hora exacta, porque las tareas programadas de GitHub se retrasan
con frecuencia y un retraso de media hora no puede impedir la publicación
del día. Que la ventana admita las dos ejecuciones en verano no duplica
nada: la segunda encuentra la fila de hoy en el registro y se planta.

Uso:
    python publicar_diario.py            # con guardia horaria
    python publicar_diario.py --ahora    # sin guardia, para probar
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config, fuentes, indice                     # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("publicar")

DIR_PUBLICO = "docs"
REGISTRO = f"{DIR_PUBLICO}/registro_publicaciones.csv"
VENTANA_PUBLICACION = (3, 5)      # horas locales de Madrid: vale las 3 y las 4
ZONA = ZoneInfo("Europe/Madrid")


def ya_publicado_hoy() -> bool:
    """¿Hay ya una fila de hoy en el registro de publicaciones?"""
    if not os.path.exists(REGISTRO):
        return False
    hoy = datetime.now(ZONA).date().isoformat()
    try:
        with open(REGISTRO, encoding="utf-8") as fh:
            return any(linea.startswith(hoy) for linea in fh)
    except OSError:
        return False


def toca_publicar() -> bool:
    ahora = datetime.now(ZONA)
    if ahora.weekday() >= 5:
        log.info("Fin de semana en Madrid (%s). No se publica.", ahora.date())
        return False
    if not VENTANA_PUBLICACION[0] <= ahora.hour < VENTANA_PUBLICACION[1]:
        log.info("En Madrid son las %02d:%02d, fuera de la ventana de "
                 "publicación (%02d:00-%02d:00). Esta ejecución no toca.",
                 ahora.hour, ahora.minute, *VENTANA_PUBLICACION)
        return False
    if ya_publicado_hoy():
        log.info("Ya hay una publicación registrada hoy. No se repite.")
        return False
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ahora", action="store_true",
                   help="salta la guardia horaria")
    args = p.parse_args()

    if not args.ahora and not toca_publicar():
        return 0

    os.makedirs(DIR_PUBLICO, exist_ok=True)

    # --- Datos --------------------------------------------------------------
    tickers = {**config.TICKERS, **config.CESTA_DEFENSA, **config.CESTA_FLETES}
    precios = fuentes.descargar_precios(tickers,
                                        inicio=config.FECHA_INICIO_MUESTRA,
                                        usar_cache=False)
    gpr = fuentes.descargar_gpr(usar_cache=False)
    prima = fuentes.descargar_prima_riesgo(usar_cache=False)
    gdelt = fuentes.cargar_gdelt()

    # --- Cálculo ------------------------------------------------------------
    res = indice.calcular(precios, gpr=gpr, prima=prima, gdelt=gdelt)
    tabla = res["tabla"]
    if not tabla["ifg"].notna().any():
        log.error("El cálculo no ha producido ningún valor. No se publica.")
        return 1

    ultimo = indice.descomponer_dia(res)
    ultimo["licencia"] = ("CC BY 4.0. Cita: el especulador.com, Índice de "
                          f"Fricción Global, versión {config.VERSION}.")
    ultimo["aviso"] = ("Contenido informativo y educativo. No constituye "
                       "asesoramiento financiero ni recomendación de inversión.")
    ultimo["estado"] = ("preliminar: reglas congeladas, índice en validación "
                        "prospectiva, no publicado como referencia citable")
    ultimo["generado"] = datetime.now(ZONA).isoformat(timespec="seconds")

    with open(f"{DIR_PUBLICO}/ifg.json", "w", encoding="utf-8") as fh:
        json.dump(ultimo, fh, ensure_ascii=False, indent=2)

    publica = tabla[["ifg", "ifg_suavizado", "variacion", "tramo",
                     "cobertura", "parcial"]].copy()
    publica.to_csv(f"{DIR_PUBLICO}/ifg_serie.csv", float_format="%.2f")

    # Registro de ejecuciones: la prueba de que se publica sin fallos, que es
    # el requisito 5 de la sección 4, y la base de la validación prospectiva.
    # También es lo que evita publicar dos veces el mismo día.
    linea = (f"{ultimo['generado']},{ultimo['fecha']},{ultimo['valor']},"
             f"{ultimo['tramo']},{ultimo['cobertura']}\n")
    nuevo = not os.path.exists(REGISTRO)
    with open(REGISTRO, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write("ejecutado,fecha_dato,valor,tramo,cobertura\n")
        fh.write(linea)

    log.info("Publicado: %s = %.1f (%s), motores %s",
             ultimo["fecha"], ultimo["valor"], ultimo["tramo"],
             [m["componente"] for m in ultimo["motores"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
