# -*- coding: utf-8 -*-
"""
Prueba de indice.empalmar con datos sintéticos.

El empalme es lógica nueva y si está mal corrompe la serie histórica sin
avisar: un salto de nivel en la junta se convierte en un pico de fricción
inventado. Aquí se comprueba contra casos donde la respuesta se conoce.
"""
import sys

import numpy as np
import pandas as pd

import config   # noqa: E402
import indice   # noqa: E402

fallos = []


def ok(cond, msg):
    print(f"  [{' ok ' if cond else 'FALLO'}] {msg}")
    if not cond:
        fallos.append(msg)


fechas = pd.bdate_range("2020-01-01", periods=20)

# --- Caso 1: el respaldo cubre el tramo anterior -------------------------
# Principal existe desde la sesión 10. Respaldo, en todas, a MITAD de nivel:
# el empalme debe conservar el nivel de la principal, no el del respaldo.
print("\n== Caso 1: niveles muy distintos, el empalme no debe dar un salto ==")
principal = pd.Series([np.nan] * 10 + [100.0] * 10, index=fechas)
# Respaldo con una tendencia conocida: sube un 1 % por sesión, nivel ~50.
respaldo = pd.Series(50.0 * (1.01 ** np.arange(20)), index=fechas)
p = pd.DataFrame({"brent": principal, "wti": respaldo})
r = indice.empalmar(p, "brent", "wti")

ok(len(r.dropna()) == 20, f"cubre las 20 sesiones (cubre {len(r.dropna())})")
ok(abs(float(r.iloc[10]) - 100.0) < 1e-9,
   "la fecha ancla conserva el valor de la principal (100)")
ok(float(r.iloc[9]) < 100.0,
   f"la sesión anterior al ancla queda por debajo de 100 ({r.iloc[9]:.2f})")
# El respaldo sube 1 % por sesión, así que hacia atrás cada paso divide por 1,01.
esperado_9 = 100.0 / 1.01
ok(abs(float(r.iloc[9]) - esperado_9) < 1e-6,
   f"reencadena con la rentabilidad del respaldo: {r.iloc[9]:.4f} "
   f"≈ {esperado_9:.4f}")
esperado_0 = 100.0 / (1.01 ** 10)
ok(abs(float(r.iloc[0]) - esperado_0) < 1e-6,
   f"y lo hace de forma acumulada hasta el inicio: {r.iloc[0]:.4f} "
   f"≈ {esperado_0:.4f}")

# La prueba decisiva: ninguna variación de la serie empalmada puede ser un
# salto que no esté en los datos originales.
var = np.log(r.dropna()).diff().dropna()
var_resp = np.log(respaldo).diff().dropna()
ok(abs(float(var.max()) - float(var_resp.max())) < 1e-9,
   "la variación máxima es la del respaldo: el empalme NO mete un salto")
print(f"       variación máxima empalmada {float(var.max()):.6f} vs "
      f"respaldo {float(var_resp.max()):.6f}")

# --- Caso 2: pegar niveles a lo bruto, para ver qué se evita -------------
print("\n== Caso 2: contraste con el pegado ingenuo de niveles ==")
ingenuo = principal.copy()
ingenuo.loc[ingenuo.isna()] = respaldo.loc[ingenuo.isna()]
salto_ingenuo = float(np.log(ingenuo).diff().abs().max())
salto_bueno = float(var.abs().max())
ok(salto_ingenuo > 10 * salto_bueno,
   f"pegar niveles metería un salto {salto_ingenuo:.3f} frente a "
   f"{salto_bueno:.3f} del empalme correcto")

# --- Caso 3: sin respaldo, devuelve la principal intacta -----------------
print("\n== Caso 3: degradación cuando falta una de las dos ==")
solo_p = pd.DataFrame({"brent": principal})
r3 = indice.empalmar(solo_p, "brent", "wti")
ok(r3.dropna().equals(principal.dropna()),
   "sin respaldo devuelve la principal sin tocarla")

solo_r = pd.DataFrame({"wti": respaldo})
r4 = indice.empalmar(solo_r, "brent", "wti")
ok(len(r4.dropna()) == 20 and abs(float(r4.iloc[0]) - 50.0) < 1e-9,
   "sin principal devuelve el respaldo tal cual")

r5 = indice.empalmar(pd.DataFrame({"otra": principal}), "brent", "wti")
ok(r5.dropna().empty, "sin ninguna de las dos devuelve serie vacía")

# --- Caso 4: la principal no tiene huecos previos ------------------------
print("\n== Caso 4: la principal ya cubre todo el rango ==")
completa = pd.Series(np.linspace(80, 120, 20), index=fechas)
r6 = indice.empalmar(pd.DataFrame({"brent": completa, "wti": respaldo}),
                     "brent", "wti")
ok(np.allclose(r6.values, completa.values),
   "no altera nada si la principal ya cubre todo")

print("\n" + (f"{len(fallos)} FALLOS" if fallos else "Todas las comprobaciones pasan."))
sys.exit(1 if fallos else 0)
