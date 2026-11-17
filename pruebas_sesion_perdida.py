# -*- coding: utf-8 -*-
"""
Pruebas de detectar_sesion_perdida(). Sin red.

Lo que se comprueba, en este orden:

  1. el caso real del 2026-11-02: ninguna bolsa de contado con cierre y el
     S&P 500 con el suyo -> se avisa;
  2. un festivo europeo normal -> NO se avisa, porque Nueva York sigue
     abierta y el ETF mundial y los petroleros imprimen cierre;
  3. el día en curso, aún sin cerrar -> no se avisa nunca;
  4. una sesión que sí está en la serie publicada -> no se avisa;
  5. un día sin cierre del S&P 500 (festivo también en Nueva York) -> no se
     avisa, porque no hay prueba de que fuera día de mercado;
  6. la condición sobre el archivo real, si está disponible: debe cumplirse
     en el 2026-11-02 y en ningún otro día de los 26 años.

Ejecutar:  python pruebas_sesion_perdida.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

import publicar_diario as pub

FALLOS: list[str] = []


def comprobar(condicion: bool, texto: str) -> None:
    if condicion:
        print(f"  OK    {texto}")
    else:
        print(f"  FALLA {texto}")
        FALLOS.append(texto)


def marco(fechas: list[str]) -> pd.DataFrame:
    """Precios de juguete con todas las columnas de la configuración."""
    corro = pub._instrumentos_de_corro()
    cols = corro + ["sp500", "brent", "eurchf"]
    idx = pd.to_datetime(fechas)
    df = pd.DataFrame(1.0, index=idx, columns=cols)
    return df


def ejecutar(precios, publicada, hoy):
    """Llama al detector en un directorio temporal para no dejar marcadores."""
    previo = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            return pub.detectar_sesion_perdida(
                precios, pd.DatetimeIndex(pd.to_datetime(publicada)),
                hoy, "2026-11-03T03:11:00+01:00")
        finally:
            os.chdir(previo)


# --- 1. El caso real ------------------------------------------------------
print("\n1. Ninguna bolsa de contado con cierre (el caso del 2026-11-02)")
p = marco(["2026-10-29", "2026-10-30", "2026-11-02"])
p.loc["2026-11-02", pub._instrumentos_de_corro()] = np.nan   # falla la renta variable
a = ejecutar(p, ["2026-10-29", "2026-10-30"], dt.date(2026, 11, 3))
comprobar(a["avisar"] is True, "se avisa")
comprobar([s["fecha"] for s in a["sesiones_perdidas"]] == ["2026-11-02"],
          "la sesión señalada es la del 2026-11-02")
comprobar(a["ultima_sesion_publicada"] == "2026-10-30",
          "se informa de en qué fecha se ha quedado la serie")


# --- 2. Festivo europeo ---------------------------------------------------
print("\n2. Festivo europeo con Wall Street abierta")
p = marco(["2026-04-02", "2026-04-03", "2026-04-06"])
europeas = [c for c in pub._instrumentos_de_corro()
            if c not in ("acwi", "frontline", "dht", "nordic")]
p.loc["2026-04-06", europeas] = np.nan      # cierran las bolsas europeas
a = ejecutar(p, ["2026-04-02", "2026-04-03"], dt.date(2026, 4, 7))
comprobar(a["avisar"] is False, "NO se avisa de un festivo")
comprobar(a["sesiones_perdidas"] == [], "no se señala ninguna sesión")


# --- 3. El día en curso ---------------------------------------------------
print("\n3. El día en curso, aún sin cerrar")
p = marco(["2026-10-30", "2026-11-03"])
p.loc["2026-11-03", pub._instrumentos_de_corro()] = np.nan
a = ejecutar(p, ["2026-10-30"], dt.date(2026, 11, 3))
comprobar(a["avisar"] is False, "una sesión sin cerrar no se avisa")


# --- 4. Sesión ya publicada ----------------------------------------------
print("\n4. Sesión que ya está en la serie publicada")
p = marco(["2026-10-29", "2026-10-30"])
p.loc["2026-10-30", pub._instrumentos_de_corro()] = np.nan
a = ejecutar(p, ["2026-10-29", "2026-10-30"], dt.date(2026, 11, 3))
comprobar(a["avisar"] is False, "si la fecha está publicada no se avisa")


# --- 5. Sin prueba de sesión ---------------------------------------------
print("\n5. Día sin cierre del S&P 500 (festivo también en Nueva York)")
p = marco(["2026-12-24", "2026-12-25", "2026-12-28"])
p.loc["2026-12-25", :] = np.nan             # no cotiza nada en ninguna parte
a = ejecutar(p, ["2026-12-24", "2026-12-28"], dt.date(2026, 12, 29))
comprobar(a["avisar"] is False,
          "sin cierre de la referencia no hay prueba de día de mercado")


# --- 6. Contraste contra el archivo real ---------------------------------
print("\n6. La condición sobre datos/precios.csv (26 años)")
if os.path.exists("datos/precios.csv"):
    real = pd.read_csv("datos/precios.csv", index_col=0, parse_dates=True)
    corro = [c for c in pub._instrumentos_de_corro() if c in real.columns]
    sin_corro = real[corro].notna().sum(axis=1) == 0
    con_ref = real[pub.REFERENCIA_SESION].notna()
    hits = [str(f.date()) for f in real.index[sin_corro & con_ref]]
    comprobar(hits == ["2026-11-02"],
              f"se cumple solo el 2026-11-02 (encontrado: {hits})")
    comprobar(len(corro) >= 10,
              f"se derivan {len(corro)} instrumentos de corro de la configuración")
else:
    print("  (omitida: no hay datos/precios.csv en este entorno)")


print()
if FALLOS:
    print(f"FALLAN {len(FALLOS)} comprobaciones:")
    for f in FALLOS:
        print(f"  - {f}")
    sys.exit(1)
print("Todas las comprobaciones pasan.")
