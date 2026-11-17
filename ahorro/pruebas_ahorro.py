"""Comprobaciones sin red de la rentabilidad real del ahorro (indicador 4).

  python ahorro/pruebas_ahorro.py

Datos simulados con valores conocidos (regla 7): la lectura de cada fuente recupera lo que se
puso y se para ante formas raras; la búsqueda en el BOE encuentra la resolución del mes y lee
el euríbor de su tabla; la rentabilidad real sigue la fórmula de Fisher; el percentil coincide
con scipy; la escritura no reescribe si la huella no cambia.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ahorro  # noqa: E402

FALLOS: list[str] = []
N = 0


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


# --------------------------------------------------------------------------- datos simulados
MESES = pd.period_range("2003-01", "2026-09", freq="M").strftime("%Y-%m").tolist()


def serie_bce(nombre: str) -> list[float]:
    base = {"es_vista": 0.2, "es_plazo_1a": 2.0, "ea_vista": 0.3, "ea_plazo_1a": 2.2}[nombre]
    return [round(base + 1.5 * np.sin(i / 40.0), 2) for i in range(len(MESES))]


def csv_bce(con_conjunto: bool = True, quitar: str | None = None) -> str:
    filas = ["KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,TITLE_COMPL"]
    for n, (area, partida, venc, cob) in ahorro.SERIES_BCE.items():
        if n == quitar:
            continue
        clave = f"M.{area}.B.{partida}.{venc}.R.A.2250.EUR.{cob}"
        if con_conjunto:
            clave = "MIR." + clave
        for mes, v in zip(MESES, serie_bce(n)):
            filas.append(f"{clave},M,{area},{mes},{v},{n}")
    return "\n".join(filas) + "\n"


def ipc_valores() -> list[float]:
    return [round(2.0 + 2.5 * np.sin(i / 25.0), 1) for i in range(len(MESES) + 1)]  # un mes más que el BCE (el INE va antes)


def json_ine(nombre: str = "Índice general. Nacional. Variación anual") -> tuple[str, str]:
    meses = MESES + ["2026-10"]
    datos = [{"Fecha": 0, "Anyo": int(m[:4]), "FK_Periodo": int(m[5:7]), "Valor": v, "Secreto": False} for m, v in zip(meses, ipc_valores())]
    return json.dumps({"Id": 251856, "Nombre": nombre}), json.dumps({"Id": 251856, "Nombre": nombre, "Data": datos})


XML_RESOLUCION = """<?xml version="1.0" encoding="utf-8"?>
<documento><metadatos><identificador>BOE-A-2026-20519</identificador>
<titulo>Resolución de 1 de octubre de 2026, del Banco de España, por la que se publican determinados tipos de interés oficiales de referencia del mercado hipotecario.</titulo>
</metadatos><texto><p class="parrafo">Mensualmente se hacen públicos los índices de referencia oficiales para los préstamos hipotecarios a tipo variable...</p>
<table><tr><td class="cabeza"></td><td class="cabeza" colspan="2">Septiembre de 2026</td></tr>
<tr><td class="cabeza">Tipos de referencia</td><td class="cabeza">1</td><td class="cabeza">Porcentaje</td></tr>
<tr><td class="cuerpo">1. Eur&iacute;bor. Plazos:</td><td></td><td></td></tr>
<tr><td class="cuerpo">&ndash; Una semana.</td><td></td><td class="cuerpo">2,289</td></tr>
<tr><td class="cuerpo">&ndash; Un mes.</td><td></td><td class="cuerpo">2,414</td></tr>
<tr><td class="cuerpo">&ndash; Tres meses.</td><td></td><td class="cuerpo">2,635</td></tr>
<tr><td class="cuerpo">&ndash; Seis meses.</td><td></td><td class="cuerpo">2,922</td></tr>
<tr><td class="cuerpo">&ndash; Un a&ntilde;o.</td><td></td><td class="cuerpo">3,247</td></tr>
<tr><td class="cuerpo">2. Permuta de intereses (IRS). Plazo cinco a&ntilde;os.</td><td></td><td class="cuerpo">3,450</td></tr>
<tr><td class="cuerpo">3. &euro;STR. Plazos:</td><td></td><td></td></tr>
<tr><td class="cuerpo">&ndash; Un a&ntilde;o.</td><td></td><td class="cuerpo">2,034</td></tr>
<tr><td class="cuerpo">4. M&iacute;bor (interbancario a un a&ntilde;o).</td><td></td><td class="cuerpo">3,247</td></tr>
</table></texto></documento>"""

XML_SIMPLE = """<documento><metadatos><titulo>Resolución de 1 de octubre de 2026</titulo></metadatos><texto>
<p>Tipos de referencia (septiembre de 2026)</p><table><tr><td>Euríbor</td><td>Un año</td><td>3,247</td></tr>
<tr><td>Míbor</td><td>Un año</td><td>3,247</td></tr></table></texto></documento>"""


def sumario(dia: date, ident: str | None) -> str:
    items = [{"identificador": "BOE-A-2026-1", "titulo": "Orden de ... por la que se regula ..."}]
    if ident:
        items.append({"identificador": ident, "titulo": "Resolución de 1 de octubre de 2026, del Banco de España, por la que se publican determinados tipos de interés oficiales de referencia del mercado hipotecario."})
    return json.dumps({"status": {"code": "200"}, "data": {"sumario": {"diario": [{"numero": "1", "seccion": [
        {"codigo": "3", "nombre": "III", "departamento": [{"nombre": "BANCO DE ESPAÑA", "epigrafe": [{"nombre": "x", "item": items}]}]}]}]}}})


# --------------------------------------------------------------------------- BCE e INE
def prueba_bce():
    df = ahorro.leer_bce(csv_bce())
    ok(set(df["serie"]) == set(ahorro.SERIES_BCE) and len(df) == 4 * len(MESES), "BCE: cuatro series completas")
    ult = df[df["serie"] == "es_plazo_1a"].iloc[-1]
    ok(ult["mes"] == "2026-09" and ult["valor"] == serie_bce("es_plazo_1a")[-1], "BCE: último valor de los depósitos a plazo")
    ok(ahorro.leer_bce(csv_bce(con_conjunto=False)).equals(df), "BCE: la clave sin el conjunto delante da lo mismo")
    for nombre, texto in [("falta una serie", csv_bce(quitar="ea_vista")), ("sin columnas", "a,b\n1,2\n"),
                          ("fuera de rango", csv_bce().replace("2026-09,", "2026-09,99").replace("2026-09,99", "2026-09,99", 1))]:
        try:
            ahorro.leer_bce(texto)
            ok(False, f"BCE: {nombre} debería parar")
        except ahorro.DatosRaros:
            ok(True, "")


def prueba_ine():
    meta, datos = json_ine()
    tabla = json.dumps([{"COD": "IPC9", "Nombre": "Índice general. Índice. ", "Data": []},
                        {"COD": "IPC8", "Nombre": "Índice general. Variación anual. ", "Data": json.loads(datos)["Data"]}])
    desde_tabla = ahorro.leer_ine(meta, ahorro.serie_de_tabla(tabla))
    ok(desde_tabla["mes"].iloc[-1] == "2026-10" and json.loads(ahorro.serie_de_tabla(tabla))["COD"] == "IPC8", "INE: la tabla de respaldo da la serie de variación anual")
    try:
        ahorro.serie_de_tabla(json.dumps([{"COD": "IPC9", "Nombre": "Índice general. Índice. ", "Data": []}]))
        ok(False, "INE: tabla sin variación anual debería parar")
    except ahorro.DatosRaros:
        ok(True, "")
    ipc = ahorro.leer_ine(meta, datos)
    ok(len(ipc) == len(MESES) + 1 and ipc["mes"].iloc[-1] == "2026-10", "INE: todos los meses, el último es octubre")
    ok(ipc["valor"].iloc[-1] == ipc_valores()[-1], "INE: último valor")
    for nombre, args in [("nombre equivocado", json_ine("Índice general. Nacional. Variación mensual")),
                         ("no es JSON", ("<html>", "<html>")),
                         ("sin datos", (meta, json.dumps({"Nombre": "Índice general. Variación anual", "Data": []})))]:
        try:
            ahorro.leer_ine(*args)
            ok(False, f"INE: {nombre} debería parar")
        except ahorro.DatosRaros:
            ok(True, "")


# --------------------------------------------------------------------------- BOE
def prueba_boe():
    ok(ahorro.buscar_resolucion(date(2026, 10, 2), lambda d: sumario(d, "BOE-A-2026-20519")) == "BOE-A-2026-20519", "BOE: encuentra la resolución en el sumario JSON")
    ok(ahorro.buscar_resolucion(date(2026, 10, 1), lambda d: sumario(d, None)) is None, "BOE: sin resolución, None")
    ok(ahorro.buscar_resolucion(date(2026, 10, 1), lambda d: "") is None, "BOE: respuesta vacía (404), None")
    xml_sum = ('<sumario><diario><seccion><departamento><item id="BOE-A-2026-20519"><titulo>Resolución de 1 de octubre de 2026, del Banco de España, '
               'por la que se publican determinados tipos de interés oficiales de referencia del mercado hipotecario.</titulo></item></departamento></seccion></diario></sumario>')
    ok(ahorro.buscar_resolucion(date(2026, 10, 2), lambda d: xml_sum) == "BOE-A-2026-20519", "BOE: también lee el sumario en XML")
    r = ahorro.leer_resolucion(XML_RESOLUCION)
    ok(r == {"mes": "2026-09", "euribor_12m": 3.247}, f"BOE: euríbor a un año y mes de la resolución, forma real por grupos ({r})")
    ok(ahorro.leer_resolucion(XML_SIMPLE) == {"mes": "2026-09", "euribor_12m": 3.247}, "BOE: también con la tabla en forma simple")
    sin_un_anio = XML_RESOLUCION.replace("&ndash; Un a&ntilde;o.</td><td></td><td class=\"cuerpo\">3,247", "&ndash; Nueve meses.</td><td></td><td class=\"cuerpo\">3,100", 1)
    try:
        ahorro.leer_resolucion(sin_un_anio)
        ok(False, "BOE: sin «un año» en el grupo del euríbor no debe tomar el del €STR")
    except ahorro.DatosRaros:
        ok(True, "")
    try:
        ahorro.leer_resolucion("<documento><texto><p>Nada que ver</p></texto></documento>")
        ok(False, "BOE: sin euríbor debería parar")
    except ahorro.DatosRaros:
        ok(True, "")
    llamadas = []

    def sum_sim(d):
        llamadas.append(d)
        return sumario(d, "BOE-A-2026-20519" if d == date(2026, 10, 2) else None)

    r = ahorro.euribor_del_mes("2026-09", sum_sim, lambda ident: XML_RESOLUCION, hoy=date(2026, 11, 17))
    ok(r and r["boe"] == "BOE-A-2026-20519" and r["fecha_boe"] == "2026-10-02" and r["euribor_12m"] == 3.247, "BOE: busca desde el día 1 del mes siguiente")
    ok(llamadas == [date(2026, 10, 1), date(2026, 10, 2)], f"BOE: para en cuanto la encuentra ({llamadas})")
    ok(ahorro.euribor_del_mes("2026-11", sum_sim, lambda i: XML_RESOLUCION, hoy=date(2026, 11, 17)) is None, "BOE: un mes aún no publicado da None sin llamar")
    llamadas.clear()
    ahorro.euribor_del_mes("2026-10", lambda d: (llamadas.append(d), sumario(d, None))[1], lambda i: XML_RESOLUCION, hoy=date(2026, 11, 17))
    ok(all(d.weekday() != 6 for d in llamadas) and len(llamadas) == 10, f"BOE: salta los domingos y mira doce días ({len(llamadas)} llamadas)")
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "euribor_boe.csv"

        def sum_todo(d):
            llamadas.append(d)
            return sumario(d, f"BOE-A-{d.year}-{d.month}") if d.day == 2 else sumario(d, None)

        def xml_todo(ident):
            a, m = ident.split("-")[2:]
            mes_ant = ahorro._mes_menos(f"{int(a):04d}-{int(m):02d}", 1)
            return XML_RESOLUCION.replace("Septiembre de 2026", f"{ahorro.MESES[int(mes_ant[5:]) - 1]} de {mes_ant[:4]}").replace("3,247", "3,100")

        llamadas.clear()
        ahorro.AVISOS.clear()
        df = ahorro.actualizar_euribor(ruta, date(2026, 11, 17), meses_atras=2, descargar_sumario=sum_todo, descargar_xml=xml_todo)
        ok(df["mes"].tolist() == ["2026-08", "2026-09", "2026-10"] and (df["euribor_12m"] == 3.1).all(), f"BOE: acumula el mes anterior y dos hacia atrás ({df['mes'].tolist()})")
        ok(ruta.exists() and not ahorro.AVISOS, "BOE: guarda el CSV y no avisa cuando el mes coincide")
        n = len(llamadas)
        df2 = ahorro.actualizar_euribor(ruta, date(2026, 11, 17), meses_atras=2, descargar_sumario=sum_todo, descargar_xml=xml_todo)
        ok(len(llamadas) == n and df2.equals(df), "BOE: con todo acumulado no vuelve a llamar")
        df3 = ahorro.actualizar_euribor(ruta, date(2026, 12, 3), descargar_sumario=sum_todo, descargar_xml=xml_todo)
        ok(df3["mes"].tolist()[-1] == "2026-11" and len(df3) == 4, "BOE: en diciembre añade noviembre")


# --------------------------------------------------------------------------- cálculos y salida
def calcular_sim(letras=None, hoy=date(2026, 11, 17)):
    bce = ahorro.leer_bce(csv_bce())
    ipc = ahorro.leer_ine(*json_ine())
    eur = pd.DataFrame({"mes": MESES[-36:], "euribor_12m": [3.0 + 0.01 * i for i in range(36)], "boe": "BOE-A-x", "fecha_boe": "2026-01-02"})
    return ahorro.calcular(bce, ipc, eur, letras, hoy)


def prueba_calculos():
    ok(abs(ahorro.real(3.0, 2.0) - 0.9804) < 1e-3 and abs(ahorro.real(1.0, 4.0) + 2.8846) < 1e-3, "real: fórmula de Fisher")
    ok(ahorro.real(2.0, 2.0) == 0.0, "real: tipo igual a inflación da cero")
    try:
        from scipy import stats
        rng = np.random.default_rng(3)
        m = pd.Series(rng.normal(0, 2, 3000))
        ok(all(abs(ahorro.percentil(m, v) - stats.percentileofscore(m, v, kind="weak")) < 1e-9 for v in (-1.0, 0.0, 2.5)), "percentil: caso de control con scipy")
    except ImportError:
        ok(ahorro.percentil(pd.Series([1, 2, 3, 4]), 2) == 50.0, "percentil: definición débil")
    ok(ahorro.racha(pd.Series([1.0, -1.0, -0.5, -2.0])) == ("negativa", 3) and ahorro.racha(pd.Series([-1.0, 0.5])) == ("positiva", 1)
       and ahorro.racha(pd.Series([-1.0, 0.0])) == ("negativa", 2), "racha: signo y longitud (el cero no es positivo)")
    ok(ahorro._mes_menos("2026-01", 12) == "2025-01" and ahorro._mes_menos("2026-03", 4) == "2025-11", "mes menos n")
    ahorro.AVISOS.clear()
    res = calcular_sim({"fecha": "2026-11-03", "marginal": 3.068, "fuente": "Tesoro"})
    p = res["tipos"]["es_plazo_1a"]
    ok(res["mes"] == "2026-09" and res["mes_ipc"] == "2026-10" and res["mes_bce"] == "2026-09" and res["mes_euribor"] == "2026-09", "calcular: meses de cada fuente y último común")
    ok(abs(p["real"] - ahorro.real(serie_bce("es_plazo_1a")[-1], ipc_valores()[-2])) < 0.006, "calcular: real del último mes común con el IPC de ese mes")
    ok(0 <= p["percentil_real"] <= 100 and p["racha"] in ("positiva", "negativa") and p["racha_meses"] >= 1, "calcular: percentil y racha")
    ok(p["variacion_12m"] == round(serie_bce("es_plazo_1a")[-1] - serie_bce("es_plazo_1a")[-13], 2), "calcular: variación a doce meses")
    ok("euribor_12m" in res["tipos"] and res["tipos"]["euribor_12m"]["tipo"] == 3.35, "calcular: euríbor con su ficha")
    ok(res["letras_12m"]["real"] == round(ahorro.real(3.068, ipc_valores()[-1]), 2) and res["letras_12m"]["ipc_usado"] == ipc_valores()[-1], "calcular: letras frente al último IPC")
    ok(res["desfase_dias"] == 48 and not ahorro.AVISOS, f"calcular: desfase 48 días sin aviso ({ahorro.AVISOS})")
    ahorro.AVISOS.clear()
    calcular_sim(hoy=date(2027, 1, 20))
    ok(any("desde su fin" in a for a in ahorro.AVISOS), "calcular: aviso pasados 75 días")
    try:
        calcular_sim(hoy=date(2027, 4, 1))
        ok(False, "calcular: pasados 150 días debería parar")
    except ahorro.DatosRaros:
        ok(True, "")
    ahorro.AVISOS.clear()
    res2 = ahorro.calcular(ahorro.leer_bce(csv_bce()), ahorro.leer_ine(*json_ine()), pd.DataFrame(columns=["mes", "euribor_12m", "boe", "fecha_boe"]), None, date(2026, 11, 17))
    ok("euribor_12m" not in res2["tipos"] and "letras_12m" not in res2 and res2["mes_euribor"] is None, "calcular: sin euríbor ni letras no se inventa nada")


def prueba_salida():
    importlib.reload(ahorro)
    res = calcular_sim({"fecha": "2026-11-03", "marginal": 3.068, "fuente": "Tesoro"})
    h = ahorro.huella(res)
    ok(h == ahorro.huella(res) and h != ahorro.huella(calcular_sim()), "huella: estable y sensible a las letras")
    frag = ahorro.fragmento(res, "2026-11-17")
    ok(frag.startswith(f"<!-- ahorro:inicio {h} -->") and frag.rstrip().endswith("<!-- ahorro:fin -->"), "fragmento: marcas con huella")
    ok("rentabilidad real fue del" in frag and "Letras del Tesoro a 12 meses" in frag and "octubre de 2026" in frag, "fragmento: lectura, letras y último IPC")
    ok("$" not in frag and not re.search(r"\bnan\b", frag, re.I) and "None" not in frag, "fragmento: sin $, nan ni None")
    svg = ahorro.grafico_svg(res["grafico"])
    puntos = re.findall(r'points="([^"]+)"', svg)
    ok(len(puntos) == 1 and re.fullmatch(r"(\d+\.\d,\d+\.\d ?)+", puntos[0]) and 'stroke-dasharray' in svg, "svg: puntos con punto decimal y línea del cero")
    ok(not re.search(r'(x|y|x1|y1|x2|y2)="[^"]*\d,\d', svg), "svg: sin comas decimales en atributos")
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "ahorro"
        ok(ahorro.escribir(res, date(2026, 11, 17), salida) is True, "escribir: primera vez escribe")
        ok(all((salida / f).exists() for f in ("fragmento-wp.html", "index.html", "datos/serie.csv", "datos/ultima.json")), "escribir: los cuatro ficheros")
        u = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
        ok(u["huella"] == h and u["mes"] == "2026-09" and u["tipos"]["es_plazo_1a"]["real"] == res["tipos"]["es_plazo_1a"]["real"], "escribir: ultima.json")
        lineas = (salida / "datos" / "serie.csv").read_text(encoding="utf-8").splitlines()
        ok(lineas[0] == "mes,serie,valor" and any(",real_es_plazo_1a," in l for l in lineas) and any(",ipc," in l for l in lineas), "escribir: serie.csv")
        texto = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
        ok(texto.count("<!-- ahorro:inicio") == 1 and "application/ld+json" in texto and ahorro.PAGES in texto, "escribir: fragmento con JSON-LD y base")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        ok(ahorro.escribir(res, date(2026, 11, 18), salida) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns == antes, "escribir: sin cambios no reescribe")
        ok(ahorro.escribir(res, date(2026, 11, 18), salida, forzar=True) is False and "17/11/2026" in (salida / "fragmento-wp.html").read_text(encoding="utf-8"),
           "escribir: --forzar reescribe conservando la fecha de publicación")
    os.environ["ESPEC_DATOS_BASE"] = "https://datos.elespeculador.com/"
    importlib.reload(ahorro)
    ok(ahorro.PAGES == "https://datos.elespeculador.com/ahorro/", "ESPEC_DATOS_BASE cambia la dirección pública")
    del os.environ["ESPEC_DATOS_BASE"]
    importlib.reload(ahorro)


if __name__ == "__main__":
    prueba_bce()
    prueba_ine()
    prueba_boe()
    prueba_calculos()
    prueba_salida()
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
