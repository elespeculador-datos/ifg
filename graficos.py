# -*- coding: utf-8 -*-
"""Gráficos de diagnóstico del IFG."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

import config

COLORES_TRAMO = {
    "Calma":   "#e8f0e8",
    "Normal":  "#f2f2ee",
    "Tensión": "#fbeee0",
    "Alta":    "#f8dcd0",
    "Extrema": "#f2c4c4",
}


def grafico_historico(resultado: dict,
                      ruta: str = "salidas/ifg_historico.png",
                      solo_mayores: bool = False) -> str:
    """Serie del IFG con bandas de tramo y hitos geopolíticos marcados."""
    tabla = resultado["tabla"]
    ifg = tabla["ifg_suavizado"].dropna()
    if ifg.empty:
        raise ValueError("No hay valores del índice para representar.")

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(16, 9), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )

    for bajo, alto, etiqueta in config.TRAMOS:
        ax.axhspan(bajo, min(alto, 100), color=COLORES_TRAMO[etiqueta], zorder=0)
        ax.text(ifg.index[2], (bajo + min(alto, 100)) / 2, etiqueta,
                fontsize=8, va="center", color="#666", zorder=1)

    ax.plot(ifg.index, ifg.values, color="#1a1a1a", linewidth=1.1, zorder=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("IFG (0-100)")
    ax.set_title(f"Índice de Fricción Global · versión {config.VERSION} · "
                 f"modo {config.MODO_TRANSFORMACION}/{config.MODO_PERCENTIL}",
                 loc="left", fontsize=13, weight="bold")

    hitos = [h for h in config.HITOS if (h[2] or not solo_mayores)]
    alturas = [96, 88, 80]
    for i, (fecha, etiqueta, mayor) in enumerate(hitos):
        f = pd.Timestamp(fecha)
        if f < ifg.index[0] or f > ifg.index[-1]:
            continue
        ax.axvline(f, color="#b03030" if mayor else "#999",
                   linewidth=1.0 if mayor else 0.6,
                   linestyle="-" if mayor else ":", alpha=0.8, zorder=2)
        if mayor:
            ax.annotate(etiqueta, xy=(f, alturas[i % 3]), fontsize=7,
                        rotation=90, ha="right", va="top", color="#b03030")

    for fecha, etiqueta in config.CONTROLES:
        f = pd.Timestamp(fecha)
        if ifg.index[0] <= f <= ifg.index[-1]:
            ax.axvline(f, color="#3060b0", linewidth=0.8, linestyle="--",
                       alpha=0.55, zorder=2)

    ax.plot([], [], color="#b03030", label="Hito geopolítico mayor")
    ax.plot([], [], color="#3060b0", linestyle="--", label="Control (caída no geopolítica)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # Panel inferior: contribuciones apiladas
    contrib = resultado["contribuciones"].dropna(how="all")
    if not contrib.empty:
        suave = contrib.rolling(21, min_periods=5).mean()
        pos = suave.clip(lower=0)
        neg = suave.clip(upper=0)
        ax2.stackplot(suave.index, *[pos[c] for c in suave.columns],
                      labels=list(suave.columns), alpha=0.85)
        ax2.stackplot(suave.index, *[neg[c] for c in suave.columns], alpha=0.85)
        ax2.axhline(0, color="#333", linewidth=0.6)
        ax2.legend(loc="upper left", ncol=4, fontsize=7, framealpha=0.9)
    ax2.set_ylabel("Contribución\n(media 21 s.)")
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    for eje in (ax, ax2):
        eje.grid(axis="y", alpha=0.25, linewidth=0.5)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)

    fig.text(0.01, 0.005,
             "Contenido informativo y educativo. No constituye asesoramiento "
             "financiero ni recomendación de inversión.",
             fontsize=7, color="#777")
    fig.savefig(ruta, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return ruta


def grafico_componentes(resultado: dict,
                        ruta: str = "salidas/ifg_componentes.png") -> str:
    """Un panel por componente, para ver si alguno está muerto o desbocado."""
    comp = resultado["componentes"].dropna(how="all")
    if comp.empty:
        raise ValueError("No hay componentes que representar.")
    n = len(comp.columns)
    fig, ejes = plt.subplots(n, 1, figsize=(14, 1.7 * n), sharex=True)
    if n == 1:
        ejes = [ejes]
    for eje, col in zip(ejes, comp.columns):
        eje.plot(comp.index, comp[col], linewidth=0.7, color="#1a1a1a")
        eje.axhline(0, color="#999", linewidth=0.5)
        eje.set_ylabel(col, fontsize=8, rotation=0, ha="right", va="center")
        eje.grid(axis="y", alpha=0.2)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
    ejes[0].set_title("Componentes del IFG en z-score", loc="left", weight="bold")
    fig.savefig(ruta, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return ruta
