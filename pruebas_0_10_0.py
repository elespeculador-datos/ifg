# -*- coding: utf-8 -*-
"""
Prueba de los caminos de código nuevos de la 0.10.0 con datos locales.

No puede probar los números definitivos: precios.csv local no tiene ^GSPC ni
CL=F, que es justo lo que hay que descargar. Lo que SÍ prueba, con datos
reales, es que la maquinaria nueva funciona y degrada bien:

  1. El tramo y la variación salen del valor crudo, no del suavizado.
  2. El denominador de refugios es configurable y se usa.
  3. El empalme del crudo se activa cuando hay respaldo y no cuando no.
  4. Si falta el factor de mercado, el cálculo no reventa.
  5. descomponer_dia expone valor, valor_crudo y valor_tendencia, y "valor"
     es el crudo.

Para los puntos 1-3 se usa el Stoxx 600 como factor y denominador, porque sí
está en los datos locales: así se ejercita la neutralización de beta de
verdad en vez de saltársela.
"""
import sys

import numpy as np
import pandas as pd

import config   # noqa: E402
import indice   # noqa: E402

BASE = "."
fallos = []


def ok(cond, msg):
    print(f"  [{' ok ' if cond else 'FALLO'}] {msg}")
    if not cond:
        fallos.append(msg)


p = pd.read_csv(f"{BASE}/datos/precios.csv", index_col=0, parse_dates=True)
g = pd.read_csv(f"{BASE}/datos/gpr.csv", index_col=0, parse_dates=True)["gpr"]
pr = pd.read_csv(f"{BASE}/datos/prima.csv", index_col=0, parse_dates=True).iloc[:, 0]

print("\n== 1. Con factor y denominador presentes (Stoxx 600) ==")
config.FACTOR_MERCADO = "stoxx600"
config.DENOMINADOR_BOLSA = "stoxx600"
res = indice.calcular(p, gpr=g, prima=pr, gdelt=None)
t = res["tabla"]

ok(not t["ifg"].dropna().empty, f"el índice emite ({len(t['ifg'].dropna())} sesiones)")

# El tramo tiene que derivarse del crudo.
sub = t.dropna(subset=["ifg", "tramo"])
esperado = sub["ifg"].map(indice.tramo)
ok(esperado.equals(sub["tramo"]), "el tramo se deriva del valor CRUDO")
desde_suave = sub["ifg_suavizado"].map(indice.tramo)
ok(not desde_suave.equals(sub["tramo"]),
   "y NO coincide con el que daría el suavizado (si coincidiera, "
   "el cambio no estaría surtiendo efecto)")
dif = int((desde_suave != sub["tramo"]).sum())
print(f"       sesiones en que los dos tramos difieren: {dif} de {len(sub)}")

# La variación también.
v = sub["ifg"].diff().round(2).dropna()
ok(np.allclose(v.values, sub["variacion"].dropna().reindex(v.index).values,
               equal_nan=True),
   "la variación se calcula sobre el crudo")

ok("oro/stoxx600(+)" in res["detalle"].get("refugios", []),
   f"el denominador de refugios es configurable: {res['detalle'].get('refugios')}")

print("\n== 2. descomponer_dia: ninguna clave desaparece ==")
fecha = res["contribuciones"].dropna(how="all").index[-1]
d = indice.descomponer_dia(res, fecha)
for clave in ("valor", "valor_crudo", "valor_tendencia", "variacion",
              "tramo", "cobertura", "motores", "version"):
    ok(clave in d, f"existe la clave '{clave}'")
ok(abs(d["valor"] - float(t.loc[fecha, "ifg"])) < 1e-9,
   f"'valor' es el crudo ({d['valor']})")
ok(abs(d["valor_tendencia"] - float(t.loc[fecha, "ifg_suavizado"])) < 1e-9,
   f"'valor_tendencia' es el suavizado ({d['valor_tendencia']})")
ok(d["valor"] == d["valor_crudo"], "'valor_crudo' coincide con 'valor'")
ok(d["version"] == "0.10.0", f"la versión que se publica es {d['version']}")

print("\n== 3. El empalme del crudo, sin respaldo ==")
#
# ESTA SECCIÓN ESTUVO MAL ESCRITA Y HAY QUE DEJARLO ANOTADO. Afirmaba que
# datos/precios.csv NO traía la columna del respaldo, y era cierto hasta que
# la republicación de la 0.10.0 descargó WTI. Entonces las tres
# comprobaciones empezaron a fallar sin que el código hubiera cambiado: la
# prueba dependía de lo que contuviera un fichero de datos mutable, que es
# justo lo que una prueba no debe hacer.
#
# Ahora el caso "sin respaldo" se construye quitando la columna, de modo que
# el resultado no depende de lo que haya descargado la última ejecución.
sin_respaldo = p.drop(columns=[config.CRUDO_RESPALDO], errors="ignore")
ok(config.CRUDO_RESPALDO not in sin_respaldo.columns,
   "el caso sin respaldo se construye quitando la columna, no confiando en "
   "que falte")
crudo = indice.empalmar(sin_respaldo, config.CRUDO_PRINCIPAL,
                        config.CRUDO_RESPALDO)
ok(crudo.dropna().index[0] == p["brent"].dropna().index[0],
   "sin respaldo, el crudo arranca donde arranca el Brent")
res_sin = indice.calcular(sin_respaldo, gpr=g, prima=pr, gdelt=None)
ok(res_sin["detalle"]["energia"] == ["brent(+)", "cobre(-)"],
   f"y el detalle lo refleja: {res_sin['detalle']['energia']}")

# Y si el respaldo SÍ está, como ocurre desde la 0.10.0, debe estar activo.
if config.CRUDO_RESPALDO in p.columns:
    crudo_real = indice.empalmar(p, config.CRUDO_PRINCIPAL,
                                 config.CRUDO_RESPALDO)
    ok(crudo_real.dropna().index[0] < p["brent"].dropna().index[0],
       f"con el respaldo real presente, el crudo arranca antes: "
       f"{crudo_real.dropna().index[0].date()} frente a "
       f"{p['brent'].dropna().index[0].date()}")
    ok(res["detalle"]["energia"][0] == "brent+wti(+)",
       f"y el detalle declara el empalme: {res['detalle']['energia']}")

# Con respaldo sintético que llega más atrás: debe extender el componente.
print("\n== 4. Con un respaldo sintético que llega más atrás ==")
p2 = p.copy()
base = p2["cobre"].dropna()          # cualquier serie larga sirve de forma
p2["wti"] = (base / base.iloc[0] * 60.0).reindex(p2.index)
crudo2 = indice.empalmar(p2, "brent", "wti")
ok(crudo2.dropna().index[0] < p["brent"].dropna().index[0],
   f"el crudo empalmado arranca antes: {crudo2.dropna().index[0].date()} "
   f"frente a {p['brent'].dropna().index[0].date()}")
junta = p["brent"].dropna().index[0]
antes = crudo2.loc[:junta].dropna()
salto = float(np.log(antes).diff().abs().max())
ok(salto < 0.25, f"y sin salto desmedido en la junta (máx {salto:.3f})")
res2 = indice.calcular(p2, gpr=g, prima=pr, gdelt=None)
ok(res2["detalle"]["energia"][0] == "brent+wti(+)",
   f"el detalle declara el empalme: {res2['detalle']['energia']}")
ok(res2["componentes"]["energia"].dropna().index[0]
   <= res["componentes"]["energia"].dropna().index[0],
   "y el componente de energía no arranca más tarde que antes")
print(f"       energia sin empalme: "
      f"{res['componentes']['energia'].dropna().index[0].date()}  ->  "
      f"con empalme: "
      f"{res2['componentes']['energia'].dropna().index[0].date()}")

print("\n== 5. Degradación si falta el factor de mercado ==")
config.FACTOR_MERCADO = "no_existe_esta_serie"
config.DENOMINADOR_BOLSA = "no_existe_esta_serie"
try:
    res3 = indice.calcular(p, gpr=g, prima=pr, gdelt=None)
    ok(not res3["tabla"]["ifg"].dropna().empty,
       "el cálculo sigue dando valores sin factor de mercado")
    ok("refugios" in res3["componentes"].columns,
       "y refugios sigue existiendo con las patas de divisa")
except Exception as e:                       # noqa: BLE001
    ok(False, f"revienta sin factor de mercado: {type(e).__name__}: {e}")

print("\n" + (f"{len(fallos)} FALLOS" if fallos else "Todas las comprobaciones pasan."))
sys.exit(1 if fallos else 0)
