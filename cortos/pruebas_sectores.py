"""Comprobaciones sin red de la clasificación sectorial propia (`cortos/sectores.csv` y `cortos/sectores.py`):
cobertura del IBEX 35 y de todos los emisores con posiciones cortas en los últimos doce meses del repositorio,
integridad de la tabla y agregado por sector."""

import csv
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import sectores  # noqa: E402

FALLOS = []
TOTAL = 0


def ok(cond, texto):
    global TOTAL
    TOTAL += 1
    if not cond:
        FALLOS.append(texto)
        print("FALLA:", texto)


tabla = sectores.cargar()
ok(len(tabla) >= 59, f"La tabla tiene al menos 59 emisores (tiene {len(tabla)})")
ok(all(f["actividad"].strip() and f["fuente"].strip() and f["asignado"].strip() for f in tabla.values()),
   "Toda fila lleva actividad, fuente y fecha de asignación")
ok(set(f["sector"] for f in tabla.values()) == set(sectores.SECTORES), "Los ocho sectores están usados y no hay otros")
ok(all(len(i) == 12 and i.isalnum() and i.isupper() for i in tabla), "Todos los ISIN tienen 12 caracteres alfanuméricos")

# Cobertura del IBEX 35 (composición del repositorio).
ibex = [r["isin"] for r in csv.DictReader(open(os.path.join(RAIZ, "dividendos", "ibex35.csv"), encoding="utf-8"))]
ok(len(ibex) == 35, "La composición del IBEX tiene 35 valores")
faltan = sectores.sin_sector(ibex, tabla)
ok(not faltan, f"Todo el IBEX 35 tiene sector (faltan: {faltan})")

# Cobertura de los emisores con cortos en los últimos doce meses de los datos guardados en el repositorio.
desde = "2025-11-01"
cortos = set()
for nombre in ("serie.csv", "anteriores.csv", "vigentes.csv"):
    ruta = os.path.join(RAIZ, "docs", "cortos", "datos", nombre)
    if os.path.exists(ruta):
        for r in csv.DictReader(open(ruta, encoding="utf-8")):
            if r["fecha_posicion"] >= desde:
                cortos.add(r["isin"])
ok(len(cortos) >= 40, f"Hay al menos 40 emisores con cortos desde {desde} en el repositorio ({len(cortos)})")
faltan = sectores.sin_sector(cortos, tabla)
ok(not faltan, f"Todo emisor con cortos recientes tiene sector (faltan: {faltan})")

# Asignaciones concretas.
ok(sectores.sector_de("ES0173516115", tabla) == "energia-utilities", "Repsol: energía y utilities")
ok(sectores.sector_de("ES0113900J37", tabla) == "financiero-seguros", "Santander: financiero y seguros")
ok(sectores.sector_de("ES0148396007", tabla) == "consumo", "Inditex: consumo")
ok(sectores.sector_de("ES0171996087", tabla) == "salud-farmacia", "Grifols: salud y farmacia")
ok(sectores.sector_de("ES0177542018", tabla) == "turismo-transporte", "IAG: turismo y transporte")
ok(sectores.sector_de("ES0105025003", tabla) == "inmobiliario", "Merlin: inmobiliario")
ok(sectores.sector_de("ES0178430E18", tabla) == "tecnologia-telecomunicaciones", "Telefónica: tecnología y telecomunicaciones")
ok(sectores.sector_de("NL0015001FS8", tabla) == "industria-construccion", "Ferrovial: industria y construcción")
ok(sectores.sector_de("es0173516115", tabla) == "energia-utilities", "El ISIN en minúsculas se normaliza")
ok(sectores.sector_de("XX0000000000", tabla) == sectores.SIN_SECTOR, "ISIN desconocido -> sin-sector")
ok(sectores.sector_de(None, tabla) == sectores.SIN_SECTOR, "ISIN vacío -> sin-sector")
ok(sectores.nombre_sector("energia-utilities") == "Energía y utilities" and sectores.nombre_sector("zzz") == "Sin sector", "Nombres legibles")
ok(sectores.sin_sector(["ES0173516115", "XX0000000000", "xx0000000000"], tabla) == ["XX0000000000"], "sin_sector no repite ni cuenta los conocidos")

# Agregado por sector.
filas = [{"isin": "ES0173516115", "valor": "1.5"}, {"isin": "ES0144580Y14", "valor": 2.0},
         {"isin": "ES0113900J37", "valor": 0.7}, {"isin": "XX0000000000", "valor": 0.3}, {"isin": "ES0173516115", "valor": None}]
agg = sectores.agregar(filas, tabla)
ok(abs(agg["energia-utilities"]["valor"] - 3.5) < 1e-9 and agg["energia-utilities"]["emisores"] == 2, "Agregado: suma y recuento de emisores por sector")
ok(abs(agg["financiero-seguros"]["valor"] - 0.7) < 1e-9, "Agregado: sector con un emisor")
ok(abs(agg["sin-sector"]["valor"] - 0.3) < 1e-9 and agg["sin-sector"]["emisores"] == 1, "Agregado: los desconocidos van a sin-sector")

# Integridad: sector desconocido o ISIN repetido paran la carga.
with tempfile.TemporaryDirectory() as d:
    ruta = os.path.join(d, "s.csv")
    open(ruta, "w", encoding="utf-8").write("isin,emisor,sector,actividad,fuente,asignado,nota\nES0173516115,Repsol,petroleo,x,y,z,\n")
    try:
        sectores.cargar(ruta)
        ok(False, "Sector desconocido debe parar")
    except ValueError:
        ok(True, "Sector desconocido para la carga")
    open(ruta, "w", encoding="utf-8").write("isin,emisor,sector,actividad,fuente,asignado,nota\nES0173516115,Repsol,energia-utilities,x,y,z,\nES0173516115,Repsol,energia-utilities,x,y,z,\n")
    try:
        sectores.cargar(ruta)
        ok(False, "ISIN repetido debe parar")
    except ValueError:
        ok(True, "ISIN repetido para la carga")

print(f"{TOTAL - len(FALLOS)}/{TOTAL} comprobaciones superadas")
sys.exit(1 if FALLOS else 0)
