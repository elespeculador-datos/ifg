"""Comprobaciones sin red del colector de Letras (solo lo que no necesita el Tesoro).

  python letras/pruebas_letras.py

Las próximas subastas del JSON y de la huella se cuentan desde el día de la pasada, no desde el
principio del año (arreglo del 18/11/2026: el JSON publicaba las ocho primeras del calendario).

Memoria y protección (23/11/2026, como en bonos/): con el CSV real que servía datos.elespeculador.com el 21/11/2026
(pruebas_tesoro/subastas-letras-servidor-2026-11-21.csv, 1.107 filas), sus cuatro filas de la web como tabla del Tesoro
y el Excel reconstruido desde ese CSV: pasada igual, rotación de la tabla el 01/12 (la versión anterior perdía las
subastas del 03/11), llegada del Excel mensual, una fila que el Excel deja de traer y recuperación desde otro CSV.
"""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import letras  # noqa: E402

CSV_REAL = Path(__file__).resolve().parent / "pruebas_tesoro" / "subastas-letras-servidor-2026-11-21.csv"

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


CAMPOS_EXCEL = ("fecha", "plazo", "solicitado", "segunda_vuelta", "adjudicado", "marginal", "medio")


def _pasada(sal: Path, web, mensual, historico, **kw) -> tuple[list[dict], dict]:
    letras.AVISOS.clear()
    filas, c = letras.calcular(web, mensual, historico, sal / "datos" / letras.CSV_SUBASTAS, **kw)
    letras._escribir_csv(sal / "datos" / letras.CSV_SUBASTAS, [x for x, _ in letras.COLUMNAS], [letras._fila_csv(f) for f in filas])
    return filas, c


def _resumen(c: dict) -> tuple:
    return (c["iguales"], len(c["actualizadas"]), len(c["recuperadas"]), len(c["conservadas"]), len(c["nuevas"]))


def memoria_y_proteccion() -> None:
    crudo = list(csv.reader(CSV_REAL.open(newline="", encoding="utf-8")))
    previas = letras.leer_csv(CSV_REAL)
    ok(len(previas) == 1107 and crudo[0] == [c for c, _ in letras.COLUMNAS], "CSV real del 21/11: 1.107 filas con las columnas de siempre")
    ok(all(letras._fila_csv(f) == r for f, r in zip(previas, crudo[1:])), "leer y volver a escribir el CSV real no cambia ninguna fila")
    web = [{k: v for k, v in f.items()} for f in previas if f["fuente"] == "web"]
    ok(sorted((w["fecha"], w["plazo"]) for w in web) == [("2026-11-03", 6), ("2026-11-03", 12), ("2026-11-10", 3), ("2026-11-10", 9)],
       "la tabla del Tesoro del 21/11: subastas del 03/11 (6 y 12 meses) y del 10/11 (3 y 9)")
    historico = [{**{k: f[k] for k in CAMPOS_EXCEL}, "fuente": "historico"} for f in previas if f["fuente"] == "historico"]
    mensual = [{**{k: f[k] for k in CAMPOS_EXCEL}, "fuente": "mensual"} for f in previas if f["fuente"] == "mensual"]
    tmp = Path(tempfile.mkdtemp())
    try:
        sal = tmp / "letras"
        (sal / "datos").mkdir(parents=True)
        shutil.copy(CSV_REAL, sal / "datos" / letras.CSV_SUBASTAS)
        # 1. Pasada con la misma tabla y el mismo Excel: el CSV no cambia ni un byte.
        filas1, c1 = _pasada(sal, web, mensual, historico)
        ok(_resumen(c1) == (1107, 0, 0, 0, 0) and not letras.AVISOS and (sal / "datos" / letras.CSV_SUBASTAS).read_bytes() == CSV_REAL.read_bytes(),
           f"misma tabla y mismo Excel: 1.107 filas iguales y el CSV idéntico byte a byte ({_resumen(c1)})")
        # 2. El 01/12 la tabla rota en 6 y 12 meses (subasta simulada) y el Excel mensual aún no trae noviembre.
        rotada = [w for w in web if w["fecha"] != "2026-11-03"] + [{**w, "fecha": "2026-12-01", "medio": w["medio"] + 0.02, "marginal": w["marginal"] + 0.02}
                                                                  for w in web if w["fecha"] == "2026-11-03"]
        sin_memoria = {(f["fecha"], f["plazo"]) for f in letras.unir(rotada, mensual, historico)}
        ok(("2026-11-03", 6) not in sin_memoria and ("2026-11-03", 12) not in sin_memoria,
           "control: sin memoria (versión anterior), la rotación del 01/12 perdería las dos subastas del 03/11")
        filas2, c2 = _pasada(sal, rotada, mensual, historico)
        ok(len(filas2) == 1109 and _resumen(c2) == (1107, 0, 0, 0, 2) and not letras.AVISOS,
           f"rotación con memoria: las 1.107 filas siguen iguales y entran las dos del 01/12 ({_resumen(c2)})")
        cols = [x for x, _ in letras.COLUMNAS]
        antes = pd.DataFrame(crudo[1:], columns=cols)
        despues = pd.DataFrame([letras._fila_csv(f) for f in filas2], columns=cols)
        m = antes.merge(despues, how="outer", on=cols, indicator=True)
        ok((m["_merge"] == "left_only").sum() == 0 and sorted(m[m["_merge"] == "right_only"]["fecha"]) == ["2026-12-01", "2026-12-01"],
           "control con pandas (unión externa por fila completa): no falta ninguna fila anterior; sobran solo las dos del 01/12")
        # 3. Llega el Excel mensual con noviembre (importes redondeados, sin precios): las filas de la web no se duplican ni pierden nada.
        nov = [{**{k: f[k] for k in CAMPOS_EXCEL}, "fuente": "mensual", "adjudicado": round(f["adjudicado"]), "solicitado": round(f["solicitado"])}
               for f in previas if f["fuente"] == "web"]
        filas3, c3 = _pasada(sal, rotada, mensual + nov, historico)
        o = [f for f in filas3 if f["fecha"] == "2026-11-03" and f["plazo"] == 12]
        ok(len(filas3) == 1109 and _resumen(c3) == (1109, 0, 0, 0, 0) and len(o) == 1 and o[0]["precio_medio"] is not None and o[0]["fuente"] == "web",
           f"llega el Excel: ninguna fila nueva, cambiada ni perdida; la del 03/11 a 12 meses conserva precio y cifras de la web ({_resumen(c3)})")
        # 4. El Excel deja de traer una fila: se conserva tal cual y el flujo avisa.
        quitada = historico[100]
        fila_antes = [letras._fila_csv(f) for f in filas3 if (f["fecha"], f["plazo"]) == (quitada["fecha"], quitada["plazo"])]
        filas4, c4 = _pasada(sal, rotada, mensual + nov, [f for f in historico if f is not quitada])
        ok(len(filas4) == 1109 and len(c4["conservadas"]) == 1 and any("se conserva tal cual" in a for a in letras.AVISOS)
           and [letras._fila_csv(f) for f in filas4 if (f["fecha"], f["plazo"]) == (quitada["fecha"], quitada["plazo"])] == fila_antes,
           "una subasta que el Excel deja de traer se conserva igual, con aviso")
        # 5. --recuperar: una subasta que faltaba en el CSV anterior vuelve desde otro CSV; --comparar lo confirma.
        sal5 = tmp / "otra" / "letras"
        (sal5 / "datos").mkdir(parents=True)
        with (sal5 / "datos" / letras.CSV_SUBASTAS).open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([r for r in crudo if r[:2] != ["2026-10-13", "3"]])
        filas5, c5 = _pasada(sal5, web, [f for f in mensual if (f["fecha"], f["plazo"]) != ("2026-10-13", 3)], historico, recuperar=[CSV_REAL])
        ok(len(c5["recuperadas"]) == 1 and len(filas5) == 1107 and [letras._fila_csv(f) for f in filas5] == [letras._fila_csv(f) for f in previas],
           "--recuperar: la subasta que faltaba vuelve y el CSV queda idéntico al real")
        lineas = letras.comparar_archivos(sal5 / "datos" / letras.CSV_SUBASTAS, CSV_REAL)
        ok(" 0 que faltan" in lineas[0] and " 0 con cambios" in lineas[0], "--comparar: nada falta ni cambia frente al CSV real")
        roto = tmp / "roto.csv"
        roto.write_text("fecha,plazo\n2026-01-01,3\n", encoding="utf-8")
        try:
            letras.leer_csv(roto)
            ok(False, "un CSV ajeno para la pasada")
        except letras.DatosRaros:
            ok(True, "un CSV ajeno para la pasada")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        letras.AVISOS.clear()


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
    memoria_y_proteccion()

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
