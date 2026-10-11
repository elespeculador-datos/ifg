# -*- coding: utf-8 -*-
"""
Comparación de agregadores con muestra partida.

Esta es la prueba que decide si la versión 2 vale algo. Se calibra la
dirección discriminante SOLO con episodios anteriores a la fecha de corte y
se mide el rendimiento por separado dentro y fuera de muestra.

Lo que hay que mirar, en este orden:

  1. La separación FUERA de muestra. Si los hitos posteriores al corte no se
     separan de los controles posteriores al corte, la firma era ruido y el
     enfoque se descarta.
  2. La caída entre dentro y fuera. Si dentro separa mucho y fuera nada, la
     dirección está sobreajustada y hay que subir el encogimiento o reducir
     componentes.
  3. La comparación con la media ponderada. Si la firma no mejora a la media,
     no se justifica la complejidad añadida y se publica la media.

Un agregador que gana dentro de muestra no ha demostrado nada: con diez
componentes y once episodios, encontrar una dirección que los separe es
trivial. La pregunta es si sigue separando lo que nunca vio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import config
import indice
import validacion


def _saltos(ifg: pd.Series, eventos, desde=None, hasta=None) -> list[float]:
    """Salto máximo sobre la base previa, para cada evento del periodo."""
    salidas = []
    for item in eventos:
        f = pd.Timestamp(item[0])
        if desde is not None and f < pd.Timestamp(desde):
            continue
        if hasta is not None and f >= pd.Timestamp(hasta):
            continue
        v = validacion._ventana(ifg, item[0], config.UMBRALES["ventana_hito"]).dropna()
        p = validacion._ventana(ifg, item[0], (-25, -3)).dropna()
        if v.empty or p.empty:
            continue
        salidas.append(float(v.max() - p.mean()))
    return salidas


def evaluar(ifg: pd.Series, desde=None, hasta=None, etiqueta="") -> dict:
    """Separación entre hitos y controles en un periodo."""
    sh = _saltos(ifg, config.HITOS, desde, hasta)
    sc = _saltos(ifg, config.CONTROLES, desde, hasta)
    res = {
        "periodo": etiqueta,
        "n_hitos": len(sh),
        "n_controles": len(sc),
        "salto_hitos": round(float(np.mean(sh)), 1) if sh else np.nan,
        "salto_controles": round(float(np.mean(sc)), 1) if sc else np.nan,
    }
    if len(sh) >= 3 and len(sc) >= 3:
        res["separacion"] = round(res["salto_hitos"] - res["salto_controles"], 1)
        # Tamaño del efecto: separación en desviaciones típicas combinadas.
        # Más informativo que el valor p con muestras de este tamaño.
        s = np.sqrt((np.var(sh, ddof=1) + np.var(sc, ddof=1)) / 2)
        res["efecto_d"] = round((np.mean(sh) - np.mean(sc)) / s, 2) if s > 0 else np.nan
        res["p"] = round(float(stats.mannwhitneyu(sh, sc, alternative="greater").pvalue), 3)
    else:
        res["separacion"] = res["efecto_d"] = res["p"] = np.nan

    # Tasas con los umbrales fijados de antemano
    mayores = [h for h in config.HITOS if h[2]]
    det = [validacion._ventana(ifg, h[0], config.UMBRALES["ventana_hito"]).max()
           for h in mayores
           if (desde is None or pd.Timestamp(h[0]) >= pd.Timestamp(desde))
           and (hasta is None or pd.Timestamp(h[0]) < pd.Timestamp(hasta))]
    det = [d for d in det if pd.notna(d)]
    fp = [validacion._ventana(ifg, c[0], config.UMBRALES["ventana_hito"]).max()
          for c in config.CONTROLES
          if (desde is None or pd.Timestamp(c[0]) >= pd.Timestamp(desde))
          and (hasta is None or pd.Timestamp(c[0]) < pd.Timestamp(hasta))]
    fp = [f for f in fp if pd.notna(f)]
    u = config.UMBRALES["nivel_activacion"]
    res["acierto_%"] = round(100 * np.mean([d >= u for d in det]), 0) if det else np.nan
    res["falsos_%"] = round(100 * np.mean([f >= u for f in fp]), 0) if fp else np.nan
    return res


def comparar(precios, gpr=None, prima=None, gdelt=None,
             agregadores=("media", "iguales", "iguales_cos", "firma_cos")) -> dict:
    """Calcula el índice con cada agregador y compara dentro y fuera."""
    corte = config.FECHA_CORTE_CALIBRACION
    filas, resultados = [], {}

    for ag in agregadores:
        try:
            res = indice.calcular(precios, gpr=gpr, prima=prima, gdelt=gdelt,
                                  agregacion=ag)
        except Exception as exc:                      # noqa: BLE001
            print(f"  {ag}: fallo ({exc})")
            continue
        resultados[ag] = res
        ifg = res["tabla"]["ifg_suavizado"]
        for etiqueta, desde, hasta in [
            ("dentro (calibración)", None, corte),
            ("FUERA (validación)", corte, None),
        ]:
            fila = evaluar(ifg, desde, hasta, etiqueta)
            fila["agregador"] = ag
            filas.append(fila)

    tabla = pd.DataFrame(filas)
    if not tabla.empty:
        cols = ["agregador", "periodo", "n_hitos", "n_controles",
                "salto_hitos", "salto_controles", "separacion", "efecto_d",
                "p", "acierto_%", "falsos_%"]
        tabla = tabla[[c for c in cols if c in tabla.columns]]
    return {"tabla": tabla, "resultados": resultados}


def informe(comparacion: dict) -> str:
    lineas = []
    add = lineas.append
    tabla = comparacion["tabla"]
    corte = config.FECHA_CORTE_CALIBRACION

    add("=" * 92)
    add(f"COMPARACIÓN DE AGREGADORES · versión {config.VERSION}")
    add(f"Calibración: episodios anteriores a {corte} · "
        f"Validación: posteriores, nunca vistos al estimar la dirección")
    add("=" * 92)
    add("")
    add(tabla.to_string(index=False))

    add("\n\nLECTURA")
    for ag in tabla["agregador"].unique():
        sub = tabla[tabla["agregador"] == ag]
        dentro = sub[sub["periodo"].str.startswith("dentro")]
        fuera = sub[sub["periodo"].str.startswith("FUERA")]
        if dentro.empty or fuera.empty:
            continue
        sd = dentro["separacion"].iloc[0]
        sf = fuera["separacion"].iloc[0]
        pf = fuera["p"].iloc[0]
        caida = "" if pd.isna(sd) or pd.isna(sf) or sd == 0 else \
            f" (retiene el {100 * sf / sd:.0f} % de la separación)"
        veredicto = ("separa fuera de muestra" if pd.notna(pf) and pf < 0.10
                     else "NO separa fuera de muestra")
        add(f"  {ag:10s} dentro {sd:+.1f} · fuera {sf:+.1f}{caida} -> {veredicto}")

    # Dirección estimada
    for ag, res in comparacion["resultados"].items():
        if (res.get("diag_firma") or {}).get("direccion_cruda"):
            d = res["diag_firma"]
            add(f"\n\nDIRECCIÓN DISCRIMINANTE ({ag})")
            add(f"  Estimada con {d['hitos_calibracion']} hitos y "
                f"{d['controles_calibracion']} controles "
                f"({d['sesiones_hitos']} y {d['sesiones_controles']} sesiones)")
            add(f"  Encogimiento hacia pesos iguales: {d['encogimiento']:.0%}")
            comp = pd.DataFrame({
                "cruda": pd.Series(d["direccion_cruda"]),
                "final": pd.Series(d["direccion_final"]),
            }).sort_values("final", ascending=False)
            add(comp.to_string())
            add("  Un valor negativo significa que ese componente sube MÁS en las")
            add("  caídas de mercado que en los episodios geopolíticos: resta.")
            break

    add("\n" + "=" * 92)
    return "\n".join(lineas)
