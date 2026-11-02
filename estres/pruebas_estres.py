"""
Comprobaciones del indicador de estrés financiero. No tocan la red.

Regla 7 del catálogo: el cálculo con datos simulados recupera valores conocidos y
un caso de control coincide con una librería estadística de referencia (scipy, si
está instalada; numpy en su defecto).

Uso:  python estres/pruebas_estres.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import estres as e  # noqa: E402

fallos: list[str] = []


def comprobar(descripcion: str, condicion: bool) -> None:
    print(("  ok  " if condicion else "FALLO ") + descripcion)
    if not condicion:
        fallos.append(descripcion)


# --------------------------------------------------------------- datos simulados
HOY = date(2026, 11, 2)
rng = np.random.default_rng(7)


def serie_simulada(desde: str, base: float, picos: dict[str, float]) -> pd.Series:
    idx = pd.bdate_range(desde, "2026-10-29")
    v = np.clip(base + rng.normal(0, 0.02, len(idx)), 0.01, 0.95)
    s = pd.Series(v, index=idx)
    for f, alto in picos.items():
        s.loc[pd.Timestamp(f)] = alto
    return s


PICOS_ES = {"2008-10-10": 0.80, "2012-07-25": 0.85, "2020-03-18": 0.70, "2022-03-07": 0.55, "1992-09-16": 0.60}
SIM = {
    "es": serie_simulada("1980-01-02", 0.12, PICOS_ES),
    "ea": serie_simulada("1999-01-04", 0.14, {"2008-10-10": 0.78}),
    "de": serie_simulada("1999-01-04", 0.10, {}),
    "fr": serie_simulada("1999-01-04", 0.11, {}),
    "it": serie_simulada("1999-01-04", 0.16, {}),
    "es_sob": serie_simulada("2000-01-03", 0.20, {"2012-07-25": 0.90}),
}


def csv_portal(series: dict[str, pd.Series]) -> str:
    filas = ["KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,OBS_STATUS"]
    for n, s in series.items():
        zona, ind = e.SERIES[n]
        clave = f"CISS.D.{zona}.Z0Z.4F.EC.{ind}.IDX"
        for t, v in s.items():
            filas.append(f"{clave},D,{zona},{t.date().isoformat()},{v:.6f},A")
    return "\n".join(filas) + "\n"


texto = csv_portal(SIM)
df = e.leer(texto)
comprobar("leer(): reconoce las seis series simuladas", set(df["serie"]) == set(SIM))
comprobar("leer(): conserva todas las observaciones", len(df) == sum(len(s) for s in SIM.values()))

# --------------------------------------------------------------- percentil
s100 = pd.Series(np.arange(1, 101, dtype=float))
comprobar("percentil(): 50 en 1..100 es el percentil 50", abs(e.percentil(s100, 50) - 50.0) < 1e-9)
comprobar("percentil(): el máximo es el percentil 100", abs(e.percentil(s100, 100) - 100.0) < 1e-9)
comprobar("percentil(): por debajo del mínimo es 0", abs(e.percentil(s100, 0.5) - 0.0) < 1e-9)
aleatoria = pd.Series(rng.normal(size=5000))
valor = float(aleatoria.iloc[123])
try:
    from scipy.stats import percentileofscore
    referencia = float(percentileofscore(aleatoria.to_numpy(), valor, kind="weak"))
    libreria = "scipy percentileofscore(kind='weak')"
except ImportError:
    referencia = float(np.mean(aleatoria.to_numpy() <= valor) * 100)
    libreria = "numpy"
comprobar(f"percentil(): coincide con la referencia ({libreria})", abs(e.percentil(aleatoria, valor) - referencia) < 1e-9)
comprobar("tramo(): 95 → muy alto, 80 → alto, 60 → por encima de lo habitual, 30 → habitual, 10 → bajo",
          [e.tramo(p) for p in (95, 80, 60, 30, 10)] == ["muy alto", "alto", "por encima de lo habitual", "habitual", "bajo"])

# --------------------------------------------------------------- variación y última vez
idx = pd.bdate_range("2026-01-01", "2026-10-29")
lineal = pd.Series(np.arange(len(idx), dtype=float) / 1000, index=idx)  # sube 0,001 por sesión
f = lineal.index[-1]
v7 = e.variacion(lineal, f, 7)
comprobar("variacion(): a 7 días son cinco sesiones (0,005) en una serie que sube 0,001 por sesión", v7 is not None and abs(v7 - 0.005) < 1e-9)
comprobar("variacion(): sin dato anterior devuelve None", e.variacion(lineal.iloc[:3], lineal.index[2], 30) is None)
escalera = pd.Series([0.5] * 50 + [0.1] * 300, index=pd.bdate_range("2024-01-01", periods=350))
ult = e.ultima_vez_igual_o_mayor(escalera, escalera.index[-1], 0.1, margen_dias=180)
comprobar("ultima_vez_igual_o_mayor(): ignora los últimos seis meses", ult is not None and pd.Timestamp(ult) <= escalera.index[-1] - pd.Timedelta(days=180))
comprobar("ultima_vez_igual_o_mayor(): None si nunca estuvo tan alto", e.ultima_vez_igual_o_mayor(escalera, escalera.index[-1], 0.99) is None)

# --------------------------------------------------------------- episodios y cálculo completo
ep = {x["episodio"]: x for x in e.episodios(SIM["es"])}
comprobar("episodios(): encuentra el pico de Lehman en su fecha", ep["Quiebra de Lehman Brothers"]["fecha_maximo"] == "2008-10-10" and ep["Quiebra de Lehman Brothers"]["maximo"] == 0.8)
comprobar("episodios(): encuentra el pico de la crisis del euro", ep["Crisis del euro"]["fecha_maximo"] == "2012-07-25")
comprobar("episodios(): cinco episodios con dato", len(ep) == 5)

e.AVISOS.clear()
res = e.calcular(df, HOY)
es = res["series"]["es"]
comprobar("calcular(): la fecha del dato es la última de la serie", es["fecha"] == "2026-10-29")
comprobar("calcular(): el máximo histórico de España es el pico de 2012", es["maximo"] == 0.85 and es["fecha_maximo"] == "2012-07-25")
comprobar("calcular(): avisa del desfase solo si pasa de 10 días (aquí, 4)", res["desfase_dias"] == 4 and not e.AVISOS)
comprobar("calcular(): el gráfico cubre tres años de España y zona euro", set(res["grafico"]) == {"es", "ea"} and res["grafico"]["es"].index[0] >= pd.Timestamp("2023-11-01"))

viejo = {n: s[s.index <= "2026-09-10"] for n, s in SIM.items()}
try:
    e.calcular(e.leer(csv_portal(viejo)), HOY)
    comprobar("calcular(): más de 45 días sin dato → DatosRaros", False)
except e.DatosRaros:
    comprobar("calcular(): más de 45 días sin dato → DatosRaros", True)

# --------------------------------------------------------------- guardas de lectura
try:
    e.leer(csv_portal({k: v for k, v in SIM.items() if k != "es"}))
    comprobar("leer(): sin España → DatosRaros", False)
except e.DatosRaros:
    comprobar("leer(): sin España → DatosRaros", True)
fuera = {k: v.copy() for k, v in SIM.items()}
fuera["de"].iloc[10] = 1.7
try:
    e.leer(csv_portal(fuera))
    comprobar("leer(): un valor fuera de 0-1 → DatosRaros", False)
except e.DatosRaros:
    comprobar("leer(): un valor fuera de 0-1 → DatosRaros", True)

# --------------------------------------------------------------- huella y fragmento
h1 = e.huella(res)
res2 = e.calcular(e.leer(texto), HOY)
comprobar("huella(): estable entre dos cálculos iguales", h1 == e.huella(res2))
cambiado = {k: v.copy() for k, v in SIM.items()}
cambiado["es"].iloc[-1] = cambiado["es"].iloc[-1] + 0.01
res3 = e.calcular(e.leer(csv_portal(cambiado)), HOY)
comprobar("huella(): cambia si cambia el último dato", h1 != e.huella(res3))
frag = e.fragmento(res, HOY.isoformat())
comprobar("fragmento(): una marca de inicio con la huella y una de fin", frag.count(f"<!-- estres:inicio {h1} -->") == 1 and frag.count("<!-- estres:fin -->") == 1)
comprobar("fragmento(): sin «$» (lo exige el escenario de Make)", "$" not in frag)
comprobar("fragmento(): lleva el gráfico SVG y las tres tablas", frag.count("<svg") == 1 and frag.count("<figure class=\"wp-block-table\">") == 3)
comprobar("fragmento(): cita al BCE y declara los cálculos propios", "Fuente: BCE" in frag and "cálculos" in frag)

# --------------------------------------------------------------- escritura completa
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    salida = Path(tmp) / "estres"
    cambia1 = e.escribir(df, res, HOY, salida)
    cambia2 = e.escribir(df, e.calcular(e.leer(texto), HOY), HOY, salida)
    comprobar("escribir(): la primera vez hay datos nuevos; la segunda, con los mismos datos, no", cambia1 and not cambia2)
    comprobar("escribir(): deja los cuatro ficheros", all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv", "datos/ultima.json")))
    import json  # noqa: E402
    u = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
    comprobar("escribir(): ultima.json lleva versión, huella y las series", u["version"] == e.VERSION and u["huella"] == h1 and "es" in u["series"])

print()
if fallos:
    print(f"{len(fallos)} comprobación(es) han fallado.")
    sys.exit(1)
print("Todas las comprobaciones pasan.")
