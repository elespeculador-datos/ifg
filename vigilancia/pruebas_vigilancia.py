"""Pruebas de vigilancia.py (sin red): empresa sin comunicados, empresa callada más de DIAS_MAX días, listado vacío,
y el caso real del 24/11/2026 (Logista y Colonial sin comunicados por sus alias antiguos).

Uso: python3 vigilancia/pruebas_vigilancia.py
"""
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vigilancia as v  # noqa: E402

fallos = 0
total = 0


def ok(cond: bool, texto: str) -> None:
    global fallos, total
    total += 1
    if not cond:
        fallos += 1
    print(("ok     " if cond else "FALLO  ") + texto)


HOY = date(2026, 11, 25)
EMPRESAS = pd.DataFrame([
    {"isin": "ES0000000001", "nombre": "Alfa", "ficha": "alfa", "patron": "^ALFA"},
    {"isin": "ES0105027009", "nombre": "Logista", "ficha": "logista", "patron": "LOGISTA HOLDINGS"},
    {"isin": "ES0139140174", "nombre": "Colonial", "ficha": "colonial", "patron": r"^INMOBILIARIA COLONIAL\b"},
    {"isin": "ES0000000004", "nombre": "Delta", "ficha": "delta", "patron": "^DELTA"},
])


def fila(isin: str, fecha: str) -> dict:
    return {"canal": "OIR", "nreg": "1", "fecha": fecha + "T09:00:00", "emisor": "X", "isin": isin}


# Todo bien: cada empresa con un comunicado reciente.
bien = [fila("ES0000000001", "2026-11-20"), fila("ES0105027009", "2026-11-06"), fila("ES0139140174", "2026-11-12"), fila("ES0000000004", "2026-07-01")]
r = v.revisar(bien, EMPRESAS, HOY)
ok(r["problemas"] == [] and [f["comunicados"] for f in r["empresas"]] == [1, 1, 1, 1], f"todo bien: sin problemas ({r['problemas']})")
ok(next(f for f in r["empresas"] if f["empresa"] == "Delta")["dias"] == 147, "días desde el último comunicado (147, por debajo del límite de 150)")

# El caso del 24/11/2026: el listado no trae ningún comunicado de Logista ni de Colonial.
caso = [fila("ES0000000001", "2026-11-20"), fila("ES0000000004", "2026-11-18")]
r = v.revisar(caso, EMPRESAS, HOY)
ok(len(r["problemas"]) == 2 and "Logista" in r["problemas"][0] and "LOGISTA HOLDINGS" in r["problemas"][0] and "Colonial" in r["problemas"][1],
   f"caso real: avisa de Logista y Colonial con su alias: {r['problemas']}")

# Una empresa callada más de 150 días (cambio de nombre a mitad del listado).
callada = bien[:3] + [fila("ES0000000004", "2026-06-27")]
r = v.revisar(callada, EMPRESAS, HOY)
ok(len(r["problemas"]) == 1 and "Delta" in r["problemas"][0] and "151 días" in r["problemas"][0], f"empresa callada 151 días: {r['problemas']}")

# Listado vacío: un solo problema, no 35.
r = v.revisar([], EMPRESAS, HOY)
ok(r["problemas"] == ["el listado de la CNMV está vacío"], f"listado vacío: {r['problemas']}")

# Filas sin ISIN o sin fecha no cuentan.
r = v.revisar([fila("", "2026-11-20"), {"isin": "ES0000000001", "fecha": ""}] + bien[1:], EMPRESAS, HOY)
ok(len(r["problemas"]) == 1 and "Alfa" in r["problemas"][0], "filas sin ISIN o sin fecha no cuentan")

# Pasada completa por línea de órdenes, con la composición real del IBEX 35: sale con 1 si falta alguna, con 0 si no.
raiz = Path(tempfile.mkdtemp())
miembros = pd.read_csv(Path(__file__).resolve().parent.parent / "dividendos" / "ibex35.csv", dtype=str)["isin"].tolist()
listado = raiz / "ibex35.csv"
pd.DataFrame([{"canal": "OIR", "nreg": str(i), "fecha": "2026-11-20T09:00:00", "emisor": "X", "isin": isin} for i, isin in enumerate(miembros)]).to_csv(listado, index=False)
orden = [sys.executable, str(Path(__file__).resolve().parent / "vigilancia.py"), "--salida", str(raiz / "vigilancia"), "--cnmv", str(listado), "--fecha", "2026-11-25"]
p = subprocess.run(orden, capture_output=True, text=True)
j = json.loads((raiz / "vigilancia" / "datos" / "ultima.json").read_text(encoding="utf-8"))
ok(p.returncode == 0 and len(j["empresas"]) == 35 and j["problemas"] == [], f"pasada completa: 35 empresas, código 0 ({p.returncode}; {p.stdout.strip()[:120]})")
pd.DataFrame([{"canal": "OIR", "nreg": str(i), "fecha": "2026-11-20T09:00:00", "emisor": "X", "isin": isin} for i, isin in enumerate(miembros) if isin != "ES0105027009"]).to_csv(listado, index=False)
p = subprocess.run(orden, capture_output=True, text=True)
ok(p.returncode == 1 and "::error::vigilancia: Logista" in p.stdout, f"pasada completa sin Logista: código 1 y error con su nombre ({p.returncode})")

print(f"{total - fallos} de {total} comprobaciones superadas." if not fallos else f"{fallos} de {total} comprobaciones fallan.")
sys.exit(1 if fallos else 0)
