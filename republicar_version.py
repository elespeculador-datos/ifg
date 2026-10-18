# -*- coding: utf-8 -*-
"""
Republicación de la serie completa por cambio de versión.

ESTE SCRIPT ROMPE LA INMUTABILIDAD A PROPÓSITO. Es la única pieza del
proyecto autorizada a sustituir valores ya publicados, y existe precisamente
para que el flujo diario NO pueda hacerlo por accidente: publicar_diario.py
conserva intactas las filas cerradas y verificar_estabilidad.py detiene la
publicación si alguna se mueve. Cuando un cambio de reglas obliga a
recalcular la serie entera, esa protección hay que levantarla de forma
deliberada, declarada y trazable. Eso es lo que hace este archivo.

QUÉ GARANTIZA, A CAMBIO:

  1. No se ejecuta sin --confirmar y sin --version-anterior. Dos flags, para
     que no baste con un dedo torpe.
  2. Archiva la serie y la foto anteriores en docs/historico/ antes de tocar
     nada. Quien haya citado un valor de la versión vieja lo sigue
     encontrando: eso es lo que exige una política de revisiones seria.
  3. Escribe docs/revision_version.md con el antes y el después medidos
     —cuántas sesiones cambian, cuánto se mueven, cómo cambia la cobertura—
     para que la discontinuidad sea auditable y no un acto de fe.
  4. Deja la serie nueva con los estados bien puestos, de modo que el flujo
     diario siguiente la encuentre coherente y siga funcionando igual.

NO SE EJECUTA DESDE EL FLUJO DIARIO. Tiene su propio flujo manual.

Uso:
    python republicar_version.py --version-anterior 0.9.0 --confirmar
    python republicar_version.py --version-anterior 0.9.0 --simular
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config
import fuentes
import indice
import publicar_diario as pub

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("republicar")

DIR_HISTORICO = f"{pub.DIR_PUBLICO}/historico"
NOTA = f"{pub.DIR_PUBLICO}/revision_version.md"
ZONA = ZoneInfo("Europe/Madrid")


# ---------------------------------------------------------------------------
def archivar(version_anterior: str, simular: bool) -> list[str]:
    """Copia la serie y la foto actuales a docs/historico/ antes de tocarlas."""
    os.makedirs(DIR_HISTORICO, exist_ok=True)
    copiados = []
    for origen, nombre in (
            (pub.RUTA_SERIE, f"ifg_serie_{version_anterior}.csv"),
            (f"{pub.DIR_PUBLICO}/ifg.json", f"ifg_{version_anterior}.json"),
            (f"{pub.DIR_PUBLICO}/ifg_serie_12m.json",
             f"ifg_serie_12m_{version_anterior}.json"),
            (pub.RUTA_COMPONENTES, f"componentes_{version_anterior}.csv"),
    ):
        if not os.path.exists(origen):
            continue
        destino = f"{DIR_HISTORICO}/{nombre}"
        if os.path.exists(destino):
            log.warning("Ya existe %s. No se sobrescribe: ¿se republicó ya "
                        "esta versión?", destino)
            continue
        if not simular:
            shutil.copy2(origen, destino)
        copiados.append(destino)
        log.info("Archivado %s -> %s", origen, destino)
    return copiados


def comparar(antigua: pd.DataFrame | None, nueva: pd.DataFrame) -> dict:
    """Mide la discontinuidad. Sin esto, la republicación es un acto de fe."""
    if antigua is None or antigua.empty:
        return {"sin_anterior": True, "sesiones_nuevas": int(len(nueva))}

    com = antigua.index.intersection(nueva.index)
    d = (nueva.loc[com, "ifg"] - antigua.loc[com, "ifg"]).dropna()
    cambia_tramo = (nueva.loc[com, "tramo"].astype(str)
                    != antigua.loc[com, "tramo"].astype(str)).sum()
    return {
        "sin_anterior": False,
        "sesiones_antes": int(len(antigua)),
        "sesiones_despues": int(len(nueva)),
        "sesiones_comunes": int(len(com)),
        "sesiones_que_cambian": int((d.abs() > 0.005).sum()),
        "cambio_medio_abs": round(float(d.abs().mean()), 2) if len(d) else None,
        "cambio_mediano_abs": (round(float(d.abs().median()), 2)
                               if len(d) else None),
        "cambio_maximo_abs": round(float(d.abs().max()), 2) if len(d) else None,
        "fecha_cambio_maximo": (str(d.abs().idxmax().date())
                                if len(d) else None),
        "sesiones_que_cambian_de_tramo": int(cambia_tramo),
        "cobertura_media_antes": round(float(antigua["cobertura"].mean()), 3),
        "cobertura_media_despues": round(float(nueva["cobertura"].mean()), 3),
        "primera_sesion_cobertura_plena_antes": _primera_plena(antigua),
        "primera_sesion_cobertura_plena_despues": _primera_plena(nueva),
        # Año a año: es lo único que responde de verdad a "¿ha servido el
        # arreglo?". La media de toda la serie puede subir por muchos sitios;
        # lo que había que corregir era la era degradada del principio.
        "cobertura_por_ano": _por_ano(antigua, nueva),
    }


def _por_ano(antigua: pd.DataFrame, nueva: pd.DataFrame) -> list[tuple]:
    a = antigua.groupby(antigua.index.year)["cobertura"].mean()
    n = nueva.groupby(nueva.index.year)["cobertura"].mean()
    anos = sorted(set(a.index) | set(n.index))
    return [(int(y),
             None if y not in a.index else round(float(a[y]), 2),
             None if y not in n.index else round(float(n[y]), 2))
            for y in anos]


def _primera_plena(s: pd.DataFrame) -> str | None:
    ok = s.index[s["cobertura"] >= 0.9999]
    return str(ok[0].date()) if len(ok) else None


def escribir_nota(cmp_: dict, version_anterior: str, copiados: list[str],
                  simular: bool) -> str:
    hoy = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M %Z")
    L = [
        f"# Revisión de versión: {version_anterior} -> {config.VERSION}",
        "",
        f"Republicado el {hoy}.",
        "",
        "## Por qué se recalcula la serie entera",
        "",
        "Un cambio de reglas obliga a recalcular toda la serie: mantener "
        "valores viejos calculados con reglas viejas junto a valores nuevos "
        "calculados con reglas nuevas produciría una serie que no es "
        "comparable consigo misma. Los cambios de esta versión están "
        "detallados en la cabecera de `config.py`.",
        "",
        "## Qué cambia, medido",
        "",
    ]
    if cmp_.get("sin_anterior"):
        L.append(f"- No había serie anterior. Se publican "
                 f"{cmp_['sesiones_nuevas']} sesiones.")
    else:
        L += [
            f"- Sesiones antes: **{cmp_['sesiones_antes']}** · "
            f"después: **{cmp_['sesiones_despues']}**",
            f"- Sesiones cuyo valor cambia: "
            f"**{cmp_['sesiones_que_cambian']}** de "
            f"{cmp_['sesiones_comunes']} comunes",
            f"- Cambio absoluto medio: **{cmp_['cambio_medio_abs']}** puntos "
            f"(mediana {cmp_['cambio_mediano_abs']})",
            f"- Cambio máximo: **{cmp_['cambio_maximo_abs']}** puntos, el "
            f"{cmp_['fecha_cambio_maximo']}",
            f"- Sesiones que cambian de tramo: "
            f"**{cmp_['sesiones_que_cambian_de_tramo']}**",
            f"- Cobertura media de componentes: "
            f"{cmp_['cobertura_media_antes']} -> "
            f"**{cmp_['cobertura_media_despues']}**",
            f"- Primera sesión con cobertura plena: "
            f"{cmp_['primera_sesion_cobertura_plena_antes']} -> "
            f"**{cmp_['primera_sesion_cobertura_plena_despues']}**",
        ]
    if cmp_.get("cobertura_por_ano"):
        L += [
            "",
            "### Cobertura de componentes, año a año",
            "",
            "Es lo que responde de verdad a si el arreglo ha servido: la media "
            "de toda la serie puede subir por muchos sitios, pero lo que había "
            "que corregir era la era degradada del principio.",
            "",
            "| Año | Antes | Después |",
            "|---|---|---|",
        ]
        for y, a, n in cmp_["cobertura_por_ano"]:
            marca = ""
            if a is not None and n is not None and n - a >= 0.10:
                marca = " (mejora)"
            L.append(f"| {y} | {'—' if a is None else f'{a:.2f}'} | "
                     f"{'—' if n is None else f'{n:.2f}'}{marca} |")

    L += [
        "",
        "## Dónde está la serie anterior",
        "",
        "Archivada, no borrada. Quien haya citado un valor de la versión "
        "anterior lo sigue encontrando aquí:",
        "",
    ]
    L += [f"- `{c}`" for c in copiados] or ["- (no había archivos previos)"]
    L += [
        "",
        "## Encuadre",
        "",
        "Contenido informativo y educativo. No constituye asesoramiento "
        "financiero ni recomendación de inversión. El índice es una lectura "
        "del estado del mercado, nunca una señal de compra o de venta.",
        "",
    ]
    texto = "\n".join(L)
    if not simular:
        with open(NOTA, "w", encoding="utf-8") as fh:
            fh.write(texto)
        log.info("Nota de revisión escrita en %s", NOTA)
    return texto


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version-anterior", required=True,
                    help="versión que se está sustituyendo, p. ej. 0.9.0")
    ap.add_argument("--confirmar", action="store_true",
                    help="obligatorio para escribir: esto sustituye valores "
                         "ya publicados")
    ap.add_argument("--simular", action="store_true",
                    help="calcula y mide, pero no escribe nada")
    args = ap.parse_args()

    if not args.confirmar and not args.simular:
        log.error("Hace falta --confirmar (o --simular). Este script sustituye "
                  "valores ya publicados y no se ejecuta por descuido.")
        return 2
    if args.version_anterior == config.VERSION:
        log.error("La versión anterior (%s) coincide con la de config.py. "
                  "¿Se olvidó subir VERSION?", config.VERSION)
        return 2

    log.info("Republicando: %s -> %s%s", args.version_anterior, config.VERSION,
             "  (SIMULACIÓN)" if args.simular else "")

    # --- Serie publicada hasta ahora ---------------------------------------
    antigua = None
    if os.path.exists(pub.RUTA_SERIE):
        antigua = pd.read_csv(pub.RUTA_SERIE, index_col=0, parse_dates=True)
        log.info("Serie anterior: %d sesiones, %s -> %s", len(antigua),
                 antigua.index[0].date(), antigua.index[-1].date())

    # --- Descarga y recálculo completo -------------------------------------
    tickers = {**config.TICKERS, **config.CESTA_DEFENSA, **config.CESTA_FLETES}
    precios = fuentes.descargar_precios(tickers,
                                        inicio=config.FECHA_INICIO_MUESTRA,
                                        usar_cache=False)
    gpr = fuentes.descargar_gpr(usar_cache=False)
    prima = fuentes.descargar_prima_riesgo(usar_cache=False)
    gdelt = fuentes.cargar_gdelt()

    res = indice.calcular(precios, gpr=gpr, prima=prima, gdelt=gdelt)
    nueva = res["tabla"][pub.COLUMNAS].dropna(subset=["ifg"]).copy()

    # Toda la serie recalculada nace con su estado según cobertura. Las
    # últimas VENTANA_PROVISIONAL sesiones pueden quedar provisionales si les
    # falta algún componente; el resto se cierra.
    ventana = set(nueva.index[-pub.VENTANA_PROVISIONAL:])
    nueva["estado"] = [pub.estado_de(float(c), f in ventana)
                       for f, c in nueva["cobertura"].items()]

    log.info("Serie nueva: %d sesiones, %s -> %s", len(nueva),
             nueva.index[0].date(), nueva.index[-1].date())

    cmp_ = comparar(antigua, nueva)
    for k, v in cmp_.items():
        log.info("  %-42s %s", k, v)

    if args.simular:
        print()
        print(escribir_nota(cmp_, args.version_anterior, [], simular=True))
        log.info("SIMULACIÓN: no se ha escrito nada.")
        return 0

    # --- Escritura, ya con todo medido -------------------------------------
    copiados = archivar(args.version_anterior, simular=False)
    nueva.to_csv(pub.RUTA_SERIE, float_format="%.2f")
    log.info("Serie nueva escrita en %s", pub.RUTA_SERIE)

    generado = datetime.now(ZONA).isoformat(timespec="seconds")
    fecha_dia = nueva.index[-1]
    ultimo = indice.descomponer_dia(res, fecha_dia)
    ultimo["estado_dato"] = str(nueva.loc[fecha_dia, "estado"])
    ultimo["generado"] = generado
    ultimo["revisiones"] = (
        f"Serie recalculada al pasar de {args.version_anterior} a "
        f"{config.VERSION}. Ver revision_version.md y docs/historico/.")
    with open(f"{pub.DIR_PUBLICO}/ifg.json", "w", encoding="utf-8") as fh:
        json.dump(ultimo, fh, ensure_ascii=False, indent=2)
    log.info("Foto del día reescrita.")

    pub.escribir_serie_panel(nueva, res, generado, fecha_dia)

    # El archivo de componentes se reescribe DESDE CERO, no se actualiza.
    # archivar_componentes() conserva a propósito las filas ya cerradas, que es
    # lo correcto a diario; en un cambio de versión dejaría los z-scores de la
    # versión vieja mezclados con los de la nueva y el archivo perdería su
    # única función: que cualquiera pueda reproducir el valor publicado
    # aplicando la fórmula publicada. Ya está archivado en docs/historico/.
    if os.path.exists(pub.RUTA_COMPONENTES):
        os.remove(pub.RUTA_COMPONENTES)
        log.info("Componentes de la versión anterior retirados; se reescriben "
                 "desde cero.")
    pub.archivar_componentes(nueva, res)
    escribir_nota(cmp_, args.version_anterior, copiados, simular=False)

    log.info("HECHO. Revisa docs/revision_version.md antes de hacer commit.")
    log.info("RECUERDA: verificar_estabilidad.py va a fallar contra el commit "
             "anterior, y es correcto que falle. No se ejecuta en esta "
             "republicación.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
