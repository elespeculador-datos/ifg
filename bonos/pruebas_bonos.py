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
    # Llamadas a nota «[1]» en las celdas del Tesoro (19/11/2026: 2.ª vuelta pendiente de anunciar).
    ok(bonos._dec("2,345[1]") == 2.345 and bonos._dec("[1] 1.886,84") == 1886.84, "_dec quita la llamada a nota y lee la cifra")
    ok(bonos._dec("[1]") is None and bonos._dec("-") is None, "_dec: la nota sola vale None, como el guion")
    try:
        bonos._dec("abc[1]")
        ok(False, "_dec sigue parando con un texto que no es número")
    except bonos.DatosRaros:
        ok(True, "_dec sigue parando con un texto que no es número")
    ok(bonos._cupon("3,45[1] v") == (3.45, True), "_cupon quita la llamada a nota")
    r = bonos.leer_resultados("bonos", (Path(__file__).resolve().parent / "prueba_ultimas_nota.html").read_text(encoding="utf-8"))
    ok([x["segunda_vuelta"] for x in r] == [None, 0.0, 309.13], "tabla del Tesoro con «[1]» en la 2.ª vuelta: pendiente -> None, las demás cifras intactas")
    ok(r[0]["adjudicado"] == 1589.84 and r[0]["marginal"] == 3.85 and r[2]["plazo"] == 9 and r[2]["medio"] == 4.286, "el resto de la tabla se lee igual que antes")
    # Páginas reales del Tesoro del 21/11/2026 (pruebas_tesoro/): el colector de main fallaba con «número con formato
    # inesperado: '[1]'» en obligaciones y bonos; con el arreglo, las tres tablas de resultados y la de valores en emisión se leen.
    reales = Path(__file__).resolve().parent / "pruebas_tesoro"
    lect = {g: bonos.leer_resultados(g, (reales / f"{g}-2026-11-21.html").read_text(encoding="utf-8")) for g in ("obligaciones", "bonos", "indexados")}
    ob, bo, ix = lect["obligaciones"], lect["bonos"], lect["indexados"]
    ok([x["columna"] for x in ob] == [10, 15, 30, 50] and [x["segunda_vuelta"] for x in ob] == [None, 0.0, 322.68, 232.97], "real 21/11, obligaciones: cuatro plazos y la 2.ª vuelta del 19/11 pendiente (None)")
    ok(ob[0]["denominacion"] == "O 3,20% (VR 8a 11m)" and ob[0]["plazo"] == 8 and ob[0]["fecha"] == "2026-11-19" and ob[0]["marginal"] == 3.85 and ob[0]["cobertura"] == 1.84, "real 21/11, obligaciones: la subasta del 19/11 completa")
    ok([x["segunda_vuelta"] for x in bo] == [0.0, None, None] and bo[2]["denominacion"] == "O 3,75% (7A)" and bo[1]["medio"] == 3.475, "real 21/11, bonos: dos 2.ª vueltas pendientes y una obligación en la página de bonos")
    ok([x["plazo"] for x in ix] == [7, 10, 15] and ix[0]["indexado"] and ix[2]["segunda_vuelta"] == 133.24, "real 21/11, indexados: €i, vida residual y 2.ª vuelta ya anunciada")
    em = bonos.leer_en_emision((reales / "en-emision-2026-11-21.html").read_text(encoding="utf-8"))
    ok(len(em) == 10 and em[0] == {"valor": "Bono a 3 años", "cupon": 2.35, "vencimiento": "2029-03-31"} and em[-1]["vencimiento"] == "2071-10-31", "real 21/11, valores en emisión: diez valores, cupón y vencimiento")
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
