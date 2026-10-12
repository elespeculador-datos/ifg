# -*- coding: utf-8 -*-
"""
Publicación diaria del Índice de Fricción Global.

Lo ejecuta GitHub Actions cada día hábil de madrugada. Recalcula la serie
completa y escribe en docs/, que GitHub Pages sirve como URL pública:

    ifg.json            el valor del día y sus dos motores. Lo lee Make.
    ifg_serie.csv       la serie histórica entera. Dato abierto.
    ifg_serie_12m.json  los últimos doce meses en formato compacto, para el
                        gráfico del panel de la web.
    revisiones.csv      cuánto se separa el recálculo de lo ya publicado.

POR QUÉ DE MADRUGADA Y NO A LAS 8:30. La especificación original fijaba las
8:30 CET, pero el pipeline editorial que genera "Antes de la apertura" corre
sobre las 5:00. Publicando después, el texto de cada mañana citaría siempre
el valor de la víspera. Publicar a las 3:30 además es MÁS fiel al criterio
de la propia especificación —hora de corte coherente con el cierre de Wall
Street del día anterior—, porque el índice queda fijado antes de que abra
ningún mercado europeo y no mezcla sesiones.

POR QUÉ RECALCULA TODO CADA DÍA en vez de añadir solo la fila nueva: los
z-scores necesitan la ventana de 750 sesiones y la escala necesita la sigma
expansiva.

LA SERIE PUBLICADA ES INMUTABLE. Esta es la regla que gobierna el archivo y
hay que entender por qué existe. El recálculo diario NO reproduce
exactamente lo publicado ayer, y no por un fallo: backfill_gdelt.py recorre
todo el rango y recupera los ficheros que en su día no estaban disponibles,
de modo que una ejecución puede insertar una muestra de GDELT con fecha
pasada. Como la serie semanal se arrastra hacia delante, esa muestra mueve
los valores diarios desde esa fecha. El 12 de octubre de 2026 se observó en
vivo: el valor del viernes 9 pasó de 63,41 a 63,69 entre dos ejecuciones del
mismo día.

Un índice que aspira a ser citable no puede permitirse eso. Así que el
recálculo se usa SOLO para las fechas que todavía no se han publicado; las
filas que ya están en docs/ifg_serie.csv se conservan intactas. La deriva
entre lo que saldría hoy y lo que se publicó en su día no se esconde: se
mide en cada ejecución y se escribe en docs/revisiones.csv, que es público.
Esa es la política de revisiones del índice y debe figurar en la
metodología.

LÍMITE CONOCIDO DE ESTA REGLA. El valor, la variación y el tramo quedan
congelados. El desglose por componentes que acompaña al día (los "motores"
de ifg.json y el desglose_nivel del panel) se recalcula, porque la serie de
contribuciones no se guarda. Es información descriptiva, la deriva observada
está muy por debajo de la décima, y congelarla exigiría guardar las once
contribuciones de cada sesión. Queda anotado como deuda, no como fallo
oculto.

GUARDIA HORARIA. GitHub Actions solo entiende UTC y España cambia de hora dos
veces al año, así que el flujo se dispara dos veces y este script se planta
salvo que en Madrid sea la madrugada. Se acepta una VENTANA de dos horas en
vez de una hora exacta, porque las tareas programadas de GitHub se retrasan
con frecuencia y un retraso de media hora no puede impedir la publicación
del día. Que la ventana admita las dos ejecuciones en verano no duplica
nada: la segunda encuentra la fila de hoy en el registro y se planta. Y aun
forzándola, la regla de inmutabilidad hace que no cambie ningún valor ya
publicado.

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
RUTA_SERIE = f"{DIR_PUBLICO}/ifg_serie.csv"
REGISTRO = f"{DIR_PUBLICO}/registro_publicaciones.csv"
REVISIONES = f"{DIR_PUBLICO}/revisiones.csv"
VENTANA_PUBLICACION = (3, 5)      # horas locales de Madrid: vale las 3 y las 4
ZONA = ZoneInfo("Europe/Madrid")

# Sesiones que se publican en el archivo compacto del panel. Doce meses de
# bolsa son unas 256 sesiones; se dejan 260 por margen.
SESIONES_PANEL = 260

# Columnas de la serie pública, en orden.
COLUMNAS = ["ifg", "ifg_suavizado", "variacion", "tramo", "cobertura", "parcial"]


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


def leer_serie_publicada() -> pd.DataFrame | None:
    """La serie tal y como quedó publicada en la ejecución anterior."""
    if not os.path.exists(RUTA_SERIE):
        return None
    try:
        previo = pd.read_csv(RUTA_SERIE, index_col=0, parse_dates=True)
    except Exception as e:                       # archivo corrupto o vacío
        log.warning("No se puede leer la serie publicada (%s). Se trata esta "
                    "ejecución como la primera.", e)
        return None
    if previo.empty:
        return None
    return previo


def fusionar(recalculada: pd.DataFrame,
             publicada: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.Series]:
    """
    Serie definitiva = filas ya publicadas INTACTAS + fechas nuevas.

    Devuelve también la deriva: para cada fecha ya publicada, cuánto se
    separa el valor que saldría hoy del que se publicó en su día. Esa serie
    no corrige nada; se publica para que la revisión sea auditable.
    """
    if publicada is None:
        log.info("No hay serie previa: se publica el recálculo entero (%d "
                 "sesiones).", len(recalculada))
        return recalculada, pd.Series(dtype=float)

    comunes = publicada.index.intersection(recalculada.index)
    deriva = (recalculada.loc[comunes, "ifg_suavizado"]
              - publicada.loc[comunes, "ifg_suavizado"]).dropna()

    nuevas = recalculada.index.difference(publicada.index)
    final = pd.concat([publicada, recalculada.loc[nuevas]]).sort_index()
    final = final[~final.index.duplicated(keep="first")]

    log.info("Fusión: %d sesiones ya publicadas se conservan, %d nuevas se "
             "añaden.", len(publicada), len(nuevas))
    if len(deriva) and deriva.abs().max() > 0.005:
        peor = deriva.abs().idxmax()
        log.warning("El recálculo se separa de lo publicado hasta %.3f puntos "
                    "(%s). NO se corrige: la serie publicada es inmutable.",
                    deriva.abs().max(), peor.date())
    return final, deriva


def anotar_revision(deriva: pd.Series, generado: str) -> None:
    """Una fila por ejecución con el tamaño de la deriva observada."""
    if deriva.empty:
        return
    peor = deriva.abs().idxmax()
    linea = (f"{generado},{len(deriva)},{deriva.abs().max():.4f},"
             f"{peor.date()},{int((deriva.abs() > 0.005).sum())}\n")
    nuevo = not os.path.exists(REVISIONES)
    with open(REVISIONES, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write("ejecutado,sesiones_comparadas,deriva_maxima,"
                     "fecha_peor,sesiones_movidas\n")
        fh.write(linea)


def escribir_serie_panel(final: pd.DataFrame, res: dict, generado: str,
                         fecha_dia: pd.Timestamp) -> dict:
    """
    Archivo compacto para el panel de la web: últimos doce meses.

    POR QUÉ EXISTE. La serie histórica completa (docs/ifg_serie.csv) tiene
    unas 4.000 filas y ronda los 250 KB. Eso vale como dato abierto para
    quien quiera descargarlo, pero no se puede pedir al navegador de cada
    lector para pintar un gráfico: penalizaría la carga de la página y
    obligaría a parsear CSV en el frontal.

    FORMATO. Arrays paralelos (fechas y valores) en vez de una lista de
    objetos. Ahorra la mitad del tamaño y es lo que una gráfica necesita.
    Se incluyen además las cifras agregadas que muestra el panel —máximo,
    mínimo y sesiones por tramo— para que el plugin no tenga que
    recalcularlas en PHP ni en JavaScript.

    Se construye sobre la serie YA FUSIONADA, no sobre el recálculo: el
    gráfico tiene que enseñar exactamente los valores publicados.

    NO SE TOCA docs/ifg.json en su forma. Los pipelines de Make ya leen ese
    archivo y cualquier cambio de estructura podría romperlos.
    """
    serie = final["ifg_suavizado"].dropna().tail(SESIONES_PANEL)
    tramos = final["tramo"].reindex(serie.index)

    # Desglose del último día. Se recalcula; ver el límite conocido anotado
    # en la cabecera del archivo.
    nivel = res["contribuciones"].loc[fecha_dia].dropna()

    panel = {
        "version": config.VERSION,
        "generado": generado,
        "desde": str(serie.index[0].date()),
        "hasta": str(serie.index[-1].date()),
        "sesiones": int(len(serie)),
        "fechas": [str(f.date()) for f in serie.index],
        "valores": [round(float(v), 2) for v in serie.values],
        "maximo": {"fecha": str(serie.idxmax().date()),
                   "valor": round(float(serie.max()), 2)},
        "minimo": {"fecha": str(serie.idxmin().date()),
                   "valor": round(float(serie.min()), 2)},
        "sesiones_por_tramo": {t: int((tramos == t).sum())
                               for _, _, t in config.TRAMOS},
        "desglose_nivel": {c: round(float(nivel[c]), 4) for c in nivel.index},
        "licencia": ("CC BY 4.0. Cita: el especulador.com, Índice de "
                     f"Fricción Global, versión {config.VERSION}."),
    }

    with open(f"{DIR_PUBLICO}/ifg_serie_12m.json", "w", encoding="utf-8") as fh:
        json.dump(panel, fh, ensure_ascii=False, separators=(",", ":"))
    return panel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ahora", action="store_true",
                   help="salta la guardia horaria")
    args = p.parse_args()

    if not args.ahora and not toca_publicar():
        return 0

    os.makedirs(DIR_PUBLICO, exist_ok=True)
    generado = datetime.now(ZONA).isoformat(timespec="seconds")

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

    # --- Solo sesiones cerradas ---------------------------------------------
    # Con la serie congelada, publicar la fecha de hoy sería congelar un
    # valor intradía como si fuera un cierre, y ya no habría forma de
    # corregirlo. En la ejecución normal de las 03:15 esto no quita nada: la
    # última sesión disponible es siempre la de un día anterior. Lo que evita
    # es que un --ahora lanzado por la tarde ensucie la serie para siempre.
    hoy = datetime.now(ZONA).date()
    recalculada = tabla[COLUMNAS].copy()
    abiertas = recalculada.index[recalculada.index.date >= hoy]
    if len(abiertas):
        log.warning("Se descartan %d sesiones sin cerrar (desde %s): no se "
                    "congela un valor intradía.", len(abiertas),
                    abiertas[0].date())
        recalculada = recalculada[recalculada.index.date < hoy]
    if recalculada.empty:
        log.error("No queda ninguna sesión cerrada que publicar.")
        return 1

    # --- Serie definitiva: lo publicado manda -------------------------------
    final, deriva = fusionar(recalculada, leer_serie_publicada())
    final.to_csv(RUTA_SERIE, float_format="%.2f")
    anotar_revision(deriva, generado)

    # --- Valor del día, tomado de la serie definitiva ------------------------
    # La fecha la manda la serie definitiva, no el recálculo: si se han
    # descartado sesiones sin cerrar, el día publicado es el último cerrado.
    fecha_dia = final.index[-1]
    ultimo = indice.descomponer_dia(res, fecha=fecha_dia)
    fila = final.loc[fecha_dia]

    # Si esta fecha ya estaba publicada, estos tres campos vienen de la
    # publicación original, no del recálculo de hoy. Es justo el punto de
    # toda la regla.
    ultimo["valor"] = None if pd.isna(fila["ifg_suavizado"]) else float(fila["ifg_suavizado"])
    ultimo["valor_crudo"] = None if pd.isna(fila["ifg"]) else float(fila["ifg"])
    ultimo["variacion"] = None if pd.isna(fila["variacion"]) else float(fila["variacion"])
    ultimo["tramo"] = fila["tramo"]

    ultimo["licencia"] = ("CC BY 4.0. Cita: el especulador.com, Índice de "
                          f"Fricción Global, versión {config.VERSION}.")
    ultimo["aviso"] = ("Contenido informativo y educativo. No constituye "
                       "asesoramiento financiero ni recomendación de inversión.")
    ultimo["estado"] = ("preliminar: reglas congeladas, índice en validación "
                        "prospectiva, no publicado como referencia citable")
    ultimo["revisiones"] = ("La serie publicada no se revisa. El recálculo "
                            "diario solo añade fechas nuevas; la deriva "
                            "observada se publica en revisiones.csv.")
    ultimo["generado"] = generado

    with open(f"{DIR_PUBLICO}/ifg.json", "w", encoding="utf-8") as fh:
        json.dump(ultimo, fh, ensure_ascii=False, indent=2)

    panel = escribir_serie_panel(final, res, generado, fecha_dia)
    log.info("Serie del panel: %d sesiones de %s a %s, máximo %.1f el %s.",
             panel["sesiones"], panel["desde"], panel["hasta"],
             panel["maximo"]["valor"], panel["maximo"]["fecha"])

    # Registro de ejecuciones: la prueba de que se publica sin fallos, que es
    # el requisito 5 de la sección 4, y la base de la validación prospectiva.
    # También es lo que evita publicar dos veces el mismo día.
    linea = (f"{generado},{ultimo['fecha']},{ultimo['valor']},"
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
