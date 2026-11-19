"""Comprobaciones sin red del colector de Letras (solo lo que no necesita el Tesoro).

  python letras/pruebas_letras.py

Las próximas subastas del JSON y de la huella se cuentan desde el día de la pasada, no desde el
principio del año (arreglo del 18/11/2026: el JSON publicaba las ocho primeras del calendario).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import letras  # noqa: E402

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
    sub = [{"fecha": f"2026-{m:02d}-10", "plazo": 12, "marginal": 2.0 + m / 100, "medio": 1.99 + m / 100} for m in range(1, 11)]
    return {"subastas": sub, "proximas": prox, "tenedores": {"ultimo": {"anio": 2026, "mes": 8, "personas_fisicas": 1.0, "total": 2.0}}}


if __name__ == "__main__":
    d = datos_simulados()
    ok([c["subasta"] for c in letras.proximas_desde(d, "2026-11-18")[:3]] == ["2026-11-20", "2026-12-10", "2026-12-20"], "próximas desde el día de la pasada")
    ok(len(letras.proximas_desde(d, "")) == 24, "sin fecha, todas")
    ok(letras.proximas_desde(d, "2026-11-20")[0]["subasta"] == "2026-11-20", "la subasta de hoy sigue siendo próxima")
    ok(letras.proximas_desde(d, "2027-01-01") == [], "pasado el calendario, ninguna")
    h1 = letras.huella(d, "2026-11-18")
    ok(h1 == letras.huella(d, "2026-11-19"), "la huella no cambia entre dos días sin subasta")
    ok(h1 != letras.huella(d, "2026-11-21"), "la huella cambia cuando pasa una subasta del calendario")
    ok(h1 != letras.huella(d, ""), "la huella con fecha no es la antigua (todas desde enero)")
    # Llamadas a nota «[1]» en las celdas del Tesoro (19/11/2026: 2.ª vuelta pendiente de anunciar).
    ok(letras._dec("2,345[1]") == 2.345 and letras._dec("[1] 1.886,84") == 1886.84, "_dec quita la llamada a nota y lee la cifra")
    ok(letras._dec("[1]") is None and letras._dec("-") is None, "_dec: la nota sola vale None, como el guion")
    try:
        letras._dec("abc[1]")
        ok(False, "_dec sigue parando con un texto que no es número")
    except letras.DatosRaros:
        ok(True, "_dec sigue parando con un texto que no es número")
    r = letras.leer_ultimas((Path(__file__).resolve().parent / "prueba_ultimas_nota.html").read_text(encoding="utf-8"))
    ok([x["segunda_vuelta"] for x in r] == [None, None, 10.0, 25.0], "tabla del Tesoro con «[1]» en la 2.ª vuelta: pendiente -> None, las demás cifras intactas")
    ok([x["plazo"] for x in r] == [3, 6, 9, 12] and r[3]["adjudicado"] == 1800.0 and r[0]["medio"] == 2.04, "el resto de la tabla se lee igual que antes")

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
