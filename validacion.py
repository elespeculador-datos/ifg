# -*- coding: utf-8 -*-
"""
Batería de validación del IFG.

Los umbrales están en config.UMBRALES y se han fijado ANTES de ver un solo
resultado. Si el índice no los cumple, se cambia la fórmula, no el umbral.

Cuatro pruebas:
  A. Sensibilidad: ¿sube en los hitos geopolíticos?
  B. Especificidad: ¿se queda quieto en caídas de bolsa no geopolíticas?
     Esta es la prueba importante. Sin ella, cualquier índice de risk-off
     aprueba el test A y no aporta nada.
  C. Independencia: ¿se distingue del VIX y del GPR?
  D. Estructura: ¿los pesos efectivos se parecen a los nominales?
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def _ventana(serie: pd.Series, fecha: str, desp: tuple[int, int]) -> pd.Series:
    """Sub-serie en una ventana de sesiones alrededor de una fecha."""
    idx = serie.index
    f = pd.Timestamp(fecha)
    pos = idx.searchsorted(f)
    if pos >= len(idx):
        return pd.Series(dtype=float)
    ini = max(0, pos + desp[0])
    fin = min(len(idx), pos + desp[1] + 1)
    return serie.iloc[ini:fin]


# ---------------------------------------------------------------------------
# A. Sensibilidad a hitos
# ---------------------------------------------------------------------------
def test_hitos(ifg: pd.Series) -> pd.DataFrame:
    filas = []
    for fecha, etiqueta, mayor in config.HITOS:
        v = _ventana(ifg, fecha, config.UMBRALES["ventana_hito"]).dropna()
        if v.empty:
            filas.append({"fecha": fecha, "evento": etiqueta, "mayor": mayor,
                          "maximo": np.nan, "previo": np.nan, "salto": np.nan,
                          "detectado": None})
            continue
        previo = _ventana(ifg, fecha, (-25, -3)).dropna()
        base = previo.mean() if not previo.empty else np.nan
        maximo = v.max()
        filas.append({
            "fecha": fecha, "evento": etiqueta, "mayor": mayor,
            "maximo": round(float(maximo), 1),
            "previo": None if pd.isna(base) else round(float(base), 1),
            "salto": None if pd.isna(base) else round(float(maximo - base), 1),
            "detectado": bool(maximo >= config.UMBRALES["nivel_activacion"]),
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# B. Especificidad: falsos positivos
# ---------------------------------------------------------------------------
def test_controles(ifg: pd.Series, precios: pd.DataFrame | None = None) -> pd.DataFrame:
    filas = []
    for fecha, etiqueta in config.CONTROLES:
        v = _ventana(ifg, fecha, config.UMBRALES["ventana_hito"]).dropna()
        caida = np.nan
        if precios is not None and "acwi" in precios.columns:
            p = _ventana(precios["acwi"], fecha, (-5, 10)).dropna()
            if len(p) > 1:
                caida = round(float(p.min() / p.iloc[0] - 1) * 100, 1)
        filas.append({
            "fecha": fecha, "evento": etiqueta,
            "caida_bolsa_%": caida,
            "maximo_ifg": np.nan if v.empty else round(float(v.max()), 1),
            "falso_positivo": None if v.empty
            else bool(v.max() >= config.UMBRALES["nivel_falso_positivo"]),
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# C. Independencia
# ---------------------------------------------------------------------------
def test_independencia(ifg: pd.Series,
                       vix: pd.Series | None,
                       gpr: pd.Series | None) -> dict:
    res: dict[str, float | None] = {}

    if vix is not None and not vix.empty:
        alin = pd.concat([ifg, vix.rename("vix")], axis=1).dropna()
        if len(alin) > 250:
            res["corr_vix_niveles"] = round(float(alin.corr().iloc[0, 1]), 3)
            d = alin.diff().dropna()
            res["corr_vix_variaciones"] = round(float(d.corr().iloc[0, 1]), 3)
    if gpr is not None and not gpr.empty:
        alin = pd.concat([ifg, gpr.rename("gpr")], axis=1).dropna()
        if len(alin) > 250:
            res["corr_gpr_niveles"] = round(float(alin.corr().iloc[0, 1]), 3)
    return res


# ---------------------------------------------------------------------------
# D. Estructura interna
# ---------------------------------------------------------------------------
def pesos_efectivos(componentes: pd.DataFrame,
                    compuesto: pd.Series,
                    pesos: dict[str, float] = None) -> pd.DataFrame:
    """
    Peso NOMINAL frente a peso EFECTIVO.

    El peso efectivo es la contribución de cada componente a la varianza del
    compuesto: w_i * cov(z_i, S) / var(S). Si dos componentes correlacionan
    0,8 y suman 45 puntos de peso nominal, el índice es en realidad un índice
    de ese factor, diga lo que diga la tabla de pesos. Este diagnóstico es
    obligatorio antes de congelar la fórmula.
    """
    pesos = pesos or config.PESOS
    cols = [c for c in componentes.columns if c in pesos]
    datos = pd.concat([componentes[cols], compuesto.rename("S")], axis=1).dropna()
    if datos.empty:
        return pd.DataFrame()

    w = pd.Series({c: pesos[c] for c in cols}, dtype=float)
    w = w / w.sum()
    var_s = datos["S"].var()
    efectivos = {c: w[c] * datos[c].cov(datos["S"]) / var_s for c in cols}

    return (pd.DataFrame({
        "peso_nominal_%": (w * 100).round(1),
        "peso_efectivo_%": (pd.Series(efectivos) * 100).round(1),
    }).assign(desvio=lambda d: (d["peso_efectivo_%"] - d["peso_nominal_%"]).round(1))
      .sort_values("peso_efectivo_%", ascending=False))


def frecuencia_tramos(resultado: dict) -> pd.DataFrame:
    """
    Cuántos días al año pasa el índice en cada tramo.

    Diagnóstico imprescindible: si el tramo "Extrema" se activa 25 días al
    año, la palabra deja de significar nada y el índice pierde autoridad
    editorial. Con escala de percentil uniforme esto ocurre por construcción.
    """
    t = resultado["tabla"]["tramo"]
    t = t[t != "sin dato"]
    if t.empty:
        return pd.DataFrame()
    conteo = t.value_counts()
    orden = [e for _, _, e in config.TRAMOS]
    conteo = conteo.reindex(orden).fillna(0).astype(int)
    return pd.DataFrame({
        "días": conteo,
        "% del tiempo": (conteo / len(t) * 100).round(1),
        "días/año": (conteo / (len(t) / 252)).round(0).astype(int),
    })


def matriz_correlacion(componentes: pd.DataFrame) -> pd.DataFrame:
    return componentes.dropna(how="all").corr().round(2)


# ---------------------------------------------------------------------------
# Informe agregado
# ---------------------------------------------------------------------------
def informe(resultado: dict,
            precios: pd.DataFrame,
            gpr: pd.Series | None = None) -> str:
    ifg = resultado["tabla"]["ifg_suavizado"]
    lineas: list[str] = []
    add = lineas.append

    add("=" * 78)
    add(f"VALIDACIÓN DEL IFG  ·  versión {config.VERSION}")
    add(f"Modo transformación: {config.MODO_TRANSFORMACION}  ·  "
        f"percentil: {config.MODO_PERCENTIL}")
    add("=" * 78)

    # --- A ---
    th = test_hitos(ifg)
    mayores = th[th["mayor"] & th["detectado"].notna()]
    tasa = mayores["detectado"].mean() if not mayores.empty else np.nan
    add("\nA. SENSIBILIDAD A HITOS GEOPOLÍTICOS")
    add(th.to_string(index=False))
    add(f"\n   Tasa de acierto en hitos mayores: "
        f"{tasa:.0%} (umbral fijado: {config.UMBRALES['tasa_acierto_minima']:.0%}) "
        f"-> {'APRUEBA' if tasa >= config.UMBRALES['tasa_acierto_minima'] else 'SUSPENDE'}")

    # --- B ---
    tc = test_controles(ifg, precios)
    val = tc[tc["falso_positivo"].notna()]
    tasa_fp = val["falso_positivo"].mean() if not val.empty else np.nan
    add("\n\nB. ESPECIFICIDAD (caídas de bolsa SIN origen geopolítico)")
    add(tc.to_string(index=False))
    add(f"\n   Tasa de falsos positivos: {tasa_fp:.0%} "
        f"(umbral fijado: {config.UMBRALES['tasa_falsos_maxima']:.0%}) "
        f"-> {'APRUEBA' if tasa_fp <= config.UMBRALES['tasa_falsos_maxima'] else 'SUSPENDE'}")

    # --- C ---
    vix = precios["vix"] if "vix" in precios.columns else None
    ind = test_independencia(ifg, vix, gpr)
    add("\n\nC. INDEPENDENCIA")
    if not ind:
        add("   Sin series de referencia disponibles (VIX / GPR).")
    for k, v in ind.items():
        add(f"   {k:28s} {v:+.3f}")
    if "corr_vix_variaciones" in ind:
        ok = abs(ind["corr_vix_variaciones"]) < config.UMBRALES["corr_max_vix_variaciones"]
        add(f"   -> frente al VIX: {'APRUEBA' if ok else 'SUSPENDE (es un VIX disfrazado)'}")
    if "corr_gpr_niveles" in ind:
        c = ind["corr_gpr_niveles"]
        ok = (config.UMBRALES["corr_min_gpr_niveles"] <= c
              <= config.UMBRALES["corr_max_gpr_niveles"])
        add(f"   -> frente al GPR: {'APRUEBA' if ok else 'SUSPENDE'}")

    # --- D ---
    add("\n\nD. ESTRUCTURA INTERNA")
    pe = pesos_efectivos(resultado["componentes"], resultado["tabla"]["compuesto"])
    add(pe.to_string() if not pe.empty else "   Sin datos suficientes.")
    add("\n   Correlación entre componentes:")
    add(matriz_correlacion(resultado["componentes"]).to_string())

    # --- E. Comportamiento editorial ---
    add("\n\nE. COMPORTAMIENTO EDITORIAL (frecuencia de tramos)")
    add(frecuencia_tramos(resultado).to_string())
    cambios = (resultado["tabla"]["tramo"] != resultado["tabla"]["tramo"].shift()).sum()
    anios = max(1, len(resultado["tabla"]) / 252)
    add(f"\n   Cambios de tramo: {int(cambios)} en {anios:.1f} años "
        f"({cambios / anios:.0f} al año)")
    add("   Referencia: por encima de ~40 cambios al año el índice es ruido "
        "y no aguanta una narración de régimen.")

    # --- Cobertura ---
    cob = resultado["tabla"]["cobertura"]
    add(f"\n\nF. COBERTURA DE DATOS")
    add(f"   Cobertura media: {cob.mean():.1%}  ·  mínima: {cob.min():.1%}")
    add(f"   Días marcados como parciales: {int(resultado['tabla']['parcial'].sum())} "
        f"de {len(cob)}")
    add("=" * 78)
    return "\n".join(lineas)
