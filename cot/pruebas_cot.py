"""Comprobaciones sin red del indicador de posicionamiento especulativo (20a, COT de la CFTC).

  python cot/pruebas_cot.py

JSON simulado con la forma de la API Socrata de la CFTC y valores conocidos: lectura y paradas, neto, variaciones,
índice COT (0 en el mínimo, 100 en el máximo), percentil con caso de control contra scipy, tramos, desfase,
huella, fragmento, JSON y CSV.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cot  # noqa: E402

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 14)   # sábado; el informe es del martes 10


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def json_simulado(hasta: date = date(2026, 11, 10), semanas: int = 400, sin: str | None = None) -> str:
    """Martes semanales. Euro: neto sube 500 por semana desde 100.000 (mínimo en la primera semana, máximo en la última).
    Oro: neto constante 150.000 salvo la última semana (150.500). VIX: neto 0 (plano). Resto: neto que oscila entre 0 y 60."""
    filas = []
    martes = [hasta - timedelta(weeks=i) for i in range(semanas)][::-1]
    for i, t in enumerate(martes):
        for codigo, (nombre, _) in cot.MERCADOS.items():
            if codigo == sin:
                continue
            if codigo == "099741":
                largo, corto, oi = 400000, 300000 - i * 500, 800000
            elif codigo == "088691":
                largo, corto, oi = (200500 if i == semanas - 1 else 200000), 50000, 500000
            elif codigo == "1170E1":
                largo, corto, oi = 500, 500, 1000
            else:
                largo, corto, oi = 500 + (i % 7) * 10, 500, 1000
            filas.append({"report_date_as_yyyy_mm_dd": t.isoformat() + "T00:00:00.000", "cftc_contract_market_code": codigo,
                          "market_and_exchange_names": nombre.upper() + " - EXCHANGE", "open_interest_all": str(oi), "noncomm_positions_long_all": str(largo),
                          "noncomm_positions_short_all": str(corto), "comm_positions_long_all": "100", "comm_positions_short_all": "300"})
    return json.dumps(filas)


def prueba_lectura():
    df = cot.leer(json_simulado())
    ok(set(df["codigo"]) == set(cot.MERCADOS) and len(df) == 400 * len(cot.MERCADOS), f"leer: mercados y filas: {len(df)}")
    e = df[df["codigo"] == "099741"].sort_values("fecha")
    ok(int(e["neto_nc"].iloc[0]) == 100000 and int(e["neto_nc"].iloc[-1]) == 299500 and int(e["neto_c"].iloc[-1]) == -200, "leer: netos")
    for texto, motivo in (("no json", "no JSON"), ("[]", "vacío"), ('[{"a": 1}]', "sin columnas"),
                          (json_simulado().replace('"open_interest_all": "800000"', '"open_interest_all": "-1"'), "negativo")):
        try:
            cot.leer(texto)
            ok(False, f"leer: aceptado {motivo}")
        except cot.DatosRaros:
            ok(True, "")
    return df


def prueba_calculo(df):
    cot.AVISOS.clear()
    res = cot.calcular(df, HOY)
    e = res["mercados"]["099741"]
    ok(res["fecha"] == "2026-11-10" and res["desfase_dias"] == 4 and not cot.AVISOS, f"calcular: fecha y desfase: {res['fecha']} {res['desfase_dias']} {cot.AVISOS}")
    ok(e["neto_especuladores"] == 299500 and e["variacion_semana"] == 500 and e["variacion_4_semanas"] == 2000, f"calcular: euro: {e}")
    ok(e["indice_cot_3a"] == 100.0 and e["percentil_3a"] == 100.0 and e["tramo"] == "largo extremo" and e["semanas_3a"] == 156, f"calcular: euro en máximo de tres años: {e}")
    ok(e["neto_sobre_oi"] == 37.4 and e["neto_comerciales"] == -200, f"calcular: neto sobre OI y comerciales: {e['neto_sobre_oi']}")
    ok(e["min_3a"] == 299500 - 155 * 500 and e["fecha_min_3a"] == (date(2026, 11, 10) - timedelta(weeks=155)).isoformat(), f"calcular: mínimo de la ventana: {e['min_3a']} {e['fecha_min_3a']}")
    g = res["mercados"]["088691"]
    ok(g["neto_especuladores"] == 150500 and g["variacion_semana"] == 500 and g["indice_cot_3a"] == 100.0 and g["tramo"] == "largo extremo", f"calcular: oro: {g}")
    z = res["mercados"]["1170E1"]
    ok(z["neto_especuladores"] == 0 and z["indice_cot_3a"] is None and z["tramo"] == "sin historial suficiente", f"calcular: serie plana sin índice: {z}")
    ok(res["mas_largos"][:2] == ["Euro (EUR/USD)", "Oro"] and ("Euro (EUR/USD)", "largo extremo") in res["extremos"], f"calcular: más largos y extremos: {res['mas_largos']} {res['extremos']}")
    ok(cot.tramo(50, 50) == "zona media" and cot.tramo(80, 60) == "largo" and cot.tramo(5, 30) == "corto extremo" and cot.tramo(20, 20) == "corto" and cot.tramo(None, None) == "sin historial suficiente", "tramos")
    ok(cot.indice_cot(pd.Series([1.0, 2.0, 3.0] * 20), 2.0) == 50.0 and cot.indice_cot(pd.Series([1.0] * 60), 1.0) is None and cot.indice_cot(pd.Series([1.0, 2.0]), 1.5) is None, "índice COT: mitad del rango; plano o corto, nada")
    try:
        from scipy import stats
        s = df[df["codigo"] == "099741"]["neto_nc"].tail(156)
        v = float(s.iloc[-50])
        ok(abs(cot.percentil(s, v) - stats.percentileofscore(s, v, kind="weak")) < 1e-9, "percentil: coincide con scipy (weak)")
    except ImportError:
        print("aviso: scipy no está; caso de control no ejecutado")
    cot.AVISOS.clear()
    cot.calcular(cot.leer(json_simulado(hasta=date(2026, 10, 27))), HOY)
    ok(any("18 días" in a for a in cot.AVISOS), f"calcular: aviso con 18 días: {cot.AVISOS}")
    try:
        cot.calcular(cot.leer(json_simulado(hasta=date(2026, 10, 6))), HOY)
        ok(False, "calcular: 39 días aceptados")
    except cot.DatosRaros:
        ok(True, "")
    cot.AVISOS.clear()
    res_sin = cot.calcular(cot.leer(json_simulado(sin="1170E1")), HOY)
    ok("1170E1" not in res_sin["mercados"] and any("VIX" in a for a in cot.AVISOS), "calcular: mercado ausente, aviso y sigue")
    res["huella"] = cot.huella(res)
    ok(len(res["huella"]) == 12 and res["huella"] == cot.huella(res), "huella: estable")
    res2 = cot.calcular(df, HOY)
    res2["mercados"]["099741"]["neto_especuladores"] += 1
    ok(cot.huella(res2) != res["huella"], "huella: cambia con el neto")
    return res


def prueba_escribir(df, res):
    raiz = Path(tempfile.mkdtemp())
    salida = raiz / "cot"
    ok(cot.escribir(df, res, HOY, salida), "escribir: primera vez")
    frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
    ok(frag.startswith(f"<!-- cot:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- cot:fin -->"), "fragmento: marcas")
    ok("martes 10/11/2026" in frag and "En extremo de tres años: Euro (EUR/USD) (largo extremo);" in frag and "Oro (largo extremo)" in frag, "fragmento: frase")
    ok("<strong>Euro (EUR/USD)</strong></td><td>299.500</td><td>+500</td><td>+2.000</td><td>+37,4 %</td><td>100</td><td>100</td><td>largo extremo</td><td>−200</td>" in frag, "fragmento: fila del euro")
    ok(frag.count("<svg") == 4 and "miles de contratos netos" in frag, "fragmento: cuatro gráficos")
    ok("no es una señal de compra ni de venta" in frag and "no es asesoramiento" in frag and '<script type="application/ld+json">' in frag, "fragmento: avisos y JSON-LD")
    ok("combustible" not in frag and "históricamente" not in frag.lower(), "fragmento: sin relacionar los extremos con lo que hará el precio")
    j = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
    ok(j["version"] == cot.VERSION and j["huella"] == res["huella"] and len(j["mercados"]) == len(cot.MERCADOS), "JSON")
    serie = pd.read_csv(salida / "datos" / "serie.csv")
    ok(list(serie.columns) == ["fecha", "codigo", "nombre", "oi", "nc_largo", "nc_corto", "neto_nc", "c_largo", "c_corto", "neto_c"] and len(serie) == len(df), "CSV largo")
    ok(not cot.escribir(df, res, HOY + timedelta(days=1), salida), "escribir: misma huella, no reescribe")


if __name__ == "__main__":
    df = prueba_lectura()
    res = prueba_calculo(df)
    prueba_escribir(df, res)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
