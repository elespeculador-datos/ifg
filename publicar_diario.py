# -*- coding: utf-8 -*-
"""
Publicación diaria del Índice de Fricción Global.

Lo ejecuta GitHub Actions cada día hábil. Recalcula la serie completa,
escribe el valor del día en docs/ifg.json y añade la fila a
docs/ifg_serie.csv. GitHub Pages sirve esa carpeta, así que el JSON queda
en una URL pública que Make puede leer.

POR QUÉ RECALCULA TODO CADA DÍA en vez de añadir solo la fila nueva: los
z-scores necesitan la ventana de 750 sesiones y la escala necesita la sigma
expansiva. Recalcular cuesta dos o tres minutos y garantiza que la serie
publicada es siempre coherente consigo misma. Como no hay look-ahead, los
valores pasados no cambian al recalcular: eso ya está comprobado.

GUARDIA HORARIA: GitHub Actions solo entiende UTC, y España cambia de hora
dos veces al año. En vez de mantener dos calendarios, el flujo se dispara a
las 06:30 y a las 07:30 UTC y este script se planta salvo que en Madrid sean
las ocho y algo. Así la publicación cae a la misma hora local todo el año
sin tocar nada.

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
HORA_PUBLICACION = 8          # hora local de Madrid
ZONA = ZoneInfo("Europe/Madrid")


def toca_publicar() -> bool:
    ahora = datetime.now(ZONA)
    if ahora.weekday() >= 5:
        log.info("Fin de semana en Madrid (%s). No se publica.", ahora.date())
        return False
    if ahora.hour != HORA_PUBLICACION:
        log.info("En Madrid son las %02d:%02d. La publicación es a las %02d:30. "
                 "Esta ejecución no toca.", ahora.hour, ahora.minute,
                 HORA_PUBLICACION)
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
    linea = (f"{ultimo['generado']},{ultimo['fecha']},{ultimo['valor']},"
             f"{ultimo['tramo']},{ultimo['cobertura']}\n")
    registro = f"{DIR_PUBLICO}/registro_publicaciones.csv"
    nuevo = not os.path.exists(registro)
    with open(registro, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write("ejecutado,fecha_dato,valor,tramo,cobertura\n")
        fh.write(linea)

    log.info("Publicado: %s = %.1f (%s), motores %s",
             ultimo["fecha"], ultimo["valor"], ultimo["tramo"],
             [m["componente"] for m in ultimo["motores"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
