"""Comprobaciones sin red del colector de Bonos y Obligaciones (solo lo que no necesita el Tesoro).

  python letras/pruebas_bonos.py

Las próximas subastas del JSON y de la huella se cuentan desde el día de la pasada, no desde el
principio del año (arreglo del 18/11/2026: el JSON publicaba las ocho primeras del calendario).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bonos  # noqa: E402

FALLOS: list[str] = []
N = 0


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def datos_simulados() -> dict:
    prox = [{"subasta": f"2026-{m:02d}-{d:02d}", "plazos": [6, 12] if d < 15 else [3, 9], "peticiones": f"2026-{m:02d}-{d - 4:02d}",
             "pago": f"2026-{m:02d}-{d + 2:02d}", "emision": f"2026-{m:02d}-{d + 3:02d}", "anio_calendario": 2026}
            for m in range(1, 13) for d in (10, 20)]
    for c in prox:
        c["indexados"] = c.pop("plazos") == [6, 12]
    sub = [{"fecha": f"2026-{m:02d}-10", "activo": "B 2,35%", "marginal": 3.0 + m / 100, "medio": 2.99 + m / 100} for m in range(1, 11)]
    return {"subastas": sub, "proximas": prox, "ultimas": [{"fecha": "2026-10-15", "denominacion": "B 2,35%", "medio": 3.1}],
            "en_emision": [{"valor": "B 2,35%", "cupon": 2.35, "vencimiento": "2029-03-31"}],
            "tenedores": {"ultimo": {"anio": 2026, "mes": 8, "personas_fisicas": 1.0, "total": 2.0}}}


if __name__ == "__main__":
    d = datos_simulados()
    ok([c["subasta"] for c in bonos.proximas_desde(d, "2026-11-18")[:3]] == ["2026-11-20", "2026-12-10", "2026-12-20"], "próximas desde el día de la pasada")
    ok(len(bonos.proximas_desde(d, "")) == 24, "sin fecha, todas")
    ok(bonos.proximas_desde(d, "2026-11-20")[0]["subasta"] == "2026-11-20", "la subasta de hoy sigue siendo próxima")
    ok(bonos.proximas_desde(d, "2027-01-01") == [], "pasado el calendario, ninguna")
    h1 = bonos.huella(d, "2026-11-18")
    ok(h1 == bonos.huella(d, "2026-11-19"), "la huella no cambia entre dos días sin subasta")
    ok(h1 != bonos.huella(d, "2026-11-21"), "la huella cambia cuando pasa una subasta del calendario")
    ok(h1 != bonos.huella(d, ""), "la huella con fecha no es la antigua (todas desde enero)")
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
