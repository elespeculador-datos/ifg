"""Clasificación sectorial propia de El Especulador (ocho sectores) para los agregados por sector de los
indicadores de cortos (1) y de directivos (10). La tabla está en `cortos/sectores.csv` y la asigna Datos
a mano a partir de la actividad que declara cada empresa; no usa la clasificación de BME ni la de la CNMV.

Uso:
    from cortos import sectores
    tabla = sectores.cargar()                 # {isin: fila}
    sectores.sector_de("ES0173516115", tabla) # "energia-utilities"
    sectores.sin_sector(isines, tabla)        # ISIN que no están en la tabla (abren aviso, no incidencia)
"""

import csv
import os

VERSION = "1.0.0"
RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sectores.csv")

SECTORES = {
    "energia-utilities": "Energía y utilities",
    "industria-construccion": "Industria y construcción",
    "consumo": "Consumo, medios y ocio",
    "financiero-seguros": "Financiero y seguros",
    "inmobiliario": "Inmobiliario",
    "tecnologia-telecomunicaciones": "Tecnología y telecomunicaciones",
    "salud-farmacia": "Salud y farmacia",
    "turismo-transporte": "Turismo y transporte",
}
SIN_SECTOR = "sin-sector"


def cargar(ruta=RUTA):
    """Tabla {isin: fila} del CSV; para si un sector no está en la lista o un ISIN se repite."""
    tabla = {}
    with open(ruta, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            isin = fila["isin"].strip().upper()
            if fila["sector"] not in SECTORES:
                raise ValueError(f"sector desconocido en sectores.csv: {fila['sector']} ({isin})")
            if isin in tabla:
                raise ValueError(f"ISIN repetido en sectores.csv: {isin}")
            tabla[isin] = fila
    return tabla


def sector_de(isin, tabla):
    """Clave del sector del ISIN, o 'sin-sector' si no está clasificado."""
    fila = tabla.get((isin or "").strip().upper())
    return fila["sector"] if fila else SIN_SECTOR


def nombre_sector(clave):
    return SECTORES.get(clave, "Sin sector")


def sin_sector(isines, tabla):
    """ISIN (sin repetir, ordenados) que no están en la tabla: el colector avisa y los agrega como 'sin-sector'."""
    return sorted({(i or "").strip().upper() for i in isines if (i or "").strip().upper() not in tabla})


def agregar(filas, tabla, isin="isin", valor="valor"):
    """Suma `valor` por sector a partir de filas con ISIN. Devuelve {sector: {"valor": suma, "emisores": n}}."""
    salida = {}
    vistos = {}
    for fila in filas:
        clave = sector_de(fila.get(isin), tabla)
        grupo = salida.setdefault(clave, {"valor": 0.0, "emisores": 0})
        grupo["valor"] += float(fila.get(valor) or 0)
        vistos.setdefault(clave, set()).add((fila.get(isin) or "").strip().upper())
    for clave, grupo in salida.items():
        grupo["emisores"] = len(vistos[clave])
        grupo["valor"] = round(grupo["valor"], 6)
    return salida
