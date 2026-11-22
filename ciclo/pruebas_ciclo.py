"""Comprobaciones sin red del reloj del ciclo (indicador 20d).

  python ciclo/pruebas_ciclo.py

Fichero real de la OCDE descargado el 22/11/2026 y recortado (`ciclo/pruebas_ciclo/cli_20261122.csv`: España
entera desde 1985 y las otras doce zonas desde noviembre de 2023, solo las columnas que se usan), con sus valores
conocidos; una serie simulada con un ciclo conocido (fases en orden, cambio nulo, huecos); paradas y avisos; textos
(nombres de la OCDE, fuente, enlaces, sin predicción); gráficos; huella, escritura, descarga simulada, línea de
órdenes y un caso de control con pandas y numpy (fases, rachas y reparto).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ciclo as c

FIJO = AQUI / "pruebas_ciclo" / "cli_20261122.csv"
HOY = date(2026, 11, 22)
FALLOS: list[str] = []
N = 0
CAB = "DATAFLOW,REF_AREA,FREQ,MEASURE,ADJUSTMENT,METHODOLOGY,TIME_PERIOD,OBS_VALUE"


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if cond:
        print(f"ok     {texto}")
    else:
        FALLOS.append(texto)
        print(f"FALLA  {texto}")


def falla(funcion, *args) -> bool:
    try:
        funcion(*args)
    except c.DatosRaros:
        return True
    return False


def csv_ocde(series: dict[str, dict[str, float]], extra: list[str] | None = None) -> str:
    lineas = [CAB]
    for z, s in series.items():
        for mes in sorted(s):
            lineas.append(f"OECD.SDD.STES:DSD_STES@DF_CLI(4.1),{z},M,LI,AA,H,{mes},{s[mes]}")
    return "\n".join(lineas + (extra or [])) + "\n"


def senoide(meses: int = 480, periodo: int = 48, desde: str = "1985-01") -> dict[str, float]:
    return {c._mes(c._n(desde) + i): round(100 + 2 * math.sin(2 * math.pi * (i + 0.5) / periodo), 5) for i in range(meses)}


def main() -> None:
    # ----- datos reales del 22/11/2026
    c.AVISOS.clear()
    series = c.leer(FIJO.read_text(encoding="utf-8"))
    ok(set(series) == {z for z, _ in c.ZONAS} and not c.AVISOS, "las trece zonas, sin avisos")
    ok(len(series["ESP"]) == 502 and min(series["ESP"]) == "1985-01" and max(series["ESP"]) == "2026-10",
       "España: 502 meses, de enero de 1985 a octubre de 2026")
    ok(series["ESP"]["2026-10"] == 99.35284 and series["ESP"]["2026-06"] == 99.86878 and series["ESP"]["2026-05"] == 100.1586,
       "valores de la OCDE sin tocar (octubre 99,35284; junio 99,86878; mayo 100,1586)")
    res = c.calcular(series, HOY)
    es = res["zonas"]["ESP"]
    ok(es["fase"] == "enfriamiento" and es["fase_ocde"] == "slowdown" and not es["encima_de_100"] and not es["sube"],
       "España en octubre de 2026: por debajo de 100 y bajando, enfriamiento («slowdown»)")
    ok(abs(es["cambio_1m"] - (99.35284 - 99.40405)) < 1e-4 and es["meses_en_direccion"] == 10 and es["lado_desde"] == "2026-06"
       and es["meses_en_fase"] == 5 and es["fase_desde"] == "2026-06",
       "−0,05 en el mes; diez meses bajando; por debajo de 100 desde junio de 2026; cinco meses en la fase")
    ok(abs(sum(es["reparto_fases_pct"].values()) - 100) < 0.2 and es["reparto_fases_pct"]["expansión"] == 32.5,
       "reparto histórico de España: suma 100 %, 32,5 % en expansión")
    fases_zona = {z: (r["fase"], r["meses_en_fase"]) for z, r in res["zonas"].items()}
    ok(fases_zona["CHN"] == ("enfriamiento", 11) and fases_zona["ITA"] == ("desaceleración", 10) and fases_zona["BRA"] == ("expansión", 1)
       and fases_zona["G7"] == ("expansión", 12), "China, Italia, Brasil y G7 con su fase y sus meses")
    ok(len(res["reloj"]) == 13 and res["reloj"][0]["mes"] == "2025-10" and res["reloj"][-1]["mes"] == "2026-10",
       "el reloj dibuja trece meses, de octubre de 2025 a octubre de 2026")
    ok(abs(res["reloj"][-1]["desviacion"] - (99.35284 - 100)) < 1e-4, "el último punto del reloj está en 99,35 − 100")

    # ----- textos
    texto = c.frase(res)
    for trozo in ("En octubre de 2026, el indicador adelantado de la OCDE para España marcó <strong>99,35</strong>: por debajo de 100",
                  "y bajando (−0,05 puntos en el mes)",
                  "Es la fase que la OCDE llama «slowdown» y aquí llamamos <strong>enfriamiento</strong>.",
                  "Lleva 10 meses bajando y está por debajo de 100 desde junio de 2026.",
                  "De las otras 12 zonas de la tabla, 11 están por encima de 100.",
                  "España ha pasado el 32 % de los meses en expansión"):
        ok(trozo in texto, f"frase: «{trozo[:70]}»")
    frag = c.fragmento(res, "abc123def456", "2026-11-22", "2026-11-22")
    ok(frag.startswith("<!-- ciclo:inicio abc123def456 -->") and frag.endswith("<!-- ciclo:fin -->"), "marcas de inicio (con huella) y fin")
    ok(all(f"«{n}»" in frag for n in ("expansion", "downturn", "slowdown", "recovery")), "los cuatro nombres de fase de la OCDE")
    ok("Fuente: OCDE" in frag and "consultado el 22/11/2026" in frag and "la OCDE no participa en esta página ni la respalda" in frag,
       "fuente, fecha de consulta y no respaldo")
    enlaces = re.findall(r'<a href="https://(?:www\.)?oecd\.org[^"]*"[^>]*>', frag)
    ok(len(enlaces) == 3 and all('target="_blank"' in a for a in enlaces), "enlaces a la OCDE en otra ventana")
    ok("Lectura histórica, sin predicción" in frag and "no es asesoramiento financiero" in frag, "aviso de lectura histórica y de no asesoramiento")
    ok(not re.search(r"subirá|bajará|caerá|repuntará|se moverá|previsiblemente|probablemente|recomend(amos|ación de compra)|compre|venda", frag, re.I),
       "sin predicción ni recomendación")
    ok("<td><strong>España</strong></td><td>99,35</td><td>−0,05</td>" in frag and "por debajo desde jun. 2026" in frag, "fila de España en la tabla")
    svgs = re.findall(r"<svg.*?</svg>", frag, flags=re.S)
    ok(len(svgs) == 2 and all("\n" not in s for s in svgs), "dos gráficos SVG en una sola línea (wpautop no los rompe)")
    ok(svgs[0].count("<circle") == 13 and "oct. 2026" in svgs[0] and "Enfriamiento" in svgs[0], "el reloj: trece puntos, el último rotulado")
    ok('style="fill:#1f4e8c;font-weight:bold">España' in svgs[1], "la leyenda de la línea lleva su color (estilo en línea)")

    # ----- serie simulada: un ciclo conocido
    c.AVISOS.clear()
    sim = {"ESP": senoide()}
    s = c.leer(csv_ocde(sim))
    f = c.fases(s["ESP"])
    orden = []
    for m in sorted(f):
        if not orden or orden[-1] != f[m]["fase"]:
            orden.append(f[m]["fase"])
    ciclo_esperado = ["expansión", "desaceleración", "enfriamiento", "recuperación"]
    i0 = orden.index("expansión")
    ok(all(orden[i] == ciclo_esperado[(i - i0) % 4] for i in range(len(orden))),
       "simulada: las fases se suceden en el orden de la OCDE (expansión, desaceleración, enfriamiento, recuperación)")
    ok(len(orden) >= 39, "simulada: diez ciclos completos de 48 meses")
    plano = dict(senoide())
    m1, m2 = "1990-03", "1990-04"
    plano[m2] = plano[m1]
    fp = c.fases(plano)
    ok(fp[m2]["sube"] == fp[m1]["sube"] and fp[m2]["cambio"] == 0, "simulada: un cambio exactamente nulo conserva la dirección del mes anterior")
    hueco = {k: v for k, v in senoide().items() if k != "1990-06"}
    fh = c.fases(hueco)
    ok("1990-06" not in fh and "1990-07" not in fh and "1990-08" in fh, "simulada: tras un hueco, el mes siguiente no tiene cambio ni fase")
    r = c.calcular(s, date(2025, 1, 15))
    ok(r["zonas"]["ESP"]["mes"] == "2024-12" and any("Cuatro grandes" in a for a in c.AVISOS), "simulada: zona que falta, aviso y sin fila")

    # ----- paradas
    ok(falla(c.leer, "a,b,c\n1,2,3\n"), "CSV sin las columnas de la OCDE: DatosRaros")
    ok(falla(c.leer, csv_ocde({"ESP": senoide(300)})), "España con menos de 400 meses: DatosRaros")
    ok(falla(c.leer, csv_ocde({"ESP": senoide()}, ["OECD.SDD.STES:DSD_STES@DF_CLI(4.1),ESP,M,LI,AA,H,2030-01,n.d."])), "valor no numérico: DatosRaros")
    ok(falla(c.leer, csv_ocde({"ESP": senoide()}, ["OECD.SDD.STES:DSD_STES@DF_CLI(4.1),ESP,M,LI,AA,H,2030-01,250"])), "valor fuera de rango: DatosRaros")
    ok(len(c.leer(csv_ocde({"ESP": senoide()}, ["OECD.SDD.STES:DSD_STES@DF_CLI(4.1),ESP,M,LI,NOR,H,2030-01,50"]))["ESP"]) == 480,
       "las filas de otras medidas o ajustes se ignoran")
    ok(falla(c.calcular, series, date(2027, 5, 1)), "seis meses sin dato de España: DatosRaros")
    c.AVISOS.clear()
    c.calcular(series, date(2027, 2, 1))
    ok(any("desfase" in a for a in c.AVISOS), "cuatro meses sin dato: aviso, sin parar")
    c.AVISOS.clear()
    viejo = {**series, "CHN": {k: v for k, v in series["CHN"].items() if k < "2026-10"}}
    c.calcular(viejo, HOY)
    ok(any("CHN" in a for a in c.AVISOS), "una zona con un mes de retraso: aviso")

    # ----- control con pandas y numpy
    df = pd.read_csv(FIJO)
    esp = df[df["REF_AREA"] == "ESP"].set_index("TIME_PERIOD")["OBS_VALUE"].sort_index()
    cambio = esp.diff().dropna()
    encima = esp.loc[cambio.index] > 100
    sube = pd.Series(np.where(cambio.values > 0, True, np.where(cambio.values < 0, False, np.nan)), index=cambio.index).ffill().astype(bool)
    nombres = {(True, True): "expansión", (True, False): "desaceleración", (False, False): "enfriamiento", (False, True): "recuperación"}
    fase_pd = pd.Series([nombres[(a, b)] for a, b in zip(encima, sube)], index=cambio.index)
    f_esp = c.fases(series["ESP"])
    ok(all(f_esp[m]["fase"] == fase_pd[m] for m in fase_pd.index) and len(f_esp) == len(fase_pd), "control: fase de cada mes igual a la de pandas")
    grupo = (fase_pd != fase_pd.shift()).cumsum()
    ok(int((grupo == grupo.iloc[-1]).sum()) == es["meses_en_fase"], "control: meses en la fase iguales a los de pandas")
    reparto_pd = (fase_pd.value_counts(normalize=True) * 100).round(1).to_dict()
    ok(all(reparto_pd[k] == v for k, v in es["reparto_fases_pct"].items()), "control: reparto por fases igual al de pandas")

    # ----- descarga simulada
    class Resp:
        def __init__(self, texto: str, estado=200):
            self.text, self.status_code = texto, estado

    llamadas = []
    original = c.requests.get

    def falso(url, **kw):
        llamadas.append((url, kw.get("params"), kw.get("headers", {}).get("Accept")))
        return Resp("<html>error</html>", 503) if len(llamadas) == 1 else Resp(FIJO.read_text(encoding="utf-8"))
    c.requests.get = falso
    try:
        t = c.descargar(esperas=[0], dormir=lambda x: None)
        ok(len(llamadas) == 2 and t.startswith(CAB) and "ESP+G4E+DEU" in llamadas[1][0] and llamadas[1][2].startswith("application/vnd.sdmx.data+csv"),
           "descarga: reintenta tras un 503, pide las trece zonas en SDMX-CSV")
        c.requests.get = lambda url, **kw: Resp("<html>error</html>", 200)
        ok(falla(c.descargar, [0, 0], lambda x: None), "descarga: si nunca llega el CSV, DatosRaros")
    finally:
        c.requests.get = original

    # ----- escritura, huella y línea de órdenes
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "ciclo"
        series = c.leer(FIJO.read_text(encoding="utf-8"))
        res = c.calcular(series, HOY)
        ok(c.escribir(series, res, HOY, salida) is True, "primera escritura: datos nuevos")
        ok(all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv", "datos/ultima.json")), "escribe los cuatro ficheros")
        h = c.huella(series)
        frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
        ok(frag.startswith(f"<!-- ciclo:inicio {h} -->") and frag.rstrip().endswith("</script>\n<!-- ciclo:fin -->"), "huella en la marca y JSON-LD antes del fin")
        js = json.loads((salida / "datos/ultima.json").read_text(encoding="utf-8"))
        ok(js["version"] == c.VERSION and js["huella"] == h and js["zonas"]["ESP"]["fase"] == "enfriamiento" and "grafico" not in js,
           "ultima.json: versión, huella y fase, sin la serie del gráfico")
        sc = pd.read_csv(salida / "datos/serie.csv")
        fila = sc[(sc["zona"] == "ESP") & (sc["mes"] == "2026-10")].iloc[0]
        ok(len(sc[sc["zona"] == "ESP"]) == 502 and fila["fase"] == "enfriamiento" and abs(fila["valor_ocde"] - 99.35284) < 1e-9,
           "serie.csv: 502 meses de España, octubre con su valor y su fase")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        ok(c.escribir(series, c.calcular(series, HOY), HOY, salida) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns == antes,
           "sin datos nuevos no reescribe nada")
        revisado = {**series, "ESP": {**series["ESP"], "1990-01": series["ESP"]["1990-01"] + 0.001}}
        ok(c.huella(revisado) != h, "una revisión de la OCDE de un mes antiguo cambia la huella")
        ok(c.escribir(series, c.calcular(series, HOY), HOY, salida, forzar=True) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns != antes,
           "--forzar reescribe aunque la huella no cambie")
        r = subprocess.run([sys.executable, str(AQUI / "ciclo.py"), "--salida", str(Path(tmp) / "cli"), "--local", str(FIJO), "--fecha", "2026-11-22"],
                           capture_output=True, text=True, check=False)
        ok(r.returncode == 0 and "Ciclo de 2026-10: España 99.3528 (enfriamiento" in r.stdout, "línea de órdenes con --local")
        r = subprocess.run([sys.executable, str(AQUI / "ciclo.py"), "--salida", str(Path(tmp) / "cli2"), "--local", str(Path(tmp) / "no.csv")],
                           capture_output=True, text=True, check=False)
        ok(r.returncode == 1 and "::error::ciclo:" in r.stdout, "sin fichero, sale con 1 y un error (incidencia en el servidor)")

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")


if __name__ == "__main__":
    main()
