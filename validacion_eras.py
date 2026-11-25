# -*- coding: utf-8 -*-
"""
Auditoría de la serie publicada: cobertura, eras y coste del suavizado.

POR QUÉ EXISTE ESTE ARCHIVO. validacion.py comprueba si el índice aprueba
las cuatro pruebas con los umbrales fijados de antemano. Lo que no comprueba
es si la serie sobre la que se aplican esas pruebas es homogénea, y no lo es:
la cobertura de componentes pasa del 15 % en 2010 al 100 % desde el 11 de
junio de 2021. Un índice cuya composición cambia a lo largo de la serie no
es un índice midiendo épocas distintas: son índices distintos.

Este script responde a tres preguntas, sin tocar la fórmula ni recalcular
nada. Trabaja sobre la serie TAL Y COMO ESTÁ PUBLICADA en docs/ifg_serie.csv,
que es lo que un tercero leería.

  1. ¿Cuántos componentes entran en cada valor, año a año?
  2. ¿Qué hitos caen en zonas de cobertura demasiado baja para contrastar
     nada? El requisito 1 pide contrastar los picos con los hitos, y un hito
     evaluado con el 18 % de los componentes no contrasta.
  3. ¿Cuánto cuesta en sensibilidad el suavizado exponencial de 3 días que
     la especificación manda aplicar al titular?

UN FALLO QUE CORRIGE. La primera versión de este análisis recortaba la serie
y volvía a pasar la batería. Estaba mal: validacion._ventana localiza la
fecha con searchsorted, así que un hito anterior al inicio del recorte no se
descarta, se evalúa contra el principio de la serie y devuelve un número
que parece válido. Aquí un hito solo cuenta si su fecha cae DENTRO del rango
disponible. Por eso no se publican resultados por fecha de inicio: con la
ventana estricta, recortar la serie reduce los hitos evaluables y las tasas
dejan de ser comparables entre sí.

DISCIPLINA. Este script mide; no propone mover ningún umbral. Si el índice
no cumple, se corrige la fórmula, no el umbral (sección 7 del proyecto).

Uso:
    python validacion_eras.py
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import config

RUTA_SERIE = "docs/ifg_serie.csv"

U = config.UMBRALES
NIVEL = U["nivel_activacion"]
VENT = U["ventana_hito"]

# Por debajo de esta cobertura, el valor de una fecha no sirve para
# contrastar un hito. No es un umbral de aceptación del índice: es el punto
# en el que la serie pasa de 2-3 componentes a la mayoría de ellos.
COBERTURA_MINIMA_UTIL = 0.80


def ventana_estricta(s: pd.DataFrame, fecha: str, col: str) -> pd.Series | None:
    """La ventana alrededor del hito, o None si el hito no cabe en la serie."""
    f = pd.Timestamp(fecha)
    if f < s.index[0] or f > s.index[-1]:
        return None
    pos = s.index.searchsorted(f)
    ini = max(0, pos + VENT[0])
    fin = min(len(s), pos + VENT[1] + 1)
    v = s[col].iloc[ini:fin].dropna()
    return v if len(v) else None


def cobertura_en(s: pd.DataFrame, fecha: str) -> float:
    pos = s.index.searchsorted(pd.Timestamp(fecha))
    pos = min(pos, len(s) - 1)
    return float(s.iloc[pos]["cobertura"])


def eras(s: pd.DataFrame) -> None:
    print("=" * 86)
    print("1. ERAS DE COBERTURA")
    print("=" * 86)
    print(f"{'año':>6}  {'cobertura':>10}  {'parciales':>10}  {'sesiones':>9}")
    for ano, gr in s.groupby(s.index.year):
        print(f"{ano:>6}  {gr['cobertura'].mean():>10.2f}  "
              f"{100 * gr['parcial'].mean():>9.1f}%  {len(gr):>9}")
    for u in (0.50, 0.80, 0.95, 1.00):
        ok = s.index[s["cobertura"] >= u]
        cuando = ok[0].date() if len(ok) else "nunca"
        print(f"  primera sesión con cobertura >= {u:.2f}:  {cuando}")


def tabla_hitos(s: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for fecha, etiqueta, mayor in config.HITOS:
        vc = ventana_estricta(s, fecha, "ifg")
        vs = ventana_estricta(s, fecha, "ifg_suavizado")
        if vc is None or vs is None:
            continue
        max_c, max_s = float(vc.max()), float(vs.max())
        filas.append({
            "fecha": fecha, "evento": etiqueta, "mayor": mayor,
            "cobertura": cobertura_en(s, fecha),
            "max_crudo": round(max_c, 1), "max_suav": round(max_s, 1),
            "coste": round(max_c - max_s, 1),
            "det_crudo": max_c >= NIVEL, "det_suav": max_s >= NIVEL,
        })
    return pd.DataFrame(filas)


def informe_hitos(t: pd.DataFrame) -> None:
    print()
    print("=" * 86)
    print("2. HITOS: COBERTURA DE SU FECHA Y DETECCIÓN")
    print(f"Nivel de activación {NIVEL}, ventana {VENT} sesiones.")
    print("=" * 86)
    print(f"{'fecha':>12} {'cob':>5} {'crudo':>7} {'suav':>7} {'coste':>7} "
          f"{'det.c':>6} {'det.s':>6}  evento")
    for _, r in t.iterrows():
        avisos = ""
        if r["cobertura"] < COBERTURA_MINIMA_UTIL:
            avisos += "  [cobertura insuficiente]"
        if r["mayor"] and r["det_crudo"] and not r["det_suav"]:
            avisos += "  <== EL SUAVIZADO LO PIERDE"
        print(f"{r['fecha']:>12} {r['cobertura']:>5.2f} {r['max_crudo']:>7.1f} "
              f"{r['max_suav']:>7.1f} {r['coste']:>7.1f} "
              f"{'SÍ' if r['det_crudo'] else 'no':>6} "
              f"{'SÍ' if r['det_suav'] else 'no':>6}  "
              f"{'[MAYOR] ' if r['mayor'] else ''}{r['evento']}{avisos}")

    util = t[t["cobertura"] >= COBERTURA_MINIMA_UTIL]
    print()
    print(f"  hitos evaluables con cobertura suficiente: {len(util)} de {len(t)}")
    print(f"  de ellos, mayores: {int(util['mayor'].sum())} "
          f"de {int(t['mayor'].sum())}")


def informe_suavizado(t: pd.DataFrame) -> None:
    may = t[t["mayor"]]
    print()
    print("=" * 86)
    print("3. EL COSTE DEL SUAVIZADO SOBRE LOS HITOS MAYORES")
    print("=" * 86)
    tc, ts = may["det_crudo"].mean(), may["det_suav"].mean()
    print(f"  hitos mayores evaluables ........ {len(may)}")
    print(f"  sensibilidad del valor CRUDO .... {int(may['det_crudo'].sum())}"
          f"/{len(may)} = {tc:.0%}"
          f"   [umbral >= {U['tasa_acierto_minima']:.0%}]  "
          f"{'APRUEBA' if tc >= U['tasa_acierto_minima'] else 'SUSPENDE'}")
    print(f"  sensibilidad del TITULAR ........ {int(may['det_suav'].sum())}"
          f"/{len(may)} = {ts:.0%}"
          f"   [umbral >= {U['tasa_acierto_minima']:.0%}]  "
          f"{'APRUEBA' if ts >= U['tasa_acierto_minima'] else 'SUSPENDE'}")
    print(f"  coste medio del suavizado ....... {may['coste'].mean():.1f} puntos")
    print(f"  coste máximo .................... {may['coste'].max():.1f} puntos")

    perdidos = may[may["det_crudo"] & ~may["det_suav"]]
    print()
    print(f"  Hitos mayores que el suavizado pierde y el crudo detecta: "
          f"{len(perdidos)}")
    for _, r in perdidos.iterrows():
        print(f"      {r['fecha']}  {r['evento']}")
        print(f"          crudo {r['max_crudo']:.1f} -> suavizado "
              f"{r['max_suav']:.1f}  (coste {r['coste']:.1f})")

    ciegos = may[~may["det_crudo"] & ~may["det_suav"]]
    print()
    print(f"  Hitos mayores que NINGUNA de las dos series detecta: {len(ciegos)}")
    for _, r in ciegos.iterrows():
        print(f"      {r['fecha']}  {r['evento']}: máximo crudo "
              f"{r['max_crudo']:.1f}, por debajo de {NIVEL}")

    if len(may):
        necesarios = int(np.ceil(U["tasa_acierto_minima"] * len(may)))
        orden = np.sort(may["max_suav"].to_numpy())[::-1]
        if necesarios <= len(orden):
            print()
            print(f"  Para que el titular llegara al "
                  f"{U['tasa_acierto_minima']:.0%} haría falta bajar el nivel")
            print(f"  de activación de {NIVEL} a {orden[necesarios - 1]:.0f}. "
                  f"NO se propone: el umbral se fijó")
            print("  antes de ver los datos y moverlo ahora sería ajustar la "
                  "regla al resultado.")


def main() -> int:
    s = pd.read_csv(RUTA_SERIE, index_col=0, parse_dates=True)
    print(f"Serie publicada: {len(s)} sesiones, "
          f"{s.index[0].date()} -> {s.index[-1].date()}")
    eras(s)
    t = tabla_hitos(s)
    informe_hitos(t)
    informe_suavizado(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
