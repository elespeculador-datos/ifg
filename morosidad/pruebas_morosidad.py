"""Comprobaciones sin red del indicador de morosidad bancaria (20g).

  python morosidad/pruebas_morosidad.py

Ficheros reales del Boletín Estadístico del Banco de España descargados el 22/11/2026 y recortados a las series que
usa el colector (`morosidad/pruebas_morosidad/`: cuadro 4.3 entero desde 1962; cuadros 4.13 y 4.18 desde 1998, sin
las filas vacías anteriores a 2024), con sus valores conocidos; casos simulados con una serie conocida (percentil,
«la más baja desde», «la más alta desde», mínimo de toda la serie, periodos), paradas (ratio que no cuadra, serie que
falta, valor no numérico, fila inesperada, fichero que no es del Banco de España, desfase), descarga simulada con la
fecha Last-Modified, textos (citas del Banco de España, enlaces en otra ventana, sin predicción), huella, escritura,
línea de órdenes y un caso de control con pandas y scipy (percentil, tasas por segmento y periodos).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import morosidad as mor

FIJOS = AQUI / "pruebas_morosidad"
FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 22)


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if cond:
        print(f"ok     {texto}")
    else:
        FALLOS.append(texto)
        print(f"FALLA  {texto}")


def textos_reales() -> dict[str, str]:
    return {c: (FIJOS / f"{c}.csv").read_bytes().decode(mor.CODIFICACION) for c in mor.CUADROS}


def falla(funcion, *args) -> bool:
    try:
        funcion(*args)
    except mor.DatosRaros:
        return True
    return False


# --------------------------------------------------------------------------- serie simulada
CAB = ["CÓDIGO DE LA SERIE", "NÚMERO SECUENCIAL", "ALIAS DE LA SERIE", "DESCRIPCIÓN DE LA SERIE", "DESCRIPCIÓN DE LAS UNIDADES", "FRECUENCIA"]
ABREV = {v: k for k, v in mor.ABREV.items()}


def csv_bde(codigos: list[str], filas: dict[str, list[str]]) -> str:
    """CSV con el formato del Boletín Estadístico: seis filas de cabecera, meses «MMM AAAA», «_» para lo que falta."""
    lineas = []
    for i, cab in enumerate(CAB):
        lineas.append(",".join([f'"{cab}"' if i == 0 else cab] + (codigos if i == 0 else [f"x{j}" for j in range(len(codigos))])))
    for mes in sorted(filas):
        lineas.append(",".join([f"{ABREV[int(mes[5:])]} {mes[:4]}"] + filas[mes]))
    lineas += ["FUENTE," + "," * (len(codigos) - 1), "NOTAS," + "," * (len(codigos) - 1)]
    return "\n".join(lineas) + "\n"


def simulado(ratios: list[float], primer_mes: str = "1980-12", trimestres: int = 48) -> dict[str, str]:
    """Cuadros 4.3, 4.13 y 4.18 simulados: crédito fijo de 1.000.000 miles; dudosos = ratio x 10.000."""
    meses = [mor._mes(mor._n(primer_mes) + i) for i in range(len(ratios))]
    t403 = csv_bde(["D_BEEA1000", "D_BEEA1600", "D_BEEA2020"],
                   {m: ["1000000", f"{r * 10000:.0f}", f"{r:.2f}"] for m, r in zip(meses, ratios)})
    ultimo = meses[-1]
    fin = mor._n(ultimo) - (mor._n(ultimo) + 1) % 3   # último fin de trimestre no posterior al último mes
    qs = [mor._mes(fin - 3 * i) for i in range(trimestres)][::-1]
    t = {}
    for cuadro in ("be0413", "be0418"):
        cods = [x for s in mor.SEGMENTOS if s[3] == cuadro for x in (s[4], s[5])]
        # crédito 1.000 y dudosos que crecen con el trimestre: la tasa del último es la del segmento i-ésimo + 1 %
        filas = {}
        for k, q in enumerate(qs):
            fila = []
            for i, s in enumerate(x for x in mor.SEGMENTOS if x[3] == cuadro):
                fila += ["1000", str(10 * (i + 1) + k)]
            filas[q] = fila
        t[cuadro] = csv_bde(cods, filas)
    return {"be0403": t403, **t}


# --------------------------------------------------------------------------- pruebas
def main() -> None:
    # ----- datos reales del 22/11/2026
    mensual, segmentos = mor.leer(textos_reales())
    ok(len(mensual["ratio"]) == 549 and min(mensual["ratio"]) == "1980-12" and max(mensual["ratio"]) == "2026-08",
       "cuadro 4.3 real: 549 meses de ratio, de diciembre de 1980 a agosto de 2026")
    ok(mensual["ratio"]["2026-08"] == 2.53 and mensual["dudosos"]["2026-08"] == 31540074 and mensual["credito"]["2026-08"] == 1245452486,
       "agosto de 2026: 2,53 %, 31.540.074 y 1.245.452.486 miles de euros")
    ok(min(mensual["credito"]) == "1962-01", "el crédito y los dudosos empiezan en enero de 1962")
    mor.AVISOS.clear()
    res = mor.calcular(mensual, segmentos, HOY, {"be0403": "2026-10-26", "be0413": "2026-10-26", "be0418": "2026-10-26"})
    ok(res["percentil"] == 22.8 and res["tramo"] == "bajo", "percentil 22,8 y tramo «bajo»")
    ok(res["var_1m"] == 0.02 and res["var_12m"] == -0.4, "variaciones: +0,02 puntos en un mes y -0,40 en doce")
    ok(res["dudosos_var_12m_pct"] == -10.9 and res["credito_var_12m_pct"] == 3.1, "dudosos -10,9 % y crédito +3,1 % en un año")
    ok(res["maximo"] == {"mes": "2013-12", "ratio": 13.62} and res["minimo"] == {"mes": "2006-12", "ratio": 0.72},
       "máximo 13,62 % (diciembre de 2013) y mínimo 0,72 % (diciembre de 2006)")
    ok(res["periodos_igual_o_menor"] == [["1998-06", "2008-08"], ["2026-07", "2026-07"]],
       "igual o por debajo del 2,53 %: de junio de 1998 a agosto de 2008 y julio de 2026")
    ok([(e["mes"], e["ratio"]) for e in res["episodios"]] == [("1986-01", 5.64), ("1994-02", 9.15), ("2006-12", 0.72), ("2013-12", 13.62)],
       "episodios: 5,64 (1986), 9,15 (1994), 0,72 (2006) y 13,62 (2013)")
    filas = {f["segmento"]: f for f in res["segmentos"]["filas"]}
    ok(res["segmentos"]["trimestre"] == "2026-06" and res["segmentos"]["hace_un_ano"] == "2025-06", "segmentos de junio de 2026 frente a junio de 2025")
    ok(filas["vivienda"]["tasa"] == 1.42 and filas["vivienda"]["tasa_hace_un_ano"] == 2.04 and filas["vivienda"]["cambio_12m"] == -0.62,
       "compra de vivienda: 1,42 % (2,04 % un año antes, -0,62)")
    ok(filas["construccion"]["tasa"] == 6.07 and filas["construccion"]["maximo"] == 34.27 and filas["construccion"]["mes_maximo"] == "2013-12",
       "construcción: 6,07 %, máximo 34,27 % en diciembre de 2013")
    ok(filas["financieras"]["tasa"] == 0.43 and filas["total"]["tasa"] == 2.54 and filas["hogares"]["tasa"] == 2.08 and filas["empresas"]["tasa"] == 3.07,
       "intermediación financiera 0,43 %, total 2,54 %, hogares 2,08 %, empresas 3,07 %")
    ok(not mor.AVISOS and res["desfase_meses"] == {"mensual": 3, "trimestral": 5}, "desfase de 3 meses (mensual) y 5 (trimestral), sin avisos")
    # La frase del método «la del total por finalidades coincide con la mensual salvo por redondeos» tiene que ser cierta.
    tot = segmentos["total"]
    difs = [abs(round(tot["dudosos"][q] / tot["credito"][q] * 100, 2) - mensual["ratio"][q]) for q in tot["credito"] if q in mensual["ratio"]]
    ok(len(difs) == 111 and max(difs) <= 0.0101, "en los 111 trimestres, el total por finalidades y la ratio mensual difieren como mucho 0,01 puntos")

    # ----- textos
    texto = mor.frase(res)
    for trozo in ("En agosto de 2026, el <strong>2,53 %</strong> del crédito de bancos y financieras a hogares y empresas en España era dudoso: "
                  "31.540 millones de euros de 1,25 billones.",
                  "Es 0,02 puntos más que en julio y 0,40 puntos menos que en agosto de 2025.",
                  "los créditos dudosos han bajado un 10,9 % y el crédito total ha subido un 3,1 %",
                  "igual o más baja en el 23 % de los meses (percentil 23): un nivel bajo en términos históricos",
                  "Estuvo igual o por debajo entre junio de 1998 y agosto de 2008 y en julio de 2026.",
                  "El máximo fue el 13,62 % de diciembre de 2013, y el mínimo, el 0,72 % de diciembre de 2006.",
                  "la tasa va del 0,43 % de la intermediación financiera no bancaria al 6,07 % de la construcción; "
                  "en la compra de vivienda, del 1,42 % y en el consumo, del 4,04 %."):
        ok(trozo in texto, f"frase: «{trozo[:70]}…»")
    ok("más baja desde" not in texto and "más alta desde" not in texto, "sin «más baja/alta desde»: en julio estaba más baja")
    frag = mor.fragmento(res, "abc123def456", "2026-11-22")
    ok(frag.startswith("<!-- morosidad:inicio abc123def456 -->") and frag.endswith("<!-- morosidad:fin -->"), "marcas de inicio (con huella) y fin")
    ok("Fuente: Sitio web del Banco de España (www.bde.es)" in frag and
       "Fuente: Elaboración propia con datos extraídos del sitio web del Banco de España (www.bde.es)" in frag,
       "las dos fórmulas de cita de los términos de uso del Banco de España")
    ok("actualizado el 26/10/2026; cuadros 4.13 y 4.18, el 26/10/2026" in frag, "fecha de actualización de los ficheros del Banco de España")
    enlaces_bde = re.findall(r'<a href="https://www\.bde\.es[^"]*"[^>]*>', frag)
    ok(len(enlaces_bde) >= 5 and all('target="_blank"' in a and 'rel="noopener"' in a for a in enlaces_bde),
       "todos los enlaces a bde.es se abren en otra ventana (aviso legal)")
    ok("no participa en esta página ni la respalda" in frag and "son gratuitos en bde.es" in frag,
       "neutralidad del Banco de España y aviso de gratuidad")
    ok(not re.search(r"subirá|bajará|caerá|repuntará|se moverá|previsiblemente|probablemente|te recomend|conviene (comprar|vender)", frag, re.I),
       "sin predicción ni recomendación")
    ok("Lectura histórica, sin predicción" in frag and "no es asesoramiento financiero" in frag, "aviso de lectura histórica y de no asesoramiento")
    svgs = re.findall(r"<svg.*?</svg>", frag, flags=re.S)
    ok(len(svgs) == 2 and all("\n" not in s for s in svgs), "dos gráficos SVG, cada uno en una sola línea (wpautop no los rompe)")
    ok("2,53 % (ago. 2026)" in svgs[1] and "13,62 % (dic. 2013)" in svgs[1], "la línea marca el último dato y el máximo")
    ok("Intermediación financiera no bancaria" in svgs[0] and "un año antes" in svgs[0], "las barras llevan nombres cortos y la marca de un año antes")
    ok("<td>· Compra de vivienda</td><td>1,42 %</td><td>2,04 %</td><td>-0,62</td><td>6,28 % (mar. 2014)</td><td>7.193</td><td>506.369</td>" in frag,
       "fila de la compra de vivienda en la tabla de segmentos")
    sin_fechas = mor.fragmento({**res, "actualizado_bde": {}}, "x", "2026-11-22")
    ok("actualizado el" not in sin_fechas.split("</p>")[0].lower().replace("actualizado el 22/11/2026", ""),
       "sin cabecera Last-Modified, no se inventa una fecha de actualización")

    # ----- casos simulados
    mor.AVISOS.clear()
    serie = [10 - i * 0.01 for i in range(540)] + [6.0] * 12 + [4.5]
    m, s = mor.leer(simulado(serie))
    r = mor.calcular(m, s, date(2026, 11, 22))
    ok(r["mes"] == "2026-12" and r["ratio"] == 4.5 and r["ultima_vez_igual_o_menor"] is None, "simulada: el último dato es el mínimo de la serie")
    ok("Es la tasa más baja de toda la serie." in mor.frase(r) and r["percentil"] == round(1 / 553 * 100, 1), "«la más baja de toda la serie» y percentil 0,2")
    serie2 = [3.0] * 150 + [5.0] * 200 + [4.0] * 24 + [2.0] * 30 + [3.5]
    m, s = mor.leer(simulado(serie2))
    r = mor.calcular(m, s, date(2014, 9, 1))
    cuatro = mor._mes(mor._n("1980-12") + 373)   # el último mes en 4,00
    ok(r["ultima_vez_igual_o_mayor"] == cuatro and f"Es la tasa más alta desde {mor.mes_largo(cuatro)}." in mor.frase(r)
       and "más baja desde" not in mor.frase(r), "simulada: sube a 3,50 tras 30 meses en 2,00: «la más alta desde» el último 4,00")
    ok(r["percentil"] == round((150 + 30 + 1) / 405 * 100, 1) and r["tramo"] == "habitual",
       "simulada: percentil con la definición «débil» (los iguales cuentan): 44,7, «habitual»")
    serie3 = [5.0] * 330 + [2.0] * 50 + [3.0] * 30 + [1.9]
    m, s = mor.leer(simulado(serie3))
    r = mor.calcular(m, s, date(2015, 3, 1))
    ok(r["ultima_vez_igual_o_menor"] is None and "Es la tasa más baja de toda la serie." in mor.frase(r), "simulada: 1,90 es el mínimo de la serie")
    serie4 = [5.0] * 330 + [2.0] * 50 + [3.0] * 30 + [2.0]
    m, s = mor.leer(simulado(serie4))
    r = mor.calcular(m, s, date(2015, 3, 1))
    ok(f"Es la tasa más baja desde {mor.mes_largo(r['ultima_vez_igual_o_menor'])}." in mor.frase(r)
       and mor._n(r["mes"]) - mor._n(r["ultima_vez_igual_o_menor"]) == 31, "simulada: vuelve a 2,00 tras 30 meses en 3,00: «la más baja desde»")
    ok(r["periodos_igual_o_menor"] == [[mor._mes(mor._n("1980-12") + 330), mor._mes(mor._n("1980-12") + 379)]], "simulada: un periodo de 50 meses igual o por debajo")
    seg = {f["segmento"]: f for f in r["segmentos"]["filas"]}
    ok(seg["total"]["tasa"] == round((10 + 47) / 1000 * 100, 2) and seg["hogares"]["tasa"] == round((20 + 47) / 1000 * 100, 2),
       "simulada: tasas por segmento = dudosos / crédito del último trimestre")

    # ----- paradas
    t = simulado(serie2)
    roto = t["be0403"].replace(",3.50\n", ",3.60\n")
    ok(falla(mor.leer, {**t, "be0403": roto}), "la ratio publicada no cuadra con dudosos / crédito: DatosRaros")
    ok(falla(mor.leer, {**t, "be0403": t["be0403"].replace("D_BEEA1600", "D_OTRA")}), "falta la serie de dudosos: DatosRaros")
    ok(falla(mor.leer, {**t, "be0403": t["be0403"].replace(",3.50\n", ",n.d.\n")}), "valor no numérico: DatosRaros")
    ok(falla(mor.leer, {**t, "be0418": t["be0418"].replace("FUENTE,", "Total general,")}), "fila inesperada: DatosRaros")
    ok(falla(mor.leer, {**t, "be0413": "<html><body>Mantenimiento</body></html>\n" * 10}), "un HTML en lugar del CSV: DatosRaros")
    ok(falla(mor.leer, simulado([3.0] * 300)), "menos de 400 meses de ratio: DatosRaros")
    ok(falla(mor.leer, simulado(serie2, trimestres=20)), "menos de 40 trimestres por segmento: DatosRaros")
    m, s = mor.leer(textos_reales())
    ok(falla(mor.calcular, m, s, date(2027, 3, 1)), "siete meses sin dato mensual: DatosRaros")
    mor.AVISOS.clear()
    mor.calcular(m, s, date(2027, 2, 1))
    ok(any("mensual" in a for a in mor.AVISOS) and any("trimestral" in a for a in mor.AVISOS), "seis y ocho meses de desfase: avisos, sin parar")
    mor.AVISOS.clear()
    s2 = json.loads(json.dumps(s))
    for k in ("vivienda", "consumo"):
        for t_ in ("credito", "dudosos"):
            s2[k][t_].pop("2026-06")
    mor.AVISOS.clear()
    r2 = mor.calcular(m, s2, HOY)
    ok(r2["segmentos"]["trimestre"] == "2026-03" and any("mismo trimestre" in a for a in mor.AVISOS),
       "si un cuadro va por detrás, se publica el trimestre común y se avisa")

    # ----- control con pandas y scipy
    serie_pd = pd.Series(mensual["ratio"]).sort_index()
    try:
        from scipy.stats import percentileofscore
        ref = percentileofscore(serie_pd.values, 2.53, kind="weak")
        ok(abs(res["percentil"] - round(ref, 1)) < 1e-9, f"control: percentil igual al de scipy ({ref:.4f})")
    except ImportError:
        ref = (serie_pd <= 2.53).mean() * 100
        ok(abs(res["percentil"] - round(ref, 1)) < 1e-9, f"control: percentil igual al de pandas ({ref:.4f}; scipy no instalado)")
    df = pd.read_csv(FIJOS / "be0418.csv", encoding=mor.CODIFICACION, skiprows=range(1, 6), na_values=["_"], index_col=0, dtype=str)
    df = df.drop(index=["FUENTE", "NOTAS"]).apply(pd.to_numeric)
    ok(abs(round(df.loc["JUN 2026", "D_MEADU103"] / df.loc["JUN 2026", "D_MEE61010"] * 100, 2) - filas["construccion"]["tasa"]) < 1e-9
       and abs(round(df.loc["JUN 2025", "D_MEADU106"] / df.loc["JUN 2025", "D_MEE61021"] * 100, 2) - filas["hosteleria"]["tasa_hace_un_ano"]) < 1e-9,
       "control: tasas de construcción y hostelería iguales a las calculadas con pandas sobre el CSV")
    ok(len(pd.period_range(serie_pd.index[0], serie_pd.index[-1], freq="M")) == len(serie_pd), "control: la ratio mensual no tiene huecos desde 1980")
    marca = serie_pd <= 2.53
    marca.iloc[-1] = False
    grupo = (marca != marca.shift()).cumsum()
    tramos_pd = [[g.index[0], g.index[-1]] for _, g in marca[marca].groupby(grupo[marca])]
    ok(tramos_pd == res["periodos_igual_o_menor"], "control: periodos igual o por debajo iguales a los de pandas")

    # ----- descarga simulada
    class Resp:
        def __init__(self, cuerpo: bytes, estado=200, cabeceras=None):
            self.content, self.status_code, self.headers = cuerpo, estado, cabeceras or {}

    llamadas = []
    original = mor.requests.get

    def falso(url, **kw):
        llamadas.append(url)
        if len(llamadas) == 1:
            return Resp(b"<html>error</html>", 503)
        return Resp((FIJOS / "be0403.csv").read_bytes(), 200, {"Last-Modified": "Mon, 26 Oct 2026 23:30:00 GMT"})
    mor.requests.get = falso
    try:
        texto_d, fecha_d = mor.descargar("be0403", esperas=[0], dormir=lambda s: None)
        ok(len(llamadas) == 2 and texto_d.startswith("CÓDIGO DE LA SERIE") and fecha_d == "2026-10-27",
           "descarga: reintenta tras un 503 y toma la fecha Last-Modified en hora de Madrid (23:30 GMT es ya el 27)")
        mor.requests.get = lambda url, **kw: Resp(b"<html>error</html>", 200)
        ok(falla(mor.descargar, "be0413", [0, 0], lambda s: None), "descarga: si nunca llega el CSV, DatosRaros")
    finally:
        mor.requests.get = original
    ok(mor._fecha_cabecera(None) is None and mor._fecha_cabecera("no es una fecha") is None, "Last-Modified ausente o roto: sin fecha")

    # ----- escritura, huella y línea de órdenes
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "morosidad"
        m, s = mor.leer(textos_reales())
        r = mor.calcular(m, s, HOY, {"be0403": "2026-10-26"})
        ok(mor.escribir(m, s, r, HOY, salida) is True, "primera escritura: datos nuevos")
        ficheros = ["fragmento-wp.html", "index.html", "datos/serie.csv", "datos/segmentos.csv", "datos/ultima.json"]
        ok(all((salida / f).exists() for f in ficheros), "escribe los cinco ficheros")
        frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
        h = mor.huella(m, s)
        ok(frag.startswith(f"<!-- morosidad:inicio {h} -->") and frag.rstrip().endswith("</script>\n<!-- morosidad:fin -->"),
           "el fragmento lleva la huella y el JSON-LD antes de la marca de fin")
        js = json.loads((salida / "datos/ultima.json").read_text(encoding="utf-8"))
        ok(js["version"] == mor.VERSION and js["huella"] == h and js["ratio"] == 2.53 and "grafico" not in js and js["cita"]["tratados"].startswith("Fuente: Elaboración propia"),
           "ultima.json: versión, huella, dato y fórmulas de cita, sin la serie del gráfico")
        serie_csv = pd.read_csv(salida / "datos/serie.csv")
        ok(len(serie_csv) == 776 and serie_csv.iloc[-1].tolist() == ["2026-08", 1245452486, 31540074, 2.53], "serie.csv: 776 meses, el último completo")
        seg_csv = pd.read_csv(salida / "datos/segmentos.csv")
        ok(set(seg_csv["segmento"]) == {x[0] for x in mor.SEGMENTOS} and abs(seg_csv.query("trimestre == '2026-06' and segmento == 'vivienda'")["tasa_pct_calculada"].iloc[0] - 1.4206) < 1e-3,
           "segmentos.csv: todos los segmentos y la tasa de vivienda (1,42 %)")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        ok(mor.escribir(m, s, mor.calcular(m, s, HOY), HOY, salida) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns == antes,
           "sin datos nuevos no reescribe nada")
        m["ratio"]["1990-01"] = m["ratio"]["1990-01"]  # mismo dato
        ok(mor.huella(m, s) == h, "la huella no cambia con los mismos datos")
        m["dudosos"]["1990-01"] += 1  # revisión de un mes antiguo
        ok(mor.huella(m, s) != h, "una revisión de un mes antiguo cambia la huella")
        m["dudosos"]["1990-01"] -= 1
        ok(mor.escribir(m, s, mor.calcular(m, s, HOY), HOY, salida, forzar=True) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns != antes,
           "--forzar reescribe aunque la huella no cambie")
        r = subprocess.run([sys.executable, str(AQUI / "morosidad.py"), "--salida", str(Path(tmp) / "cli"), "--local", str(FIJOS), "--fecha", "2026-11-22"],
                           capture_output=True, text=True, check=False)
        ok(r.returncode == 0 and "Morosidad de 2026-08: 2.53 %" in r.stdout and "Datos nuevos." in r.stdout, "línea de órdenes con --local")
        r = subprocess.run([sys.executable, str(AQUI / "morosidad.py"), "--salida", str(Path(tmp) / "cli2"), "--local", str(Path(tmp) / "no-existe")],
                           capture_output=True, text=True, check=False)
        ok(r.returncode == 1 and "::error::morosidad:" in r.stdout, "sin ficheros, sale con 1 y un error (incidencia en el servidor)")

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")


if __name__ == "__main__":
    main()
