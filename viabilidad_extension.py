# -*- coding: utf-8 -*-
"""
¿Hasta dónde llega de verdad la extensión hacia atrás? Respuesta: poco.

Cruza el sondeo real de fuentes (datos/sonda_historia.csv, obtenido en
Actions el 18 de octubre de 2026) con la estructura de componentes y el
calentamiento de la normalización, para decidir con hechos qué cobertura se
alcanza en cada fecha y qué hitos del pre-registro resultan evaluables.

CONCLUSIÓN, QUE CONTRADICE LA EXPECTATIVA CON LA QUE SE ESCRIBIÓ EL
PRE-REGISTRO: ninguno. Cero hitos mayores de la muestra 1996-2009 queda
evaluable, ni exigiendo el 50 % de cobertura ni el 70 %. El cuello de botella
no era ACWI: son el cobre y el trigo, que en esta fuente arrancan en agosto y
julio de 2000, y los cruces del euro, que arrancan en enero de 2003. Sumado
el calentamiento, la serie no es utilizable antes de 2009.

Lo que el arreglo de ACWI sí consigue, y no es poco, es elevar la cobertura
del tramo YA PUBLICADO: en enero de 2010 pasaría de un 15 % a del orden del
75 %. Mejora el producto; no desbloquea la validación.

ADVERTENCIA SOBRE LA PRECISIÓN. El calentamiento se modela aquí como una
constante de ~3,5 años, que es el apilamiento medido para los componentes en
modo "mixto". Los que usan modo "nivel", como vol_energia, calientan menos:
el dato real muestra que ese componente arranca antes de lo que esta
aproximación predice. Las fechas de abajo son por tanto orientativas y
conservadoras; las definitivas solo salen del recálculo completo.
"""

from __future__ import annotations

import sys

import pandas as pd

import config                    # noqa: E402
import muestra_1996_2009 as pre  # noqa: E402

S = pd.read_csv("datos/sonda_historia.csv")
S = S[S["desde"].notna()].set_index("clave")
ini = pd.to_datetime(S["desde"])

# Calentamiento medido en la auditoría: transformar (impulso/estado + z-score)
# + neutralización de beta + z-score posterior. ~900 sesiones ~ 3,5 años.
CALENT = pd.Timedelta(days=int(365.25 * 3.5))

FUENTES_EXTERNAS = {
    "prima": pd.Timestamp("2004-09-06"),   # medido en datos/prima.csv
    "gpr":   pd.Timestamp("1985-01-01"),   # medido en datos/gpr.csv
    "gdelt": pd.Timestamp("2015-01-01"),   # conservador: depende del backfill
}

# Qué series necesita cada componente, YA con las sustituciones de la
# precondición aplicadas. La lista es conjuntiva: manda la más tardía.
NECESITA = {
    "energia":     ["wti", "cobre"],
    "vol_energia": ["ovx"],                        # vstoxx: sin datos en Yahoo
    "refugios":    ["oro", "sp500", "eurchf", "eurjpy"],
    "defensa":     ["rheinmetall", "bae", "thales", "dassault_av",
                    "indra", "leonardo", "stoxx600"],
    "prima":       [],
    "transporte":  ["iag", "amadeus", "ibex"],
    "fletes":      ["nordic", "frontline", "dht"],
    "grano":       ["trigo"],
    "gas":         ["gas_ttf"],
    "gdelt":       [],
    "gpr":         [],
}


def disponible_desde(comp: str) -> pd.Timestamp:
    fechas = []
    for s in NECESITA[comp]:
        if s in ini.index:
            fechas.append(ini[s])
        else:
            return pd.Timestamp("2100-01-01")
    if comp in FUENTES_EXTERNAS:
        fechas.append(FUENTES_EXTERNAS[comp])
    if not fechas:
        return pd.Timestamp("2100-01-01")
    return max(fechas)


print("=" * 84)
print("1. CUÁNDO EMPIEZA A EMITIR CADA COMPONENTE, TRAS EL CALENTAMIENTO")
print("=" * 84)
print(f"{'componente':>12} {'peso':>5}  {'fuente desde':>13}  {'emite desde':>13}"
      f"  serie que manda")
filas = []
for c, w in sorted(config.PESOS.items(), key=lambda kv: -kv[1]):
    if c not in NECESITA:
        continue
    d = disponible_desde(c)
    emite = d + CALENT
    manda = ""
    if NECESITA[c]:
        cand = {s: ini[s] for s in NECESITA[c] if s in ini.index}
        if c in FUENTES_EXTERNAS:
            cand[c] = FUENTES_EXTERNAS[c]
        if cand:
            manda = max(cand, key=cand.get)
    elif c in FUENTES_EXTERNAS:
        manda = f"{c} (externa)"
    print(f"{c:>12} {w:>5}  {str(d.date()):>13}  {str(emite.date()):>13}  {manda}")
    filas.append({"comp": c, "peso": w, "emite": emite})

t = pd.DataFrame(filas).sort_values("emite")
total = t["peso"].sum()

print()
print("=" * 84)
print("2. COBERTURA DE PESO ALCANZADA EN CADA FECHA")
print("=" * 84)
acum = 0
for _, r in t.iterrows():
    acum += r["peso"]
    print(f"  desde {str(r['emite'].date()):>12}:  cobertura {acum/total:>5.0%}"
          f"   (entra {r['comp']}, +{r['peso']} puntos)")

print()
print("=" * 84)
print("3. QUÉ HITOS DEL PRE-REGISTRO RESULTAN EVALUABLES")
print("=" * 84)
for umbral, etiq in ((0.50, "cobertura >= 50 %"), (0.70, "cobertura >= 70 %")):
    acum, fecha_u = 0, None
    for _, r in t.iterrows():
        acum += r["peso"]
        if acum / total >= umbral:
            fecha_u = r["emite"]
            break
    print(f"\n  --- Con {etiq}: serie utilizable desde {fecha_u.date()} ---")
    may_ok, may_tot, ctrl_ok = [], 0, []
    for f, et, mayor in pre.HITOS:
        if mayor:
            may_tot += 1
        if pd.Timestamp(f) >= fecha_u:
            if mayor:
                may_ok.append((f, et))
    for f, et in pre.CONTROLES:
        if pd.Timestamp(f) >= fecha_u:
            ctrl_ok.append((f, et))
    print(f"    hitos MAYORES evaluables: {len(may_ok)} de {may_tot}")
    for f, et in may_ok:
        print(f"        {f}  {et}")
    print(f"    controles evaluables: {len(ctrl_ok)} de {len(pre.CONTROLES)}")
    for f, et in ctrl_ok:
        print(f"        {f}  {et}")
