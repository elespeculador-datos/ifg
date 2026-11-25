# -*- coding: utf-8 -*-
"""
Autopsia de los tres hitos mayores que el índice no detecta.

No busca un arreglo. Busca entender POR QUÉ falla, que es distinto: si la
causa es que un componente está mal especificado, eso es un defecto y se
corrige; si la causa es que el episodio no dejó firma en los precios, el
índice está haciendo lo correcto y el hito estaba mal clasificado; si la
causa es la normalización, es una limitación estructural que se declara.

Los tres casos:
    2016-06-23  Brexit ............... máximo 62,5
    2019-09-14  Abqaiq ............... máximo 70,9
    2022-08-26  Pico crisis del gas .. máximo 68,5

Contraste con tres que sí detecta, para tener referencia:
    2022-02-24  Invasión de Ucrania .. 100,0
    2023-10-07  Ataque de Hamás ...... 99,7
    2020-01-03  Soleimani ............ 95,5

LIMITACIÓN. Se recalcula sin GDELT, porque la muestra está en parquet y este
entorno no tiene pyarrow. GDELT pesa 10 de 100 y es opcional: el pipeline
reparte su peso entre los disponibles. Por eso al final se compara la serie
recalculada con la publicada: si el error es pequeño, el diagnóstico sobre
qué componentes se movieron es fiable.

Uso:
    python autopsia.py
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import config   # noqa: E402
import indice   # noqa: E402

BASE = "."

FALLOS = [
    ("2016-06-23", "Brexit"),
    ("2019-09-14", "Abqaiq"),
    ("2022-08-26", "Pico crisis del gas"),
]
ACIERTOS = [
    ("2020-01-03", "Soleimani"),
    ("2022-02-24", "Invasión de Ucrania"),
    ("2023-10-07", "Ataque de Hamás"),
]


def cargar():
    p = pd.read_csv(f"{BASE}/datos/precios.csv", index_col=0, parse_dates=True)
    g = pd.read_csv(f"{BASE}/datos/gpr.csv", index_col=0, parse_dates=True)["gpr"]
    pr = pd.read_csv(f"{BASE}/datos/prima.csv", index_col=0, parse_dates=True)
    pr = pr.iloc[:, 0]
    return p, g, pr


def maximo_ventana(s: pd.Series, fecha: str) -> tuple[float, pd.Timestamp]:
    """Máximo del componente en la ventana del hito, y cuándo se alcanza."""
    lo, hi = config.UMBRALES["ventana_hito"]
    pos = s.index.searchsorted(pd.Timestamp(fecha))
    v = s.iloc[max(0, pos + lo): min(len(s), pos + hi + 1)].dropna()
    if v.empty:
        return np.nan, pd.NaT
    return float(v.max()), v.idxmax()


def main() -> int:
    p, g, pr = cargar()
    res = indice.calcular(p, gpr=g, prima=pr, gdelt=None)

    comp = res["componentes"]
    ifg = res["tabla"]["ifg"]

    # --- ¿es fiable el recálculo sin GDELT? ---------------------------------
    pub = pd.read_csv(f"{BASE}/docs/ifg_serie.csv", index_col=0, parse_dates=True)
    com = ifg.index.intersection(pub.index)
    err = (ifg.loc[com] - pub.loc[com, "ifg"]).abs()
    print("=" * 84)
    print("0. FIABILIDAD DEL RECÁLCULO SIN GDELT")
    print("=" * 84)
    print(f"  sesiones comparadas .......... {len(com)}")
    print(f"  error absoluto medio ......... {err.mean():.2f} puntos")
    print(f"  error absoluto mediano ....... {err.median():.2f} puntos")
    print(f"  percentil 95 del error ....... {err.quantile(0.95):.2f} puntos")
    print(f"  error máximo ................. {err.max():.2f} puntos")
    if err.mean() > 5:
        print("  AVISO: el error medio es alto. El diagnóstico por componentes")
        print("  sigue siendo indicativo, pero los niveles no son comparables.")

    print()
    print("=" * 84)
    print("1. QUÉ HIZO CADA COMPONENTE (z-score máximo en la ventana del hito)")
    print("=" * 84)
    cols = [c for c in comp.columns]
    cab = "  ".join(f"{c[:9]:>9}" for c in cols)
    print(f"{'hito':>22}  {'IFG':>6}  {cab}")

    for etiqueta_grupo, grupo in (("NO DETECTADOS", FALLOS),
                                  ("DETECTADOS", ACIERTOS)):
        print(f"  --- {etiqueta_grupo} ---")
        for fecha, nombre in grupo:
            mx, _ = maximo_ventana(ifg, fecha)
            fila = []
            for c in cols:
                z, _ = maximo_ventana(comp[c], fecha)
                fila.append("      n/d" if np.isnan(z) else f"{z:>9.2f}")
            print(f"{nombre[:22]:>22}  {mx:>6.1f}  " + "  ".join(fila))

    # --- ¿cuántos componentes faltaban en cada fecha? -----------------------
    print()
    print("=" * 84)
    print("2. COMPONENTES AUSENTES EN LA FECHA DEL HITO")
    print("=" * 84)
    for fecha, nombre in FALLOS + ACIERTOS:
        pos = comp.index.searchsorted(pd.Timestamp(fecha))
        pos = min(pos, len(comp) - 1)
        fila = comp.iloc[pos]
        ausentes = [c for c in cols if pd.isna(fila[c])]
        print(f"  {fecha}  {nombre[:24]:>24}:  "
              f"{len(cols) - len(ausentes)}/{len(cols)} presentes"
              + (f"   faltan: {', '.join(ausentes)}" if ausentes else ""))

    # --- ¿está la winsorización recortando la señal? -----------------------
    print()
    print("=" * 84)
    print(f"3. ¿RECORTA LA WINSORIZACIÓN? (CLIP_Z = {config.CLIP_Z})")
    print("=" * 84)
    print("  Si un componente toca el tope justo en los hitos, el índice no")
    print("  puede distinguir 'grave' de 'gravísimo'. Sesiones en el tope:")
    tope = config.CLIP_Z
    for c in cols:
        s = comp[c].dropna()
        if s.empty:
            continue
        n_tope = int((s >= tope - 1e-9).sum())
        pct = 100 * n_tope / len(s)
        marca = "   <== TOCA TOPE" if pct > 0.5 else ""
        print(f"    {c:>12}:  {n_tope:>4} de {len(s)} sesiones "
              f"({pct:>4.1f} %)  máx {s.max():.2f}{marca}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
