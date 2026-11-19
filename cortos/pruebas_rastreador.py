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

# ------------------------------------------------- lo nuevo del indicador 1: sector, evolución, semana
res_s = pd.DataFrame([
    {"isin": "ES0173516115", "emisor": "REPSOL, S.A.", "tenedores": 2, "suma_publicada_pct": 1.2, "mayor_posicion_pct": 0.7, "ultima_fecha_posicion": "2026-10-27", "mayor_tenedor": "Fondo A"},
    {"isin": "ES0144580Y14", "emisor": "IBERDROLA, S.A.", "tenedores": 1, "suma_publicada_pct": 0.6, "mayor_posicion_pct": 0.6, "ultima_fecha_posicion": "2026-10-20", "mayor_tenedor": "Fondo B"},
    {"isin": "ES0171996087", "emisor": "GRIFOLS, S.A.", "tenedores": 3, "suma_publicada_pct": 2.5, "mayor_posicion_pct": 1.1, "ultima_fecha_posicion": "2026-10-28", "mayor_tenedor": "Fondo C"},
    {"isin": "XX0000000000", "emisor": "DESCONOCIDA, S.A.", "tenedores": 1, "suma_publicada_pct": 0.5, "mayor_posicion_pct": 0.5, "ultima_fecha_posicion": "2026-10-28", "mayor_tenedor": "Fondo D"},
])
comprobar("sectores: la tabla sectorial se carga", r.SECTORES is not None and len(r.SECTORES) >= 59)
sec = r.por_sector(res_s)
por = {x.sector: x for x in sec.itertuples()}
comprobar("por_sector: energía agrega Repsol e Iberdrola (1,80 %, 2 emisores, 3 tenedores)",
          por["energia-utilities"].emisores == 2 and abs(por["energia-utilities"].suma_pct - 1.8) < 1e-9 and por["energia-utilities"].tenedores == 3)
comprobar("por_sector: media por emisor y mayor presión", abs(por["energia-utilities"].media_pct - 0.9) < 1e-9 and por["energia-utilities"].mayor_emisor == "REPSOL, S.A.")
comprobar("por_sector: orden por suma (salud primero, con 2,50 %)", sec.iloc[0]["sector"] == "salud-farmacia")
comprobar("por_sector: el ISIN desconocido va a «sin sector»", "sin-sector" in por and por["sin-sector"].emisores == 1)
comprobar("por_sector: sin filas devuelve None", r.por_sector(res_s.iloc[0:0]) is None)

historia = pd.DataFrame([
    fila("ES0173516115", "Fondo A", 0.70, "2025-10-01"), fila("ES0173516115", "Fondo A", 0.55, "2026-07-01"), fila("ES0173516115", "Fondo A", 0.70, "2026-10-27"),
    fila("ES0173516115", "Fondo E", 0.60, "2026-09-15"), fila("ES0173516115", "Fondo E", 0.40, "2026-10-10"),   # Fondo E baja del umbral el 10/10
    fila("ES0171996087", "Fondo C", 1.10, "2026-01-05"),
])
comprobar("suma_en: hoy Repsol 0,70 (Fondo E ya no cuenta)", r.suma_en(historia, "ES0173516115", "2026-10-28") == 0.70)
comprobar("suma_en: hace cuatro semanas Repsol 1,15 (Fondo A 0,55 + Fondo E 0,60)", r.suma_en(historia, "ES0173516115", "2026-09-30") == 1.15)
comprobar("suma_en: hace un año Repsol 0,70 (solo Fondo A)", r.suma_en(historia, "ES0173516115", "2025-10-29") == 0.70)
comprobar("suma_en: sin historia, cero", r.suma_en(historia, "ES0144580Y14", "2026-10-28") == 0.0)
evo = r.evolucion(historia, res_s, "2026-10-28", n=2)
comprobar("evolucion: dos emisores, columnas de 4, 13 y 52 semanas",
          list(evo.columns) == ["isin", "emisor", "ahora_pct", "hace_4_pct", "hace_13_pct", "hace_52_pct"] and len(evo) == 2)
fila_rep = evo[evo["isin"] == "ES0173516115"].iloc[0]
comprobar("evolucion: Repsol ahora 1,20 (de la publicación), hace 4 semanas 1,15, hace 52 0,70",
          fila_rep["ahora_pct"] == 1.2 and fila_rep["hace_4_pct"] == 1.15 and fila_rep["hace_52_pct"] == 0.70)

historial = pd.DataFrame([
    {"fecha_publicacion": "2026-10-27", "isin": "ES01", "emisor": "Uno S.A.", "tenedor": "Fondo A", "tipo": "nueva", "antes_pct": None, "ahora_pct": 0.5, "fecha_posicion": "2026-10-26"},
    {"fecha_publicacion": "2026-10-24", "isin": "ES02", "emisor": "Dos S.A.", "tenedor": "Fondo B", "tipo": "deja de publicarse", "antes_pct": 0.6, "ahora_pct": None, "fecha_posicion": None},
    {"fecha_publicacion": "2026-10-23", "isin": "ES01", "emisor": "Uno S.A.", "tenedor": "Fondo C", "tipo": "sube", "antes_pct": 0.5, "ahora_pct": 0.7, "fecha_posicion": "2026-10-22"},
    {"fecha_publicacion": "2026-10-10", "isin": "ES03", "emisor": "Tres S.A.", "tipo": "nueva", "tenedor": "Fondo D", "antes_pct": None, "ahora_pct": 0.9, "fecha_posicion": "2026-10-09"},
])
sem = r.semana(historial, "2026-10-28")
comprobar("semana: ventana de siete días, una entrada, una salida, una subida", sem["desde"] == "2026-10-21" and len(sem["entradas"]) == 1 and len(sem["salidas"]) == 1 and sem["subidas"] == 1 and sem["bajadas"] == 0)
comprobar("semana: la entrada de hace tres semanas queda fuera", all(x["emisor"] != "Tres S.A." for x in sem["entradas"]))
comprobar("semana: detalle de la salida con el porcentaje anterior", sem["salidas"][0]["antes_pct"] == 0.6 and sem["salidas"][0]["pct"] is None)
comprobar("semana: sin historial, vacío", r.semana(None, "2026-10-28")["entradas"] == [])

vig_s = pd.DataFrame([fila("ES0173516115", "Fondo A", 0.70, "2026-10-27", emisor="REPSOL, S.A."), fila("ES0173516115", "Fondo E", 0.50, "2026-10-20", emisor="REPSOL, S.A."),
                      fila("ES0171996087", "Fondo C", 1.10, "2026-10-28", emisor="GRIFOLS, S.A.", lei="L1")])
frag = r.fragmento_wp("2026-10-28", "2026-10-27", vig_s, res_s, pd.DataFrame(columns=["emisor", "tenedor", "tipo", "antes_pct", "ahora_pct"]), None, sec, evo, sem)
comprobar("fragmento: tabla por sector, evolución y semana", "<h2>Presión bajista por sector</h2>" in frag and "Hace 52 semanas" in frag and "<h2>Entradas y salidas de la semana</h2>" in frag)
comprobar("fragmento: nombres de sector y nota de clasificación propia", "Energía y utilities" in frag and "clasificación propia" in frag)
comprobar("fragmento: sin el símbolo del dólar", "$" not in frag.replace("&#36;", ""))
frag0 = r.fragmento_wp("2026-10-28", "2026-10-27", vig_s, res_s, pd.DataFrame(columns=["emisor", "tenedor", "tipo", "antes_pct", "ahora_pct"]), None)
comprobar("fragmento: sin los bloques nuevos sigue funcionando como antes", "Presión bajista por sector" not in frag0 and "<h2>Suma publicada por emisor</h2>" in frag0)

print()
if fallos:
    print(f"{len(fallos)} comprobaciones han fallado.")
    sys.exit(1)
print("Todas las comprobaciones pasan.")
