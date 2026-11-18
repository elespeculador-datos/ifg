"""Comprobaciones sin red del indicador de divisas de exposición (14).

  python divisas/pruebas_divisas.py

CSV simulado con el formato del portal del BCE (csvdata) y valores conocidos: lectura y paradas, variaciones
de la divisa frente al euro (invertidas respecto al tipo unidades por euro), desde enero, cesta emergente
(media geométrica), percentil con caso de control contra scipy, huella, fragmento y escritura.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import divisas as dv  # noqa: E402

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 18)


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def csv_simulado(hasta: date = HOY, quitar: str | None = None, negativo: bool = False) -> str:
    """Días hábiles de 2023-01-02 a `hasta`. BRL sube linealmente de 5 a 6; MXN 20 y 19 el último día; TRY 40; USD 1,10 y 1,21 el último día; GBP 0,85."""
    dias = pd.bdate_range("2023-01-02", hasta)
    filas = ["KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS"]
    n = len(dias)
    for i, t in enumerate(dias):
        ultimo = t.date() == hasta
        valores = {"BRL": 5 + i / (n - 1), "MXN": 19.0 if ultimo else 20.0, "TRY": 40.0, "USD": 1.21 if ultimo else 1.10, "GBP": 0.85}
        if negativo and ultimo:
            valores["TRY"] = -1
        for d, v in valores.items():
            if d == quitar:
                continue
            filas.append(f"EXR.D.{d}.EUR.SP00.A,D,{d},EUR,SP00,A,{t.date().isoformat()},{v:.6f},A")
    return "\n".join(filas) + "\n"


def prueba_lectura():
    df = dv.leer(csv_simulado())
    ok(list(df.columns) == ["BRL", "MXN", "TRY", "USD", "GBP"] and df.index.max().date() == HOY, f"leer: columnas y última fecha: {list(df.columns)} {df.index.max()}")
    ok(abs(df["BRL"].iloc[0] - 5.0) < 1e-9 and abs(df["BRL"].iloc[-1] - 6.0) < 1e-9, "leer: valores")
    for texto, motivo in ((csv_simulado(quitar="TRY"), "falta una divisa"), (csv_simulado(negativo=True), "tipo no positivo"), ("a,b\n1,2\n", "sin columnas"), ("KEY,TIME_PERIOD,OBS_VALUE\n", "vacío")):
        try:
            dv.leer(texto)
            ok(False, f"leer: aceptado un CSV con {motivo}")
        except dv.DatosRaros:
            ok(True, "")
    return df


def prueba_calculo(df):
    fecha = pd.Timestamp(HOY)
    ok(abs(dv.variacion_divisa(df["USD"], fecha, 7) - (1.10 / 1.21 - 1) * 100) < 1e-9, "variación: el dólar se deprecia un 9,09 % cuando el tipo sube de 1,10 a 1,21")
    ok(abs(dv.variacion_divisa(df["MXN"], fecha, 7) - (20 / 19 - 1) * 100) < 1e-9, "variación: el peso se aprecia un 5,26 % cuando el tipo baja de 20 a 19")
    ok(dv.variacion_divisa(df["TRY"], fecha, 365) == 0.0 and dv.variacion_divisa(df["GBP"], fecha, 30) == 0.0, "variación: constantes, cero")
    ok(dv.variacion_divisa(df["BRL"], fecha, 7) < 0 and dv.variacion_divisa(df["BRL"], fecha, 365) < dv.variacion_divisa(df["BRL"], fecha, 30) < 0, "variación: el real se deprecia más cuanto más larga la ventana")
    cierre_2025 = float(df.loc[df.index <= pd.Timestamp("2025-12-31"), "BRL"].iloc[-1])
    ok(abs(dv.variacion_desde_enero(df["BRL"], fecha) - (cierre_2025 / 6.0 - 1) * 100) < 1e-9, "desde enero: contra el último dato de 2025")
    ok(dv.variacion_divisa(df["USD"], pd.Timestamp("2023-01-03"), 365) is None, "variación: sin dato anterior, nada")
    esperado = ((1.0 + 0) * (20 / 19) * 1.0) ** (1 / 3) - 1
    cesta = dv.cesta_variacion(df, fecha, 7)
    brl = 1 + dv.variacion_divisa(df["BRL"], fecha, 7) / 100
    esperado = (brl * (20 / 19) * 1.0) ** (1 / 3) - 1
    ok(abs(cesta / 100 - esperado) < 1e-9, f"cesta: media geométrica de las tres variaciones: {cesta:.4f} frente a {esperado * 100:.4f}")
    res = dv.calcular(df, HOY)
    ok(res["fecha"] == HOY.isoformat() and set(res["divisas"]) == set(dv.DIVISAS), "calcular: fecha y divisas")
    ok(res["divisas"]["BRL"]["percentil_euro_3a"] == 100.0 and res["divisas"]["MXN"]["percentil_euro_3a"] < 1, f"calcular: percentiles conocidos: {res['divisas']['BRL']['percentil_euro_3a']} {res['divisas']['MXN']['percentil_euro_3a']}")
    ok(res["divisas"]["USD"]["max_52s"] == 1.21 and res["divisas"]["USD"]["min_52s"] == 1.1 and res["divisas"]["USD"]["fecha_max_52s"] == HOY.isoformat(), f"calcular: máximo y mínimo de 52 semanas: {res['divisas']['USD']}")
    ok(res["mayor_movimiento_12m"] == "USD", f"calcular: mayor movimiento: {res['mayor_movimiento_12m']}")
    ok(res["divisas"]["USD"]["variaciones"]["1 semana"] == round((1.10 / 1.21 - 1) * 100, 2), "calcular: redondeo a dos decimales")
    # caso de control del percentil contra scipy
    try:
        from scipy import stats
        s = df["BRL"].tail(300)
        ok(abs(dv.percentil(s, float(s.iloc[-100])) - stats.percentileofscore(s, float(s.iloc[-100]), kind="weak")) < 1e-9, "percentil: coincide con scipy (weak)")
    except ImportError:
        print("aviso: scipy no está; caso de control no ejecutado")
    # desfase
    dv.AVISOS.clear()
    df6 = dv.leer(csv_simulado(hasta=HOY - timedelta(days=6)))
    dv.calcular(df6, HOY)
    ok(any("6 días" in a for a in dv.AVISOS), f"calcular: aviso con 6 días de desfase: {dv.AVISOS}")
    try:
        dv.calcular(dv.leer(csv_simulado(hasta=HOY - timedelta(days=11))), HOY)
        ok(False, "calcular: 11 días de desfase aceptados")
    except dv.DatosRaros:
        ok(True, "")
    res["huella"] = dv.huella(res)
    ok(res["huella"] == dv.huella(res) and len(res["huella"]) == 12, "huella: estable")
    res2 = dv.calcular(df, HOY)
    res2["divisas"]["USD"]["tipo"] = 1.2
    ok(dv.huella(res2) != res["huella"], "huella: cambia con el tipo")
    return res


def prueba_escribir(df, res):
    raiz = Path(tempfile.mkdtemp())
    salida = raiz / "divisas"
    ok(dv.escribir(df, res, HOY, salida), "escribir: primera vez")
    frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
    ok(frag.startswith(f"<!-- divisas:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- divisas:fin -->"), "fragmento: marcas")
    ok("Tipos en unidades de divisa por euro" in frag and "cesta emergente del IBEX" in frag and "<svg" in frag and frag.count("<polyline") == 5, "fragmento: texto, tabla y gráfico con cinco líneas")
    ok("−9,1 %" in frag and "+5,3 %" in frag, f"fragmento: variaciones con signo tipográfico")
    ok("zona más débil de tres años" in frag and "no es asesoramiento" in frag and "sin predicción" in frag, "fragmento: zonas y avisos")
    ok('<script type="application/ld+json">' in frag, "fragmento: JSON-LD")
    j = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
    ok(j["version"] == dv.VERSION and j["huella"] == res["huella"] and j["cesta"]["divisas"] == ["BRL", "MXN", "TRY"], "JSON")
    serie = pd.read_csv(salida / "datos" / "serie.csv")
    ok(list(serie.columns) == ["fecha", "divisa", "unidades_por_euro"] and len(serie) == df.notna().sum().sum(), "CSV largo")
    ok(not dv.escribir(df, res, HOY + timedelta(days=1), salida), "escribir: misma huella, no reescribe")
    ok("Comprobado el 18/11/2026" in (salida / "index.html").read_text(encoding="utf-8"), "index.html")


if __name__ == "__main__":
    df = prueba_lectura()
    res = prueba_calculo(df)
    prueba_escribir(df, res)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
