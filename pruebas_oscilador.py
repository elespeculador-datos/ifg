# -*- coding: utf-8 -*-
"""
Pruebas del Oscilador Geopolítico 0.10.1 (oscilador.py). Sin pytest: se
ejecuta con el venv del proyecto desde /home/smpro/ifg (o una copia):

    python pruebas_oscilador.py

Comprueba:
  1. Las reglas de tramo e histéresis con casos fijados de antemano.
  2. Que los tramos ya publicados de sesiones cerradas se respetan.
  3. Con los datos reales de docs/: que los valores del Oscilador son los del
     IFG 0.10.0 sesión a sesión, que la foto y los doce meses cuadran, que
     trae lo que lee el plugin y que dos pasadas dan lo mismo.
Sale con código 0 si todo pasa y 1 si algo falla.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile

import pandas as pd

import oscilador as osc

FALLOS = []


def comprobar(cond: bool, que: str) -> None:
    print(("  ok   " if cond else "  FALLA ") + que)
    if not cond:
        FALLOS.append(que)


def pruebas_reglas() -> None:
    print("1. Tramos e histéresis")
    p = osc.paso_histeresis
    comprobar(p(None, 41.0) == "Estable", "sin anterior, 41 → Estable")
    comprobar(p(None, 0.0) == "Alivio fuerte", "0 → Alivio fuerte")
    comprobar(p(None, 100.0) == "Presión fuerte", "100 → Presión fuerte")
    comprobar(p(None, 20.0) == "Alivio", "20 exacto → Alivio (cortes [desde, hasta))")
    comprobar(p("Alivio", 41.5) == "Alivio", "Alivio y 41,5 → sigue Alivio")
    comprobar(p("Alivio", 42.0) == "Alivio", "Alivio y 42,0 → sigue Alivio (no supera en MÁS de 2)")
    comprobar(p("Alivio", 42.01) == "Estable", "Alivio y 42,01 → Estable")
    comprobar(p("Estable", 38.0) == "Estable", "Estable y 38,0 → sigue Estable")
    comprobar(p("Estable", 37.99) == "Alivio", "Estable y 37,99 → Alivio")
    comprobar(p("Alivio fuerte", 50.0) == "Estable", "Alivio fuerte y 50 → Estable (salto de dos tramos)")
    comprobar(p("Presión fuerte", 78.5) == "Presión fuerte", "Presión fuerte y 78,5 → sigue")
    comprobar(p("Presión fuerte", 77.9) == "Presión", "Presión fuerte y 77,9 → Presión")
    comprobar(p("Estable", float("nan")) == osc.SIN_DATO, "valor nulo → sin dato")
    s = pd.Series([41.0, float("nan"), 41.0], index=["a", "b", "c"])
    t = osc.calcular_tramos(s)
    comprobar(list(t) == ["Estable", osc.SIN_DATO, "Estable"], "tras un hueco no hay histéresis")
    s = pd.Series([30.0, 41.0, 43.0, 39.0, 37.0], index=list("abcde"))
    t = osc.calcular_tramos(s)
    comprobar(list(t) == ["Alivio", "Alivio", "Estable", "Estable", "Alivio"], "secuencia 30, 41, 43, 39, 37")


def pruebas_fijados() -> None:
    print("2. Lo cerrado no se toca")
    s = pd.Series([30.0, 41.0, 43.0], index=list("abc"))
    t = osc.calcular_tramos(s, {"a": "Estable"})
    comprobar(list(t) == ["Estable", "Estable", "Estable"], "un tramo fijado manda y la histéresis sigue desde él")
    with tempfile.TemporaryDirectory() as d:
        serie = pd.DataFrame({"ifg": [30.0, 41.0], "estado": ["definitivo", "provisional"]},
                             index=["2026-01-01", "2026-01-02"])
        previa = os.path.join(d, "previa.csv")
        pd.DataFrame({"valor": [30.0, 40.0], "tramo": ["Alivio", "Estable"],
                      "estado": ["definitivo", "provisional"]},
                     index=pd.Index(["2026-01-01", "2026-01-02"], name="fecha")).to_csv(previa)
        f = osc.tramos_fijados(serie, previa)
        comprobar(f == {"2026-01-01": "Alivio"}, "solo se fijan las sesiones cerradas")
        serie.loc["2026-01-01", "ifg"] = 31.0
        try:
            osc.tramos_fijados(serie, previa)
            comprobar(False, "si una sesión cerrada cambia de valor, se para")
        except osc.ErrorOscilador:
            comprobar(True, "si una sesión cerrada cambia de valor, se para")


def pruebas_datos_reales(base: str) -> None:
    print(f"3. Datos reales de {base}/docs")
    with tempfile.TemporaryDirectory() as d:
        # Copia de los tres ficheros de entrada: las pruebas no escriben en docs/.
        os.makedirs(os.path.join(d, "docs"))
        for f in ("ifg_serie.csv", "ifg.json", "ifg_serie_12m.json"):
            shutil.copy2(os.path.join(base, "docs", f), os.path.join(d, "docs", f))
        foto, s12, tabla, n = osc.calcular(d)
        serie = pd.read_csv(os.path.join(d, "docs", "ifg_serie.csv"), index_col=0)
        serie.index = serie.index.astype(str)
        iguales = all((math.isnan(a) and math.isnan(b)) or a == b
                      for a, b in zip(tabla["valor"], serie["ifg"]))
        comprobar(iguales and len(tabla) == len(serie), f"los {len(serie)} valores son los del IFG 0.10.0, uno a uno")
        comprobar(n == 0, "sin fichero previo no hay tramos fijados")
        ifg = json.load(open(os.path.join(d, "docs", "ifg.json"), encoding="utf-8"))
        comprobar(foto["fecha"] == ifg["fecha"] and foto["valor"] == ifg["valor"], "la foto es la del IFG del día")
        comprobar(foto["indice"] == "Oscilador Geopolítico" and foto["version"] == "0.10.1", "nombre y versión")
        comprobar(foto["tramo"] in osc.LIMITES, f"tramo del día de la tabla nueva ({foto['tramo']})")
        for clave in ("fecha", "valor", "tramo", "variacion", "motores", "licencia", "aviso",
                      "indice", "nombre_anterior", "lectura", "leyenda_desglose", "faltan", "estado_dato"):
            comprobar(clave in foto, f"la foto trae «{clave}»")
        comprobar("#licencia" in foto["licencia"] and "oscilador-geopolitico" in foto["licencia"], "licencia con la ficha nueva")
        comprobar(s12["fechas"][-1] == foto["fecha"] and len(s12["tramos_sesion"]) == len(s12["fechas"]), "doce meses cuadrados con la foto")
        comprobar(set(s12["sesiones_por_tramo"]) == set(osc.LIMITES), "sesiones por tramo con las cinco etiquetas nuevas")
        comprobar(sum(s12["sesiones_por_tramo"].values()) == len(s12["fechas"]), "el reparto suma las sesiones de doce meses")
        for clave in ("fechas", "valores", "maximo", "desglose_nivel", "licencia"):
            comprobar(clave in s12, f"los doce meses traen «{clave}»")
        # Idempotencia: escribir, volver a calcular con el fichero previo y comparar.
        cwd = os.getcwd()
        os.chdir(d)
        try:
            osc.escribir(foto, s12, tabla)
        finally:
            os.chdir(cwd)
        modo = os.stat(os.path.join(d, osc.SAL_FOTO)).st_mode & 0o777
        comprobar(modo == 0o644, f"la foto escrita se puede leer desde nginx (permisos {oct(modo)})")
        foto2, s122, tabla2, n2 = osc.calcular(d)
        comprobar(foto2 == foto and s122 == s12 and tabla2["tramo"].equals(tabla["tramo"]),
                  f"segunda pasada idéntica (con {n2} tramos cerrados fijados)")
        cerradas = tabla["estado"].astype(str).str.startswith("definitivo").sum()
        comprobar(n2 == cerradas, f"se fijan todas las sesiones cerradas ({cerradas})")
        print()
        print(osc.resumen(tabla))
        print()
        print("Últimas sesiones:")
        print(tabla.tail(8).to_string())


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    pruebas_reglas()
    pruebas_fijados()
    pruebas_datos_reales(base)
    print()
    if FALLOS:
        print(f"FALLAN {len(FALLOS)} pruebas")
        return 1
    print("TODAS LAS PRUEBAS PASAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
