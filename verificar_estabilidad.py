# -*- coding: utf-8 -*-
"""
Verificación de estabilidad: la serie publicada no se revisa.

POR QUÉ EXISTE ESTE FICHERO. El requisito 2 de la metodología dice que las
reglas están congeladas y que todo cambio se anuncia. Eso implica una
propiedad más fuerte y menos visible: el valor publicado para una fecha no
puede cambiar mañana. Esa propiedad se comprobó una vez y luego se rompió al
añadir GDELT: la serie llega con muestreo semanal y se interpolaba al
calendario diario, de modo que el valor de un miércoles se calculaba
promediando la muestra del lunes anterior con la del lunes siguiente, que
aún no existía al publicar. Cuando llegaba, el valor ya publicado se movía
hasta 2 puntos. Un look-ahead silencioso, introducido al arreglar otra cosa.

Una propiedad verificada una vez no está garantizada: está garantizada
mientras algo la verifique. Por eso esto corre cada día dentro del flujo de
publicación, antes de publicar nada. Si alguna vez el pasado se mueve más de
la tolerancia, la ejecución falla con ruido en vez de revisar la serie en
silencio.

CÓMO FUNCIONA. Recalcula el índice dos veces: una con todos los datos y otra
fingiendo que hoy es una fecha anterior, recortando TODAS las fuentes a esa
fecha. Después compara las sesiones comunes anteriores al recorte. Si el
índice es honesto, deben coincidir hasta el último decimal.

Uso:
    python verificar_estabilidad.py                  # recorte por defecto
    python verificar_estabilidad.py --corte 2026-06-30
    python verificar_estabilidad.py --tolerancia 0.01
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config, fuentes, indice                       # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("estabilidad")

# Cero de verdad: no hay ninguna razón legítima para que el pasado se mueva.
# Se deja un epsilon mínimo solo por el redondeo de coma flotante.
TOLERANCIA = 0.005


def recortar(obj, hasta: pd.Timestamp):
    """Recorta un DataFrame o Serie con índice de fechas."""
    if obj is None:
        return None
    return obj[obj.index <= hasta]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corte", default=None,
                   help="fecha que se finge como 'hoy' (por defecto, hace 45 días)")
    p.add_argument("--tolerancia", type=float, default=TOLERANCIA)
    args = p.parse_args()

    # --- Datos --------------------------------------------------------------
    tickers = {**config.TICKERS, **config.CESTA_DEFENSA, **config.CESTA_FLETES}
    precios = fuentes.descargar_precios(tickers,
                                        inicio=config.FECHA_INICIO_MUESTRA,
                                        usar_cache=True)
    gpr = fuentes.descargar_gpr(usar_cache=True)
    prima = fuentes.descargar_prima_riesgo(usar_cache=True)
    gdelt = fuentes.cargar_gdelt()

    corte = (pd.Timestamp(args.corte) if args.corte
             else precios.index[-1] - pd.Timedelta(days=45))
    log.info("Fingiendo que hoy es %s", corte.date())

    # --- Los dos cálculos ---------------------------------------------------
    completo = indice.calcular(precios, gpr=gpr, prima=prima,
                               gdelt=gdelt)["tabla"]["ifg_suavizado"]
    truncado = indice.calcular(recortar(precios, corte),
                               gpr=recortar(gpr, corte),
                               prima=recortar(prima, corte),
                               gdelt=recortar(gdelt, corte))["tabla"]["ifg_suavizado"]

    com = pd.concat([truncado.rename("publicado"),
                     completo.rename("recalculado")], axis=1).dropna()
    com = com[com.index <= corte]
    if com.empty:
        log.error("No hay sesiones comunes que comparar. Revisa la fecha de corte.")
        return 1

    dif = (com["publicado"] - com["recalculado"]).abs()
    peor = dif.max()
    movidas = int((dif > args.tolerancia).sum())

    log.info("Sesiones comparadas: %d (de %s a %s)",
             len(com), com.index[0].date(), com.index[-1].date())
    log.info("Diferencia máxima: %.6f puntos", peor)

    if movidas:
        log.error("LA SERIE SE REVISA: %d sesiones cambian más de %.3f puntos.",
                  movidas, args.tolerancia)
        peores = dif.sort_values(ascending=False).head(10)
        for f, v in peores.items():
            log.error("   %s  %6.2f -> %6.2f  (%+.3f)", f.date(),
                      com.loc[f, "publicado"], com.loc[f, "recalculado"],
                      com.loc[f, "recalculado"] - com.loc[f, "publicado"])
        log.error("No se publica. Una serie que se revisa sola no es citable.")
        return 1

    log.info("ESTABLE: ninguna sesión publicada cambia al recalcular.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
