# -*- coding: utf-8 -*-
"""
Validación fuera de muestra del IFG sobre el pre-registro 1996-2009.

ESTO SE EJECUTA UNA SOLA VEZ. No es un script de exploración: es la prueba.
Lee las listas congeladas de muestra_1996_2009.py, construye las dos
especificaciones pre-registradas, las evalúa con los umbrales de
config.UMBRALES sin tocar ninguno, aplica la regla de decisión fijada de
antemano e imprime el informe completo de las dos, pase lo que pase.

Si el resultado no gusta, NO se retoca nada y se vuelve a ejecutar. Esa es
toda la diferencia entre esto y lo que agotó la muestra anterior.

Ver PROTOCOLO_VALIDACION.md, secciones 6, 9, 10 y 11.

-----------------------------------------------------------------------------
POR QUÉ NO SE USA validacion.test_hitos
-----------------------------------------------------------------------------
validacion._ventana localiza la fecha con searchsorted y no comprueba que el
hito caiga dentro del rango de la serie. Para un hito anterior al inicio,
searchsorted devuelve 0 y la función evalúa la ventana del PRINCIPIO de la
serie, devolviendo un número con aspecto de válido. Con una muestra que
arranca en 1996 y una serie que empezará bastante después, eso contaminaría
casi todas las filas. Aquí un hito solo cuenta si su fecha cae dentro del
rango, con margen para la ventana completa; si no, se marca NO EVALUABLE y se
excluye de las tasas.

Uso:
    python validar_muestra_nueva.py                 # datos de datos/
    python validar_muestra_nueva.py --salida informe_validacion.txt
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import config
import indice
import muestra_1996_2009 as pre

U = config.UMBRALES
NIVEL = U["nivel_activacion"]
VENT = U["ventana_hito"]

# El titular pasa a ser el valor crudo (protocolo 7.1). La validación usa la
# misma serie que se publica: validar una cifra distinta de la publicada es
# justamente el error que la auditoría de cobertura encontró.
COLUMNA_OFICIAL = "ifg"


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def cargar_datos(dir_datos: str = "datos"):
    p = pd.read_csv(f"{dir_datos}/precios.csv", index_col=0, parse_dates=True)
    try:
        g = pd.read_csv(f"{dir_datos}/gpr.csv", index_col=0,
                        parse_dates=True)["gpr"]
    except FileNotFoundError:
        g = None
    try:
        pr = pd.read_csv(f"{dir_datos}/prima.csv", index_col=0,
                         parse_dates=True).iloc[:, 0]
    except FileNotFoundError:
        pr = None
    gd = None
    for nombre in ("gdelt_conflicto_diario.parquet", "gdelt.csv"):
        ruta = f"{dir_datos}/{nombre}"
        try:
            if nombre.endswith(".parquet"):
                gd = pd.read_parquet(ruta).iloc[:, 0]
            else:
                gd = pd.read_csv(ruta, index_col=0, parse_dates=True).iloc[:, 0]
            break
        except Exception:
            continue
    return p, g, pr, gd


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------
def ventana_estricta(s: pd.Series, fecha: str) -> pd.Series | None:
    """Ventana del hito, o None si el hito no cae dentro de la serie."""
    f = pd.Timestamp(fecha)
    if s.empty or f < s.index[0] or f > s.index[-1]:
        return None
    pos = s.index.searchsorted(f)
    v = s.iloc[max(0, pos + VENT[0]): min(len(s), pos + VENT[1] + 1)].dropna()
    return v if len(v) else None


def evaluar(ifg: pd.Series, hitos: list, controles: list,
            vix: pd.Series | None, gpr: pd.Series | None) -> dict:
    det_hitos, det_ctrl = [], []

    for fecha, etiqueta, mayor in hitos:
        v = ventana_estricta(ifg, fecha)
        det_hitos.append({
            "fecha": fecha, "evento": etiqueta, "mayor": mayor,
            "maximo": np.nan if v is None else round(float(v.max()), 1),
            "evaluable": v is not None,
            "detectado": None if v is None else bool(v.max() >= NIVEL),
        })

    for fecha, etiqueta in controles:
        v = ventana_estricta(ifg, fecha)
        det_ctrl.append({
            "fecha": fecha, "evento": etiqueta,
            "maximo": np.nan if v is None else round(float(v.max()), 1),
            "evaluable": v is not None,
            "falso": None if v is None else bool(v.max() >= U["nivel_falso_positivo"]),
        })

    th = pd.DataFrame(det_hitos)
    tc = pd.DataFrame(det_ctrl)

    may = th[th["mayor"] & th["evaluable"]]
    ctr = tc[tc["evaluable"]]

    res = {
        "tabla_hitos": th, "tabla_controles": tc,
        "n_mayores": len(may),
        "acierto": float(may["detectado"].mean()) if len(may) else np.nan,
        "n_controles": len(ctr),
        "falsos": float(ctr["falso"].mean()) if len(ctr) else np.nan,
        "corr_vix": None, "corr_gpr": None,
    }

    # Sin el Brexit, que solo existe en la muestra vieja. Se publica como
    # análisis de sensibilidad declarado, nunca en sustitución (protocolo 7.2).
    sin_brexit = may[~may["evento"].str.contains("Brexit", case=False, na=False)]
    res["acierto_sin_brexit"] = (float(sin_brexit["detectado"].mean())
                                 if len(sin_brexit) else np.nan)
    res["n_mayores_sin_brexit"] = len(sin_brexit)

    if vix is not None:
        al = pd.concat([ifg.rename("ifg"), vix.rename("vix")],
                       axis=1, sort=False).sort_index().dropna()
        if len(al) > 250:
            res["corr_vix"] = round(float(al.diff().dropna().corr().iloc[0, 1]), 3)
    if gpr is not None:
        al = pd.concat([ifg.rename("ifg"), gpr.rename("gpr")],
                       axis=1, sort=False).sort_index().dropna()
        if len(al) > 250:
            res["corr_gpr"] = round(float(al.corr().iloc[0, 1]), 3)

    return res


def fallos_umbral(r: dict) -> list[str]:
    """Contra los umbrales congelados. Ninguno se reinterpreta aquí."""
    f = []
    if np.isnan(r["acierto"]):
        f.append("sin hitos mayores evaluables")
    elif r["acierto"] < U["tasa_acierto_minima"]:
        f.append(f"sensibilidad {r['acierto']:.0%} < "
                 f"{U['tasa_acierto_minima']:.0%}")
    if not np.isnan(r["falsos"]) and r["falsos"] > U["tasa_falsos_maxima"]:
        f.append(f"falsos positivos {r['falsos']:.0%} > "
                 f"{U['tasa_falsos_maxima']:.0%}")
    if r["corr_vix"] is not None and r["corr_vix"] > U["corr_max_vix_variaciones"]:
        f.append(f"corr. VIX {r['corr_vix']:.2f} > "
                 f"{U['corr_max_vix_variaciones']}")
    if r["corr_gpr"] is not None:
        if r["corr_gpr"] < U["corr_min_gpr_niveles"]:
            f.append(f"corr. GPR {r['corr_gpr']:.2f} < "
                     f"{U['corr_min_gpr_niveles']}")
        elif r["corr_gpr"] > U["corr_max_gpr_niveles"]:
            f.append(f"corr. GPR {r['corr_gpr']:.2f} > "
                     f"{U['corr_max_gpr_niveles']}")
    return f


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
def bloque(titulo: str) -> str:
    return "\n" + "=" * 78 + f"\n{titulo}\n" + "=" * 78


def informe_especificacion(clave: str, r: dict, muestra: str) -> str:
    L = [bloque(f"{clave} — {pre.ESPECIFICACIONES[clave]['descripcion']}"
                f"\nMuestra: {muestra}")]
    ac = "n/d" if np.isnan(r["acierto"]) else f"{r['acierto']:.0%}"
    fa = "n/d" if np.isnan(r["falsos"]) else f"{r['falsos']:.0%}"
    L.append(f"  A. sensibilidad ......... {ac:>6}  "
             f"({r['n_mayores']} hitos mayores evaluables)"
             f"   [umbral >= {U['tasa_acierto_minima']:.0%}]")
    if r["n_mayores_sin_brexit"] != r["n_mayores"]:
        asb = ("n/d" if np.isnan(r["acierto_sin_brexit"])
               else f"{r['acierto_sin_brexit']:.0%}")
        L.append(f"     sin el Brexit ........ {asb:>6}  "
                 f"({r['n_mayores_sin_brexit']} hitos)"
                 f"   [declarado, NO sustituye al anterior]")
    L.append(f"  B. falsos positivos ..... {fa:>6}  "
             f"({r['n_controles']} controles evaluables)"
             f"   [umbral <= {U['tasa_falsos_maxima']:.0%}]")
    cv = "n/d" if r["corr_vix"] is None else f"{r['corr_vix']:+.3f}"
    cg = "n/d" if r["corr_gpr"] is None else f"{r['corr_gpr']:+.3f}"
    L.append(f"  C. corr. VIX (variac.) .. {cv:>6}"
             f"   [umbral <= {U['corr_max_vix_variaciones']}]")
    L.append(f"     corr. GPR (niveles) .. {cg:>6}"
             f"   [banda {U['corr_min_gpr_niveles']}–{U['corr_max_gpr_niveles']}]")

    f = fallos_umbral(r)
    L.append(f"  VEREDICTO ............... "
             f"{'CUMPLE LOS CUATRO UMBRALES' if not f else 'NO CUMPLE: ' + '; '.join(f)}")

    L.append("\n  Detalle hito por hito:")
    L.append(f"  {'fecha':>12} {'máximo':>7} {'det.':>5}  evento")
    for _, h in r["tabla_hitos"].iterrows():
        if not h["evaluable"]:
            marca, mx = "  n/ev", "    n/d"
        else:
            marca = "   SÍ" if h["detectado"] else "   no"
            mx = f"{h['maximo']:>7.1f}"
        L.append(f"  {h['fecha']:>12} {mx} {marca:>5}  "
                 f"{'[MAYOR] ' if h['mayor'] else ''}{h['evento']}"
                 f"{'' if h['evaluable'] else '   <- NO EVALUABLE'}")

    L.append("\n  Controles (un máximo >= "
             f"{U['nivel_falso_positivo']} es falso positivo):")
    for _, c in r["tabla_controles"].iterrows():
        if not c["evaluable"]:
            L.append(f"  {c['fecha']:>12}     n/d        {c['evento']}"
                     f"   <- NO EVALUABLE")
        else:
            L.append(f"  {c['fecha']:>12} {c['maximo']:>7.1f} "
                     f"{'  FALSO+' if c['falso'] else '     ok'}  {c['evento']}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--salida", default=None,
                    help="archivo donde guardar el informe íntegro")
    args = ap.parse_args()

    p, g, pr, gd = cargar_datos(args.datos)

    L = [bloque("VALIDACIÓN FUERA DE MUESTRA DEL IFG")]
    L.append(f"  Índice ..................... versión {config.VERSION}")
    L.append(f"  Pre-registro de la muestra . {pre.FECHA_PRE_REGISTRO}")
    L.append(f"  Factor de mercado .......... {config.FACTOR_MERCADO}")
    L.append(f"  Serie oficial evaluada ..... {COLUMNA_OFICIAL} "
             f"(valor crudo, protocolo 7.1)")
    L.append(f"  Precios disponibles ........ {p.index[0].date()} -> "
             f"{p.index[-1].date()}")
    L.append(f"  GDELT disponible ........... "
             f"{'sí' if gd is not None else 'NO (E1 no será evaluable)'}")

    resultados = {}
    for clave in pre.PREFERENCIA:
        spec = pre.ESPECIFICACIONES[clave]
        usa = spec["usar_gdelt"]
        res = indice.calcular(p, gpr=g, prima=pr,
                              gdelt=gd if usa else None)
        ifg = res["tabla"][COLUMNA_OFICIAL].dropna()
        if ifg.empty:
            L.append(f"\n  {clave}: el índice no emite ningún valor. "
                     f"Revisar datos de entrada.")
            continue

        vix = p["vix"] if "vix" in p.columns else None
        r_nueva = evaluar(ifg, pre.HITOS, pre.CONTROLES, vix, g)
        r_vieja = evaluar(ifg, config.HITOS, config.CONTROLES, vix, g)
        resultados[clave] = r_nueva

        L.append(informe_especificacion(
            clave, r_nueva, f"PRE-REGISTRADA 1996-2009 (fuera de muestra) — "
                            f"índice desde {ifg.index[0].date()}"))
        L.append(informe_especificacion(
            clave, r_vieja, "ANTERIOR 2010-2026 (AGOTADA: informativa, "
                            "no decide nada)"))

    # --- regla de decisión pre-registrada ----------------------------------
    L.append(bloque("REGLA DE DECISIÓN (protocolo 11.3, fijada de antemano)"))
    cumplen = [k for k in pre.PREFERENCIA
               if k in resultados and not fallos_umbral(resultados[k])]
    if len(cumplen) == 1:
        L.append(f"  Cumple una sola especificación: {cumplen[0]}.")
        L.append(f"  -> {cumplen[0]} es la especificación del índice. "
                 f"Pasa a 1.0.0.")
    elif len(cumplen) == 2:
        L.append("  Cumplen las dos. Ante empate manda la vigente.")
        L.append(f"  -> {pre.PREFERENCIA[0]} es la especificación del índice. "
                 f"Pasa a 1.0.0.")
    else:
        L.append("  No cumple ninguna de las dos.")
        L.append("  -> El índice NO pasa a 1.0.0. Se aplica la tabla de la "
                 "sección 10 sobre E1,")
        L.append("     que es la especificación vigente, y se publica el "
                 "suspenso de las dos.")
    L.append("\n  Recordatorio: este resultado no se repite ni se retoca. "
             "La muestra queda")
    L.append("  agotada a partir de aquí; lo único limpio que resta es la "
             "validación prospectiva.")

    texto = "\n".join(L)
    print(texto)
    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
        print(f"\nInforme guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
