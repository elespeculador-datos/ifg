"""
Comprobaciones del rastreador de cortos. No tocan la red.

Cubren el fallo del 29 y 30 de octubre de 2026 (incidencia #65): la hoja
«Última» de la CNMV trajo dos filas con el mismo ISIN y el mismo tenedor y
`cambios()` se detuvo con un TypeError, porque indexar por esa clave devolvía
una Series donde el código esperaba un número.

Uso:  python cortos/pruebas_rastreador.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rastreador as r  # noqa: E402

fallos: list[str] = []


def comprobar(descripcion: str, condicion: bool) -> None:
    print(("  ok  " if condicion else "FALLO ") + descripcion)
    if not condicion:
        fallos.append(descripcion)


def fila(isin, tenedor, pct, fecha, emisor="Emisor S.A.", lei="L0"):
    return {"lei": lei, "isin": isin, "emisor": emisor, "tenedor": tenedor,
            "fecha_posicion": fecha, "posicion_pct": pct}


# --------------------------------------------------------------- sin duplicados
previo = pd.DataFrame([
    fila("ES01", "Fondo A", 0.80, "2026-10-20"),
    fila("ES01", "Fondo B", 0.60, "2026-10-21"),
    fila("ES02", "Fondo C", 1.20, "2026-10-19", emisor="Otra S.A.", lei="L1"),
])

vigentes = pd.DataFrame([
    fila("ES01", "Fondo A", 0.95, "2026-10-29"),   # sube
    fila("ES02", "Fondo C", 1.20, "2026-10-19", emisor="Otra S.A.", lei="L1"),  # igual
    fila("ES03", "Fondo D", 0.55, "2026-10-29", emisor="Tercera S.A.", lei="L2"),  # nueva
])                                                  # Fondo B deja de publicarse

cam = r.cambios(previo, vigentes, "2026-10-29")
tipos = dict(zip(cam["tenedor"], cam["tipo"]))
comprobar("sin duplicados: detecta la subida de Fondo A", tipos.get("Fondo A") == "sube")
comprobar("sin duplicados: detecta el alta de Fondo D", tipos.get("Fondo D") == "nueva")
comprobar("sin duplicados: detecta que Fondo B deja de publicarse",
          tipos.get("Fondo B") == "deja de publicarse")
comprobar("sin duplicados: una posición idéntica no genera cambio", "Fondo C" not in tipos)
comprobar("sin duplicados: ni un cambio de más", len(cam) == 3)

# ------------------------------------------------- el caso que detuvo el flujo
# El mismo tenedor, dos veces sobre el mismo valor: la posición y la
# comunicación con la que cruza el 0,5 %. Antes del arreglo, TypeError.
dup = pd.DataFrame([
    fila("ES01", "Fondo A", 0.80, "2026-10-26"),   # comunicación antigua
    fila("ES01", "Fondo A", 0.45, "2026-10-29"),   # la que retrata el día
    fila("ES02", "Fondo C", 1.20, "2026-10-19", emisor="Otra S.A.", lei="L1"),
])

try:
    cam2 = r.cambios(previo, dup, "2026-10-29")
    reventado = False
except TypeError:
    cam2 = pd.DataFrame()
    reventado = True

comprobar("con la clave duplicada: cambios() ya no se detiene", not reventado)
if not reventado:
    f = cam2[cam2["tenedor"] == "Fondo A"]
    comprobar("con la clave duplicada: gana la fecha_posicion más reciente",
              len(f) == 1 and abs(float(f.iloc[0]["ahora_pct"]) - 0.45) < 1e-9)
    comprobar("con la clave duplicada: el cambio se registra como bajada",
              len(f) == 1 and f.iloc[0]["tipo"] == "baja")
    comprobar("con la clave duplicada: una sola fila por tenedor y valor",
              not cam2.duplicated(subset=["isin", "tenedor"]).any())

# ------------------------------------------- a igualdad de fecha, la última fila
empate = pd.DataFrame([
    fila("ES01", "Fondo A", 0.70, "2026-10-29"),
    fila("ES01", "Fondo A", 0.90, "2026-10-29"),
    fila("ES02", "Fondo C", 1.20, "2026-10-19", emisor="Otra S.A.", lei="L1"),
])
cam3 = r.cambios(previo, empate, "2026-10-29")
f3 = cam3[cam3["tenedor"] == "Fondo A"]
comprobar("empate de fecha: se queda con la última fila del fichero",
          len(f3) == 1 and abs(float(f3.iloc[0]["ahora_pct"]) - 0.90) < 1e-9)

# --------------------------------------------------- la suma publicada no se infla
res_dup = r.resumen(pd.DataFrame([
    fila("ES01", "Fondo A", 0.80, "2026-10-26"),
    fila("ES01", "Fondo A", 0.90, "2026-10-29"),   # el mismo tenedor, más reciente
    fila("ES01", "Fondo B", 0.60, "2026-10-28"),
]))
suma = float(res_dup.loc[res_dup["isin"] == "ES01", "suma_publicada_pct"].iloc[0])
comprobar("resumen(): no suma dos veces al mismo tenedor (0,90 + 0,60 = 1,50)",
          abs(suma - 1.50) < 1e-9)
comprobar("resumen(): cuenta un tenedor por nombre, no por comunicación",
          int(res_dup.loc[res_dup["isin"] == "ES01", "tenedores"].iloc[0]) == 2)

res_limpio = r.resumen(pd.DataFrame([
    fila("ES01", "Fondo A", 0.90, "2026-10-29"),
    fila("ES01", "Fondo B", 0.60, "2026-10-28"),
]))
comprobar("resumen(): sin duplicados da exactamente lo mismo que antes",
          abs(float(res_limpio.loc[res_limpio["isin"] == "ES01", "suma_publicada_pct"].iloc[0]) - 1.50) < 1e-9)

# ----------------------------------------------- la fila de bajada sigue contando
# `_una_por_clave` no debe tocar el DataFrame cuando la clave ya es única:
# la hoja «Última» incluye por diseño comunicaciones por debajo del 0,5 %.
unico = pd.DataFrame([fila("ES01", "Fondo A", 0.45, "2026-10-29"),
                      fila("ES01", "Fondo B", 0.60, "2026-10-28")])
comprobar("clave ya única: el DataFrame se devuelve intacto",
          r._una_por_clave(unico, ["isin", "tenedor"], "prueba").equals(unico))

print()
if fallos:
    print(f"{len(fallos)} comprobaciones han fallado.")
    sys.exit(1)
print("Todas las comprobaciones pasan.")
