# -*- coding: utf-8 -*-
"""
Prueba de la guardia que impide que una descarga corta borre el histórico.

EL FALLO QUE ESTO VIGILA PASÓ DE VERDAD. El 2 de noviembre de 2026 Yahoo
devolvió UNA sesión de TTF=F en vez de 2.269, el caché se escribió encima y
nueve años de gas europeo desaparecieron del repositorio. El índice se publicó
igual -marcado como provisional- unos 13 puntos por debajo de lo que le
correspondía, y el recálculo se separó 18,07 puntos de filas ya cerradas.

Aquí se comprueba, con datos sintéticos, que eso ya no puede volver a pasar
sin que quede constancia y sin que el histórico sobreviva.
"""
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

import fuentes   # noqa: E402

fallos = []


def ok(cond, msg):
    print(f"  [{' ok ' if cond else 'FALLO'}] {msg}")
    if not cond:
        fallos.append(msg)


fechas = pd.bdate_range("2020-01-01", periods=500)

# Caché "de ayer": dos columnas con histórico completo.
previo = pd.DataFrame(
    {"brent": np.linspace(60, 90, 500), "gas_ttf": np.linspace(20, 100, 500)},
    index=fechas,
)

# --- Caso 1: el caso real, una columna vuelve con una sola sesión --------
print("\n== Caso 1: descarga corta en una columna (el fallo del gas) ==")
corta = previo.copy()
corta.loc[corta.index[:-1], "gas_ttf"] = np.nan   # solo sobrevive la última
r = fuentes._conservar_historia(corta, previo)

ok(int(r["gas_ttf"].notna().sum()) == 500,
   f"el histórico del gas se conserva entero (quedan {int(r['gas_ttf'].notna().sum())})")
ok(abs(float(r.loc[fechas[-1], "gas_ttf"]) - float(corta.loc[fechas[-1], "gas_ttf"])) < 1e-9,
   "la sesión que sí trae la descarga manda sobre el caché")
ok(int(r["brent"].notna().sum()) == 500, "la columna sana no se toca")

# --- Caso 2: la columna desaparece por completo -------------------------
print("\n== Caso 2: la descarga ni siquiera trae la columna ==")
sin_col = previo[["brent"]].copy()
r2 = fuentes._conservar_historia(sin_col, previo)
ok("gas_ttf" in r2.columns, "la columna ausente reaparece desde el caché")
ok(int(r2["gas_ttf"].notna().sum()) == 500, "con todo su histórico")

# --- Caso 3: una descarga normal añade sesiones nuevas ------------------
print("\n== Caso 3: descarga normal, el día siguiente ==")
manana = pd.bdate_range("2020-01-01", periods=501)
normal = pd.DataFrame(
    {"brent": np.linspace(60, 90.5, 501), "gas_ttf": np.linspace(20, 100.5, 501)},
    index=manana,
)
r3 = fuentes._conservar_historia(normal, previo)
ok(len(r3) == 501, f"la serie avanza una sesión (tiene {len(r3)})")
ok(abs(float(r3.loc[manana[-1], "gas_ttf"]) - 100.5) < 1e-9,
   "la sesión nueva entra con su valor")
ok(abs(float(r3.loc[fechas[-1], "brent"]) - float(normal.loc[fechas[-1], "brent"])) < 1e-9,
   "donde hay dato fresco manda el fresco, no el caché")

# --- Caso 4: el valor fresco corrige uno guardado -----------------------
print("\n== Caso 4: la fuente revisa un cierre ==")
revisado = previo.copy()
revisado.loc[fechas[-1], "brent"] = 999.0
r4 = fuentes._conservar_historia(revisado, previo)
ok(abs(float(r4.loc[fechas[-1], "brent"]) - 999.0) < 1e-9,
   "una revisión al alza o a la baja sí se acepta (no se congela el dato)")

# --- Caso 5: de punta a punta, escribiendo el caché de verdad -----------
print("\n== Caso 5: descargar_precios no escribe un caché más pobre ==")
tmp = tempfile.mkdtemp()
dir_original = fuentes.DIR_CACHE
try:
    fuentes.DIR_CACHE = tmp
    previo.to_csv(os.path.join(tmp, "precios.csv"))

    # Se simula la descarga del día del fallo: solo la última sesión del gas.
    leido_antes = pd.read_csv(os.path.join(tmp, "precios.csv"), index_col=0,
                              parse_dates=True)
    fundido = fuentes._conservar_historia(corta, leido_antes)
    fuentes._escribir_cache("precios", fundido)
    en_disco = pd.read_csv(os.path.join(tmp, "precios.csv"), index_col=0,
                           parse_dates=True)
    ok(int(en_disco["gas_ttf"].notna().sum()) == 500,
       "el caché escrito en disco conserva el histórico")
finally:
    fuentes.DIR_CACHE = dir_original
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + (f"{len(fallos)} FALLOS" if fallos else "Todas las comprobaciones pasan."))
sys.exit(1 if fallos else 0)
