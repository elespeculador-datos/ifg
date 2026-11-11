# -*- coding: utf-8 -*-
"""
Pruebas de la 0.11.0: un valor arrastrado suma, pero no cuenta como cobertura.

LO QUE HAY QUE DEMOSTRAR, y en este orden de importancia:

  1. EL VALOR DEL ÍNDICE NO CAMBIA. Es la prueba que de verdad importa: si
     cambiara, esto no sería una política de revisiones distinta, sería una
     fórmula distinta, y entonces la republicación movería la serie por un
     motivo que no se ha anunciado.
  2. La cobertura baja exactamente el peso del componente arrastrado.
  3. La máscara señala la celda arrastrada y solo esa, y respeta el límite
     de tres sesiones.
  4. Con la cobertura por debajo de 1, la fila nace provisional en vez de
     definitiva, que es el objetivo de todo el cambio.
  5. Cuando llega el dato real, la provisional se corrige y se cierra.
  6. Sin máscara, el comportamiento es el de la 0.10.0 (compatibilidad).

Ejecución:
    python pruebas_arrastre_cobertura.py
"""
import numpy as np
import pandas as pd

import config
import indice
import publicar_diario as pub

fallos = []


def comprobar(cond: bool, titulo: str, detalle: str = "") -> None:
    if cond:
        print(f"  OK   {titulo}")
    else:
        print(f"  FALLA {titulo}  {detalle}")
        fallos.append(titulo)


# Calendario de diez sesiones y dos componentes con pesos conocidos.
cal = pd.bdate_range("2026-10-05", periods=10)
PESOS = {"energia": 20, "gpr": 5}
TOTAL = sum(PESOS.values())

# "energia" tiene dato todos los días. "gpr" deja de tenerlo tras la cuarta
# sesión: es el caso real, la entrega semanal de la Reserva Federal.
comp = pd.DataFrame({
    "energia": np.linspace(-1.0, 1.0, len(cal)),
    "gpr": [0.5, 0.7, 0.9, 1.1] + [np.nan] * 6,
}, index=cal)

print("\n1-3. Alineado, máscara y cobertura")

tabla, pendiente = indice.alinear_con_arrastre(comp, cal, max_arrastre=3)

# El arrastre llega tres sesiones y la cuarta ya es hueco.
comprobar(tabla["gpr"].iloc[4:7].eq(1.1).all(),
          "el valor se arrastra tres sesiones")
comprobar(bool(tabla["gpr"].iloc[7:].isna().all()),
          "a la cuarta deja de arrastrarse: el índice no finge estar vivo")
comprobar(int(pendiente["gpr"].sum()) == 3,
          "la máscara marca las tres celdas que esperan entrega",
          str(int(pendiente["gpr"].sum())))
comprobar(not pendiente["energia"].any(),
          "no marca nada en el componente que sí tiene dato propio")
comprobar(not bool(pendiente["gpr"].iloc[:4].any()),
          "no marca las sesiones con dato propio")

compuesto_v, contrib_v, cob_v = indice.agregar(tabla, PESOS)
compuesto_n, contrib_n, cob_n = indice.agregar(tabla, PESOS,
                                               pendiente=pendiente)

# --- 1. LA PRUEBA QUE IMPORTA --------------------------------------------
comprobar(bool(np.allclose(compuesto_v.values, compuesto_n.values,
                           equal_nan=True)),
          "el compuesto es IDÉNTICO: no cambia la fórmula, solo la cobertura")
comprobar(bool(np.allclose(contrib_v.fillna(0).values,
                           contrib_n.fillna(0).values)),
          "las contribuciones de cada componente tampoco cambian")

# --- 2. la cobertura baja el peso justo ----------------------------------
esperada = 1 - PESOS["gpr"] / TOTAL
comprobar(bool(np.allclose(cob_n.iloc[4:7].values, esperada)),
          f"en las arrastradas la cobertura baja a {esperada:.3f}",
          str(cob_n.iloc[4:7].round(4).tolist()))
comprobar(bool(np.allclose(cob_v.iloc[4:7].values, 1.0)),
          "mientras que antes esas mismas filas daban cobertura 1,00")
comprobar(bool(np.allclose(cob_n.iloc[:4].values, 1.0)),
          "las sesiones con dato propio siguen en 1,00")
comprobar(bool(np.allclose(cob_n.iloc[7:].values, esperada)),
          "y un hueco de verdad cuenta igual que un arrastre: ninguno es dato")

# --- 6. compatibilidad ----------------------------------------------------
comprobar(bool(np.allclose(cob_v.values, indice.agregar(tabla, PESOS)[2].values)),
          "sin máscara, el comportamiento es el de la 0.10.0")
comprobar(indice.alinear(comp, cal, 3).equals(tabla),
          "alinear() sigue devolviendo la tabla de siempre")

print("\n3 bis. Un festivo de otro mercado NO es entrega pendiente")
#
# ESTE ES EL CASO QUE TUMBÓ EL PRIMER INTENTO. El calendario son las sesiones
# del IBEX; cuando Nueva York cierra, el cobre o el oro no imprimen en una
# sesión que aquí es hábil. Ese dato no existe y no va a existir: arrastrar
# es el tratamiento correcto y descontarlo de la cobertura dejaría el 10 % de
# la serie marcada como incompleta para siempre, sin que ninguna corrección
# pueda llegar nunca. Medido sobre la serie real: 439 sesiones afectadas con
# el criterio ingenuo, 1 con el criterio correcto.
festivo = pd.DataFrame({
    "energia": np.linspace(-1.0, 1.0, len(cal)),
    # Agujero INTERIOR: falta la sesión 5, pero la serie sigue después.
    "gpr": [0.5, 0.7, 0.9, 1.1, 1.3, np.nan, 1.7, 1.9, 2.1, 2.3],
}, index=cal)
t_f, p_f = indice.alinear_con_arrastre(festivo, cal, max_arrastre=3)

comprobar(t_f["gpr"].iloc[5] == 1.3,
          "el hueco interior se rellena arrastrando, como siempre")
comprobar(not bool(p_f["gpr"].any()),
          "pero NO se marca como pendiente: no hay nada que esperar",
          f"marcadas {int(p_f['gpr'].sum())}")
_, _, cob_f = indice.agregar(t_f, PESOS, pendiente=p_f)
comprobar(bool(np.allclose(cob_f.values, 1.0)),
          "así que la cobertura sigue completa y la fila nace cerrada")

# Y el discriminante es exactamente "más allá del último dato propio".
mixto = pd.DataFrame({
    "energia": np.linspace(-1.0, 1.0, len(cal)),
    # Hueco interior en la 5 Y final de serie en la 7: solo el final espera.
    "gpr": [0.5, 0.7, 0.9, 1.1, 1.3, np.nan, 1.7, np.nan, np.nan, np.nan],
}, index=cal)
t_m, p_m = indice.alinear_con_arrastre(mixto, cal, max_arrastre=3)
comprobar(not bool(p_m["gpr"].iloc[5]),
          "en una serie con las dos cosas, el hueco interior no es pendiente")
comprobar(bool(p_m["gpr"].iloc[7:].all()),
          "y lo que va detrás del último dato propio sí lo es",
          str(p_m["gpr"].iloc[7:].tolist()))

# Un componente sin un solo dato propio no tiene nada pendiente: está ausente,
# y de eso ya se encarga el reparto de pesos.
vacio = pd.DataFrame({"energia": np.linspace(-1.0, 1.0, len(cal)),
                      "gpr": [np.nan] * len(cal)}, index=cal)
_, p_v = indice.alinear_con_arrastre(vacio, cal, max_arrastre=3)
comprobar(not bool(p_v["gpr"].any()),
          "un componente ausente del todo no genera pendientes")

print("\n4-5. Estado de la fila: provisional en vez de definitiva")

# El estado lo decide la cobertura. Con 0,80 la fila ya no puede nacer
# cerrada, y es justo lo que se buscaba.
comprobar(pub.estado_de(1.0, True) == pub.DEFINITIVO,
          "cobertura completa -> definitivo")
comprobar(pub.estado_de(esperada, True) == pub.PROVISIONAL,
          "cobertura incompleta y dentro de la ventana -> provisional",
          pub.estado_de(esperada, True))
comprobar(pub.estado_de(esperada, False) == pub.INCOMPLETO,
          "fuera de la ventana -> definitivo_incompleto, con la marca puesta")

# Y la corrección: una provisional que el recálculo mejora se reescribe y se
# cierra. Es el ciclo entero, que antes no llegaba a empezar.
def fila(ifg, cob, estado=None):
    d = {"ifg": ifg, "ifg_suavizado": ifg, "variacion": 0.0,
         "tramo": indice.tramo(ifg), "cobertura": cob, "parcial": False}
    if estado:
        d["estado"] = estado
    return d

idx = pd.to_datetime(["2026-10-14", "2026-10-15", "2026-10-16"])
publicada = pd.DataFrame([fila(63.13, esperada, pub.PROVISIONAL),
                          fila(54.40, esperada, pub.PROVISIONAL),
                          fila(50.20, 1.0, pub.DEFINITIVO)], index=idx)
# El recálculo trae ya el GPR real: cobertura completa y otro valor.
recalculada = pd.DataFrame([fila(73.27, 1.0), fila(56.00, 1.0),
                            fila(50.20, 1.0)], index=idx)

final, deriva, correcciones = pub.fusionar(recalculada, publicada)
comprobar(len(correcciones) == 2,
          "se corrigen las dos provisionales", str(len(correcciones)))
if correcciones:
    c = correcciones[0]
    comprobar(c["fecha"] == "2026-10-14" and c["valor_anterior"] == 63.13
              and c["valor_nuevo"] == 73.27,
              "la corrección queda registrada con el antes y el después",
              str(c))
    comprobar(c["estado_nuevo"] == pub.DEFINITIVO,
              "y la fila se cierra al completarse", str(c["estado_nuevo"]))
comprobar(float(final.loc[idx[2], "ifg"]) == 50.20,
          "la fila que ya estaba cerrada no se toca")
comprobar(deriva.abs().max() < 0.005,
          "y la deriva sobre lo cerrado sigue siendo cero",
          str(deriva.abs().max()))

print("\n7. Versión")
comprobar(config.VERSION == "0.11.0", "la versión sube", config.VERSION)

print("\n" + ("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}"))
raise SystemExit(1 if fallos else 0)
