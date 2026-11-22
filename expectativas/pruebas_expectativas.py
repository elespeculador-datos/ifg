"""Comprobaciones sin red del indicador de expectativas de los hogares (20c).

  python expectativas/pruebas_expectativas.py

CSV simulado con el formato del portal del BCE (csvdata, conjunto CES) y un serie.csv de ahorro con el IPC,
con valores conocidos: lectura y paradas, fichas (variaciones, percentil), brecha de percepción, acierto a
doce meses, huella, fragmento y escritura.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import expectativas as ex  # noqa: E402

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 18)


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def meses(desde="2020-04", hasta="2026-09"):
    out, a, m = [], int(desde[:4]), int(desde[5:])
    while f"{a:04d}-{m:02d}" <= hasta:
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, a = 1, a + 1
    return out


def csv_ces(hasta="2026-09", sin_es=False, loco=False) -> str:
    filas = ["KEY,FREQ,REF_AREA,CES_BREAKDOWN,CES_CUSTOM,CES_VARIABLE,CES_ANSWER,CES_DENOM,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE"]
    ms = meses(hasta=hasta)
    for i, mes in enumerate(ms):
        # España: expectativa a 12 meses sube 0,01 al mes desde 2,0, salvo los valores fijados
        fijos = {"2026-09": 3.8, "2026-08": 3.1, "2025-09": 2.5}
        valores = {("ES", "C1120"): fijos.get(mes, 2.0 + i * 0.01), ("ES", "C1020"): 4.4 if mes == "2026-09" else 3.0, ("ES", "C1220"): 3.2, ("ES", "E2020"): 3.0,
                   ("ES", "C1150_UNCERT"): 2.2, ("ES", "C2120"): 4.1, ("ES", "C3220"): 1.8, ("ES", "C6120"): 2.7, ("ES", "C4020"): 0.6, ("ES", "C4031"): 10.5, ("ES", "C5111"): 3.5,
                   ("Z18", "C1120"): 3.1 if mes >= "2022-04" else None, ("Z18", "C1020"): 3.3 if mes >= "2022-04" else None, ("DE", "C1120"): 2.9, ("FR", "C1120"): 2.9, ("IT", "C1120"): 4.4}
        if loco and mes == "2026-09":
            valores[("ES", "C1120")] = 99.0
        for (area, var), v in valores.items():
            if v is None or (sin_es and area == "ES"):
                continue
            filas.append(f"CES.M.{area}.ALL.T.{var}.NUM_VAR.WM,M,{area},ALL,T,{var},NUM_VAR,WM,{mes},{v},A,titulo")
    return "\n".join(filas) + "\n"


def csv_ipc(raiz: Path) -> Path:
    p = raiz / "ahorro" / "datos" / "serie.csv"
    p.parent.mkdir(parents=True)
    filas = ["mes,serie,valor"] + [f"{m},ipc,{4.9 if m == '2026-09' else 3.0}" for m in meses("2023-01", "2026-10")] + [f"{m},es_vista,0.16" for m in meses("2023-01", "2026-09")]
    p.write_text("\n".join(filas) + "\n", encoding="utf-8")
    return p


def prueba_lectura():
    df = ex.leer(csv_ces())
    ok(set(df["area"]) == set(ex.AREAS) and set(df["variable"]) == set(ex.VARIABLES), "leer: áreas y variables")
    ok(len(df[(df["area"] == "ES") & (df["variable"] == "C1120")]) == 78 and df["mes"].max() == "2026-09", "leer: 78 meses de España hasta 2026-09")
    for texto, motivo in ((csv_ces(sin_es=True), "sin España"), (csv_ces(loco=True), "valor fuera de rango"), ("a,b\n1,2\n", "sin columnas"), ("KEY,TIME_PERIOD,OBS_VALUE\n", "vacío")):
        try:
            ex.leer(texto)
            ok(False, f"leer: aceptado un CSV {motivo}")
        except ex.DatosRaros:
            ok(True, "")
    return df


def prueba_calculo(df):
    raiz = Path(tempfile.mkdtemp())
    ipc = ex.leer_ipc(csv_ipc(raiz))
    ok(ipc is not None and ipc.loc["2026-09"] == 4.9 and ipc.index.max() == "2026-10", f"leer_ipc: serie del INE desde ahorro: {None if ipc is None else ipc.tail(2).to_dict()}")
    ok(ex.leer_ipc(raiz / "no_existe.csv") is None, "leer_ipc: sin fichero, nada")
    ex.AVISOS.clear()
    res = ex.calcular(df, ipc, HOY)
    e = res["fichas"]["ES"]["C1120"]
    ok(res["mes"] == "2026-09" and e["valor"] == 3.8 and e["variacion_1m"] == 0.7 and e["variacion_12m"] == 1.3, f"calcular: ficha de la expectativa a 12 meses: {e}")
    ok(e["percentil"] == 100.0 and e["max"] == 3.8 and e["mes_max"] == "2026-09" and e["min"] == 2.0 and e["mes_min"] == "2020-04", f"calcular: percentil y extremos: {e}")
    ok(res["ipc"] == {"mes": "2026-09", "valor": 4.9} and res["brecha_percepcion"] == -0.5, f"calcular: brecha de percepción (4,4 percibida frente a 4,9 real): {res['ipc']} {res['brecha_percepcion']}")
    ok(res["acierto_12m"] == {"mes_expectativa": "2025-09", "esperado": 2.5, "ipc_real": 4.9, "diferencia": -2.4}, f"calcular: acierto a 12 meses: {res['acierto_12m']}")
    ok(res["fichas"]["Z18"]["C1120"]["valor"] == 3.1 and res["fichas"]["Z18"]["C1120"]["desde"] == "2022-04" and res["fichas"]["Z18"]["C5111"] is None, "calcular: zona euro desde 2022 y sin hipoteca")
    ok(res["desfase_dias"] == (HOY - date(2026, 9, 28)).days and not ex.AVISOS, f"calcular: desfase sin aviso: {res['desfase_dias']} {ex.AVISOS}")
    ex.AVISOS.clear()
    ex.calcular(ex.leer(csv_ces(hasta="2026-08")), ipc, HOY)
    ok(any("2026-08" in a for a in ex.AVISOS), f"calcular: aviso con más de 75 días: {ex.AVISOS}")
    try:
        ex.calcular(ex.leer(csv_ces(hasta="2026-06")), ipc, HOY)
        ok(False, "calcular: más de 120 días aceptados")
    except ex.DatosRaros:
        ok(True, "")
    ex.AVISOS.clear()
    res_sin = ex.calcular(df, None, HOY)
    ok(res_sin["ipc"]["valor"] is None and res_sin["brecha_percepcion"] is None and any("Sin IPC" in a for a in ex.AVISOS), "calcular: sin IPC, sin brecha y con aviso")
    res["huella"] = ex.huella(res)
    ok(res["huella"] == ex.huella(res) and len(res["huella"]) == 12, "huella: estable")
    res2 = ex.calcular(df, ipc, HOY)
    res2["fichas"]["ES"]["C1120"]["valor"] = 3.9
    ok(ex.huella(res2) != res["huella"], "huella: cambia con el dato")
    try:
        from scipy import stats
        s = ex._serie(df, "ES", "C1120")
        ok(abs(ex.percentil(s, 3.0) - stats.percentileofscore(s, 3.0, kind="weak")) < 1e-9, "percentil: coincide con scipy (weak)")
    except ImportError:
        print("aviso: scipy no está; caso de control no ejecutado")
    return res, ipc


def prueba_escribir(df, res, ipc):
    raiz = Path(tempfile.mkdtemp())
    salida = raiz / "expectativas"
    ok(ex.escribir(df, ipc, res, HOY, salida), "escribir: primera vez")
    frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
    ok(frag.startswith(f"<!-- expectativas:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- expectativas:fin -->"), "fragmento: marcas")
    ok("esperaba una inflación del <strong>3,8 %</strong>" in frag and "+0,7 p.p. respecto al mes anterior" in frag and "frente al 3,1 % del hogar mediano de la zona euro" in frag, "fragmento: frase")
    ok("brecha de percepción de −0,5 p.p." in frag and "esperaba un 2,5 % y el IPC de septiembre de 2026 ha sido del 4,9 % (−2,4 p.p.)" in frag, "fragmento: brecha y acierto")
    ok("Tasa de paro esperada a 12 meses" in frag and "10,5 % de paro" not in frag and "<td>10,5 % </td>" not in frag, "fragmento: tabla de otras expectativas")
    ok("protección frente a la inflación" not in frag and "históricamente" not in frag.lower() and "no predice la inflación ni recomienda nada" in frag,
       "fragmento: sin relacionar la expectativa con productos de inversión")
    ok(frag.count("<polyline") == 4 and "IPC real" in frag, "fragmento: gráfico con cuatro líneas")
    ok("no es asesoramiento" in frag and "no predice" in frag and '<script type="application/ld+json">' in frag, "fragmento: avisos y JSON-LD")
    j = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
    ok(j["version"] == ex.VERSION and j["huella"] == res["huella"] and j["mes"] == "2026-09" and j["variables"]["C1120"] == "inflación esperada a 12 meses", "JSON")
    serie = pd.read_csv(salida / "datos" / "serie.csv")
    ok(list(serie.columns) == ["mes", "area", "variable", "valor", "nombre"] and len(serie) == len(df), "CSV largo con nombres")
    ok(not ex.escribir(df, ipc, res, HOY + timedelta(days=1), salida), "escribir: misma huella, no reescribe")
    ok("Comprobado el 18/11/2026" in (salida / "index.html").read_text(encoding="utf-8"), "index.html")


if __name__ == "__main__":
    df = prueba_lectura()
    res, ipc = prueba_calculo(df)
    prueba_escribir(df, res, ipc)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
