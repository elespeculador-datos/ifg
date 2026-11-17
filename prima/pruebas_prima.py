"""Comprobaciones sin red del semáforo de la prima de riesgo (indicador 3).

  python prima/pruebas_prima.py

Datos simulados con valores conocidos (regla 7 del catálogo): la lectura del JSON-stat
recupera lo que se puso, los diferenciales solo usan fechas comunes, el percentil coincide
con scipy como caso de control, los tramos y el semáforo cortan donde dicen, los episodios
devuelven el máximo de su ventana, y la escritura no reescribe si la huella no cambia.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prima  # noqa: E402

FALLOS: list[str] = []
N = 0


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


# --------------------------------------------------------------------------- datos simulados
def meses(desde: str, hasta: str) -> pd.DatetimeIndex:
    """Primer día de cada mes, como guarda el colector los periodos «AAAA-MM» de Eurostat."""
    return pd.date_range(desde, hasta, freq="MS")


def rendimientos(fechas: pd.DatetimeIndex) -> dict[str, pd.Series]:
    """Alemania sube y baja suavemente; los demás llevan un diferencial conocido, con picos en meses fijados."""
    t = np.arange(len(fechas))
    de = pd.Series(2.5 + 1.5 * np.sin(t / 40.0), index=fechas)
    prima_es = pd.Series(100.0, index=fechas)  # puntos básicos
    prima_es[(fechas >= "2010-04-01") & (fechas <= "2012-12-31")] = 300.0
    prima_es[fechas == "2012-07-01"] = 560.0
    prima_es[fechas == "2020-03-01"] = 140.0
    prima_es[fechas == "2022-06-01"] = 120.0
    prima_es[fechas >= "2024-01-01"] = 70.0
    prima_es[fechas >= "2026-10-01"] = 85.0
    es = de + prima_es / 100
    it = de + 1.3
    fr = de + 0.4
    return {"DE": de, "ES": es, "IT": it, "FR": fr}


def jsonstat(series: dict[str, pd.Series], valor_lista: bool = False, orden: tuple[str, ...] = ("freq", "int_rt", "geo", "time"),
             claves_str: bool = True, quitar: tuple[tuple[str, str], ...] = ()) -> str:
    geos = sorted(series)
    fechas = sorted({f for s in series.values() for f in s.index})
    tam = {"freq": 1, "int_rt": 1, "geo": len(geos), "time": len(fechas)}
    size = [tam[d] for d in orden]
    pasos, acc = {}, 1
    for d in reversed(orden):
        pasos[d] = acc
        acc *= tam[d]
    valores: dict = {}
    for ig, g in enumerate(geos):
        s = series[g]
        for it_, f in enumerate(fechas):
            if f in s.index and (g, f.strftime("%Y-%m")) not in quitar:
                idx = ig * pasos["geo"] + it_ * pasos["time"]
                valores[str(idx) if claves_str else idx] = round(float(s.loc[f]), 2)
    if valor_lista:
        total = acc
        lista = [None] * total
        for k, v in valores.items():
            lista[int(k)] = v
        valores = lista
    dim = {
        "freq": {"label": "Time frequency", "category": {"index": {"D": 0}, "label": {"D": "Daily"}}},
        "int_rt": {"label": "Interest rate", "category": {"index": {"MCBY": 0}, "label": {"MCBY": "Maastricht criterion bond yields"}}},
        "geo": {"label": "Geopolitical entity (reporting)", "category": {"index": {g: i for i, g in enumerate(geos)}, "label": {g: g for g in geos}}},
        "time": {"label": "Time", "category": {"index": {f.strftime("%Y-%m"): i for i, f in enumerate(fechas)}}},
    }
    return json.dumps({"version": "2.0", "label": "EMU convergence criterion series - monthly data", "source": "ESTAT",
                       "updated": "2026-11-12T11:00:00+0100", "id": list(orden), "size": size, "dimension": dim, "value": valores})


FECHAS = meses("1995-01-01", "2026-10-01")
SERIES = rendimientos(FECHAS)
HOY = date(2026, 11, 17)


# --------------------------------------------------------------------------- lectura
def prueba_lectura():
    df, meta = prima.leer(jsonstat(SERIES))
    ok(set(df["pais"]) == {"ES", "DE", "IT", "FR"}, "leer: los cuatro países")
    ok(len(df) == 4 * len(FECHAS), f"leer: {len(df)} filas, se esperaban {4 * len(FECHAS)}")
    ult = df[(df["pais"] == "ES")].iloc[-1]
    ok(ult["fecha"] == pd.Timestamp("2026-10-01") and abs(ult["valor"] - round(float(SERIES["ES"].iloc[-1]), 2)) < 1e-9,
       "leer: el último dato español es el que se puso")
    ok(meta["actualizado"] == "2026-11-12T11:00:00+0100" and "convergence" in meta["etiqueta"], "leer: metadatos")
    df2, _ = prima.leer(jsonstat(SERIES, valor_lista=True))
    ok(df2.equals(df), "leer: `value` como lista da lo mismo que como diccionario")
    df3, _ = prima.leer(jsonstat(SERIES, orden=("geo", "time", "freq", "int_rt")))
    ok(df3.equals(df), "leer: otro orden de dimensiones da lo mismo")
    df4, _ = prima.leer(jsonstat(SERIES, claves_str=False))
    ok(df4.equals(df), "leer: claves enteras en `value` dan lo mismo")
    df5, _ = prima.leer(jsonstat(SERIES, quitar=(("DE", "2026-10"),)))
    ok(len(df5) == len(df) - 1 and df5[df5["pais"] == "DE"].iloc[-1]["fecha"] == pd.Timestamp("2026-09-01"),
       "leer: una celda sin dato simplemente no está")
    for nombre, texto in [
        ("sin España", jsonstat({k: v for k, v in SERIES.items() if k != "ES"})),
        ("pocas observaciones", jsonstat({k: v.iloc[-100:] for k, v in SERIES.items()})),
        ("periodos que no son meses", re.sub(r'"(\d{4})-(\d{2})":', r'"\1M\2":', jsonstat(SERIES))),
        ("fuera de rango", jsonstat({**SERIES, "ES": SERIES["ES"] + 50})),
        ("error de Eurostat", json.dumps({"error": {"status": 400, "label": "Dataset contains no data"}})),
        ("no es JSON", "<html>mantenimiento</html>"),
        ("sin geo", json.dumps({"id": ["time"], "size": [1], "dimension": {"time": {"category": {"index": {"2026-01-01": 0}}}}, "value": {"0": 1}})),
    ]:
        try:
            prima.leer(texto)
            ok(False, f"leer: {nombre} debería parar")
        except prima.DatosRaros:
            ok(True, "")


# --------------------------------------------------------------------------- cálculos
def prueba_calculos():
    niveles = {p: s.round(2) for p, s in SERIES.items()}
    difs = prima.diferenciales(niveles)
    ok(set(difs) == {"es_de", "it_de", "fr_de", "es_it", "es_fr"}, "diferenciales: los cinco")
    ok(abs(difs["es_de"].loc["2012-07-01"] - 560.0) < 1.01, f"diferenciales: pico de 2012 = {difs['es_de'].loc['2012-07-01']}")
    ok(abs(difs["it_de"].iloc[-1] - 130.0) < 1.01, "diferenciales: Italia-Alemania 130 pb")
    sin = {**niveles, "DE": niveles["DE"].drop(pd.Timestamp("2026-10-01"))}
    d2 = prima.diferenciales(sin)
    ok(d2["es_de"].index[-1] == pd.Timestamp("2026-09-01") and d2["es_it"].index[-1] == pd.Timestamp("2026-10-01"),
       "diferenciales: solo fechas comunes a los dos países")

    rng = np.random.default_rng(7)
    muestra = pd.Series(rng.normal(100, 40, 5000))
    try:
        from scipy import stats
        for v in (20.0, 100.0, 137.5, float(muestra.iloc[17])):
            ok(abs(prima.percentil(muestra, v) - stats.percentileofscore(muestra, v, kind="weak")) < 1e-9,
               f"percentil: caso de control con scipy para {v}")
    except ImportError:
        ok(prima.percentil(pd.Series([1, 2, 3, 4]), 2) == 50.0, "percentil: definición débil (sin scipy)")
    ok(prima.percentil(pd.Series([1.0, 2.0, 2.0, 3.0]), 2.0) == 75.0, "percentil: empates cuentan (débil)")
    ok(np.isnan(prima.percentil(pd.Series([], dtype=float), 1.0)), "percentil: serie vacía da NaN")
    ok([prima.tramo(p) for p in (0, 24.9, 25, 49.9, 50, 74.9, 75, 89.9, 90, 100)]
       == ["bajo", "bajo", "habitual", "habitual", "por encima de lo habitual", "por encima de lo habitual", "alto", "alto", "muy alto", "muy alto"],
       "tramo: cortes en 25, 50, 75 y 90")
    ok([prima.semaforo(p) for p in (0, 49.9, 50, 89.9, 90, 100)] == ["verde", "verde", "ámbar", "ámbar", "rojo", "rojo"],
       "semáforo: verde < 50, ámbar < 90, rojo desde 90")

    s = pd.Series([10.0, 12.0, 15.0, 11.0, 20.0], index=pd.to_datetime(["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]))
    f = pd.Timestamp("2026-10-01")
    ok(prima.variacion(s, f, 28) == 9.0, "variación: un mes toma el mes anterior")
    ok(prima.variacion(s, f, 91) == 8.0, "variación: tres meses toma julio")
    ok(prima.variacion(s, f, 364) is None, "variación: sin historia suficiente, None")
    ok(prima.ultima_vez_igual_o_mayor(pd.Series([5.0, 9.0, 3.0], index=pd.to_datetime(["2025-01-01", "2025-06-01", "2026-11-16"])),
                                      pd.Timestamp("2026-11-16"), 4.0) == "2025-06-01", "última vez igual o mayor, fuera de los seis meses")

    ep = prima.episodios(difs["es_de"])
    por = {e["episodio"]: e for e in ep}
    ok(por["Crisis del euro"]["maximo"] == 560.0 and por["Crisis del euro"]["fecha_maximo"] == "2012-07-01", "episodios: máximo y mes de 2012")
    ok(por["Pandemia"]["fecha_maximo"] == "2020-03-01", "episodios: máximo de 2020 en su mes")
    ok("Crisis del Sistema Monetario Europeo" not in por, "episodios: sin datos en la ventana, no se publica")


def prueba_calcular():
    prima.AVISOS.clear()
    df, _ = prima.leer(jsonstat(SERIES))
    res = prima.calcular(df, HOY, {})
    d = res["diferenciales"]["es_de"]
    ok(res["fecha"] == "2026-10-01" and res["mes"] == "2026-10" and res["desfase_dias"] == 17, "calcular: mes y desfase desde el fin de mes")
    ok(abs(d["valor"] - 85.0) < 1.01, f"calcular: prima actual 85 pb ({d['valor']})")
    ok(d["semaforo"] == "rojo" and d["percentil_3a"] > 90, "calcular: 85 pb tras tres años a 70 es rojo frente a tres años")
    ok(d["tramo_historico"] in ("bajo", "habitual") and d["percentil_historico"] < 50, "calcular: pero habitual o bajo desde 2000")
    ok(d["desde_historico"] == "2000-01-01", "calcular: el histórico empieza en 2000")
    ok(d["maximo_historico"] == 560.0 and d["fecha_maximo_historico"] == "2012-07-01", "calcular: máximo histórico 2012")
    ok(res["ranking"] == ["Italia", "España", "Francia", "Alemania"], f"calcular: ranking {res['ranking']}")
    ok(set(res["grafico"]) == {"es_de", "it_de", "fr_de"} and res["grafico"]["es_de"].index[0] >= pd.Timestamp("2016-10-01")
       and len(res["grafico"]["es_de"]) == 120, "calcular: gráfico de diez años (120 meses)")
    ok(res["niveles"]["ES"]["pais"] == "España" and isinstance(res["niveles"]["ES"]["valor"], float), "calcular: ficha de nivel")
    ok(not prima.AVISOS, f"calcular: sin avisos con datos al día ({prima.AVISOS})")
    prima.AVISOS.clear()
    prima.calcular(df, HOY + timedelta(days=40), {})
    ok(any("desde su fin" in a for a in prima.AVISOS), "calcular: aviso pasados 50 días del fin de mes")
    try:
        prima.calcular(df, HOY + timedelta(days=100), {})
        ok(False, "calcular: pasados 100 días debería parar")
    except prima.DatosRaros:
        ok(True, "")
    prima.AVISOS.clear()


def prueba_tesoro():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        ok(prima.leer_tesoro(raiz) == {}, "tesoro: sin salidas, nada")
        (raiz / "letras" / "datos").mkdir(parents=True)
        (raiz / "bonos" / "datos").mkdir(parents=True)
        (raiz / "letras" / "datos" / "ultima.json").write_text(json.dumps({
            "fuente": "Tesoro", "ultimas": {"12": {"fecha": "2026-11-03", "marginal": 3.068, "solicitado": 6845.63, "adjudicado": 4044.79},
                                            "6": {"fecha": "2026-11-03", "marginal": 2.845}}}), encoding="utf-8")
        (raiz / "bonos" / "datos" / "ultima.json").write_text(json.dumps({
            "fuente": "Tesoro", "ultimas": [
                {"plazo": 10, "fecha": "2026-09-17", "marginal": 3.9, "denominacion": "O 3,50%", "cobertura": 1.8},
                {"plazo": 10, "fecha": "2026-10-15", "marginal": 3.95, "denominacion": "O 3,55%", "cobertura": 2.1},
                {"plazo": 10, "fecha": "2026-11-05", "marginal": 1.2, "denominacion": "O 1,00% (indexada)", "indexado": True},
                {"plazo": 5, "fecha": "2026-11-05", "marginal": 3.4}]}), encoding="utf-8")
        t = prima.leer_tesoro(raiz)
        ok(t["letras_12m"]["marginal"] == 3.068 and t["letras_12m"]["cobertura"] == 1.69, "tesoro: letras a 12 meses con cobertura")
        ok(t["obligaciones_10a"]["fecha"] == "2026-10-15" and t["obligaciones_10a"]["marginal"] == 3.95, "tesoro: la última a 10 años no indexada")
        (raiz / "bonos" / "datos" / "ultima.json").write_text("{roto", encoding="utf-8")
        prima.AVISOS.clear()
        ok(prima.leer_tesoro(raiz) == {} and prima.AVISOS, "tesoro: JSON roto avisa y no publica nada")
        prima.AVISOS.clear()


def prueba_escritura():
    importlib.reload(prima)
    df, meta = prima.leer(jsonstat(SERIES))
    res = prima.calcular(df, HOY, {"letras_12m": {"fecha": "2026-11-03", "marginal": 3.068, "cobertura": 1.69}})
    h1 = prima.huella(res)
    res_b = prima.calcular(df, HOY, {})
    ok(h1 != prima.huella(res_b) and h1 == prima.huella(res), "huella: cambia con el Tesoro y es estable")
    frag = prima.fragmento(res, "2026-11-17")
    ok(frag.startswith(f"<!-- prima:inicio {h1} -->") and frag.rstrip().endswith("<!-- prima:fin -->"), "fragmento: marcas con huella")
    ok("Semáforo: rojo" in frag and "puntos básicos" in frag and "El pulso del Tesoro" in frag, "fragmento: semáforo y pulso del Tesoro")
    ok("$" not in frag and not re.search(r"\bnan\b", frag, flags=re.I) and "None" not in frag, "fragmento: sin $, nan ni None")
    svg = prima.grafico_svg(res["grafico"])
    puntos = re.findall(r'points="([^"]+)"', svg)
    ok(len(puntos) == 3 and all(re.fullmatch(r"(\d+\.\d,\d+\.\d ?)+", p) for p in puntos), "svg: puntos con punto decimal")
    ok(not re.search(r'(x|y|x1|y1|x2|y2)="[^"]*\d,\d', svg), "svg: ningún atributo con coma decimal")
    ld = prima.ld_wp("2026-11-17")
    ok(json.loads(ld.split(">", 1)[1].rsplit("<", 1)[0])["distribution"][0]["contentUrl"].startswith(prima.PAGES), "JSON-LD: contentUrl con la base")
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "prima"
        ok(prima.escribir(df, res, meta, HOY, salida) is True, "escribir: primera vez escribe")
        ficheros = ["fragmento-wp.html", "index.html", "datos/serie.csv", "datos/ultima.json"]
        ok(all((salida / f).exists() for f in ficheros), "escribir: los cuatro ficheros")
        marcas = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
        ok(marcas.count("<!-- prima:inicio") == 1 and marcas.count("<!-- prima:fin -->") == 1 and "application/ld+json" in marcas,
           "escribir: fragmento con marcas únicas y JSON-LD")
        u = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
        ok(u["huella"] == h1 and u["semaforo"] == "rojo" and u["version"] == prima.VERSION and u["eurostat_actualizado"] == meta["actualizado"],
           "escribir: ultima.json")
        csvt = (salida / "datos" / "serie.csv").read_text(encoding="utf-8").splitlines()
        ok(csvt[0] == "mes,serie,unidad,valor" and any("2026-10,es_de,puntos_basicos," in l for l in csvt) and any(",de,porcentaje," in l for l in csvt),
           "escribir: serie.csv con niveles y diferenciales")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        ok(prima.escribir(df, res, meta, HOY + timedelta(days=1), salida) is False, "escribir: sin cambios no reescribe")
        ok((salida / "fragmento-wp.html").stat().st_mtime_ns == antes, "escribir: el fichero no se toca")
        ok(prima.escribir(df, res, meta, HOY + timedelta(days=1), salida, forzar=True) is False
           and "Actualizado el 17/11/2026" in (salida / "fragmento-wp.html").read_text(encoding="utf-8"),
           "escribir: --forzar reescribe conservando la fecha de publicación")
    os.environ["ESPEC_DATOS_BASE"] = "https://datos.elespeculador.com/"
    importlib.reload(prima)
    ok(prima.PAGES == "https://datos.elespeculador.com/prima/", "ESPEC_DATOS_BASE cambia la dirección pública")
    del os.environ["ESPEC_DATOS_BASE"]
    importlib.reload(prima)
    ok(prima.PAGES.startswith("https://elespeculador-datos.github.io/ifg/"), "sin variable, GitHub Pages")


if __name__ == "__main__":
    prueba_lectura()
    prueba_calculos()
    prueba_calcular()
    prueba_tesoro()
    prueba_escritura()
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
