"""Comprobaciones sin red del colector de Bonos y Obligaciones (solo lo que no necesita el Tesoro).

  python bonos/pruebas_bonos.py

Las próximas subastas del JSON y de la huella se cuentan desde el día de la pasada, no desde el
principio del año (arreglo del 18/11/2026: el JSON publicaba las ocho primeras del calendario).

Memoria, protección y plazo por columna (23/11/2026): se simula la pasada del lunes con el CSV real que servía
datos.elespeculador.com el 21/11/2026 (pruebas_tesoro/subastas-servidor-2026-11-21.csv, 1.489 filas, sin las dos
subastas perdidas del 05/11), las tablas reales del Tesoro del 21/11 y el Excel reconstruido desde ese mismo CSV; y
después, la rotación de la tabla del Tesoro, la llegada del Excel mensual, una fila que el Excel deja de traer y las
filas repetidas de diciembre de 2025.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bonos  # noqa: E402

AQUI = Path(__file__).resolve().parent
REALES = AQUI / "pruebas_tesoro"
CSV_REAL = REALES / "subastas-servidor-2026-11-21.csv"

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


CAMPOS_EXCEL = ("fecha", "clase", "indexado", "verde", "variable", "sindicada", "mas_de", "plazo", "activo", "cupon", "solicitado",
                "segunda_vuelta", "adjudicado", "marginal", "medio")


def _excel_desde_csv(filas: list[dict]) -> tuple[list[dict], list[dict]]:
    """El Excel histórico y el mensual, reconstruidos desde el CSV real: lo que subastas_excel habría devuelto."""
    historico = [{**{k: f[k] for k in CAMPOS_EXCEL}, "fuente": "historico"} for f in filas if f["fuente"] == "historico"]
    mensual = [{**{k: f[k] for k in CAMPOS_EXCEL}, "fuente": "mensual"} for f in filas if f["fuente"].startswith("mensual")]
    return historico, mensual


def _busca(filas: list[dict], fecha: str, cupon: float, indexado: bool = False) -> list[dict]:
    return [f for f in filas if f["fecha"] == fecha and f.get("cupon") == cupon and f["indexado"] == indexado]


def _pasada(sal: Path, web, mensual, historico, **kw) -> tuple[list[dict], dict]:
    bonos.AVISOS.clear()
    filas, c = bonos.calcular(web, mensual, historico, sal / "datos" / bonos.CSV_SUBASTAS, **kw)
    bonos._escribir_csv(sal / "datos" / bonos.CSV_SUBASTAS, [x for x, _ in bonos.COLUMNAS], [bonos._fila_csv(f) for f in filas])
    return filas, c


def _resumen(c: dict) -> tuple:
    return (c["iguales"], len(c["actualizadas"]), len(c["recuperadas"]), len(c["duplicadas"]), len(c["conservadas"]), len(c["nuevas"]))


def resultados_boe(texto: str) -> dict:
    """Cifras de una resolución del BOE de resultados de subastas de Obligaciones (salida de pdftotext -layout), con la
    precisión de la tabla web del Tesoro: importes con dos decimales; precio medio de compra = precio de adjudicación de
    las peticiones no competitivas (con inflación, en las €i)."""
    def num(s: str) -> float:
        return float(s.replace(".", "").replace(",", "."))
    out = {}
    for p in re.split(r"\n\s+\d\.\s+Resultado de la subasta de ", texto)[1:]:
        d, mes, a = re.search(r"vencimiento\s+(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})", p).groups()
        nc = re.search(r"Peticiones no competitivas:\s+([\d.,]+)\s+([\d.,]+)(?:\s+([\d.,]+))?", p)
        sv = re.search(r"d\)\s+Segunda vuelta:\s*(?:.*\n)*?\s*(No se han presentado|– Importe nominal adjudicado: ([\d.,]+))", p)
        clave = (num(re.search(r"al (\d+,\d+) por 100", p).group(1)), "€i" in p.split("\n")[0])
        out[clave] = {"solicitado": round(num(re.search(r"Importe nominal solicitado: ([\d.,]+) millones", p).group(1)), 2),
                      "adjudicado": round(num(re.search(r"Importe nominal adjudicado: ([\d.,]+) millones", p).group(1)), 2),
                      "precio_medio_ex": num(re.search(r"Precio medio ponderado \(ex-cup[oó]n[^)]*\): ([\d.,]+) por 100", p).group(1)),
                      "precio_medio_compra": num(nc.group(3) or nc.group(2)),
                      "marginal": num(re.search(r"correspondiente al precio m[ií]nimo: ([\d.,]+) por 100", p).group(1)),
                      "medio": num(re.search(r"correspondiente al precio medio ponderado: ([\d.,]+) por 100", p).group(1)),
                      "segunda_vuelta": 0.0 if sv.group(1).startswith("No") else num(sv.group(2)),
                      "vencimiento": f"{a}-{bonos.MESES.index(mes) + 1:02d}-{int(d):02d}"}
    return out


def boe_frente_a_csv() -> None:
    """Las dos filas recuperadas, frente a la Resolución del BOE de los resultados del 05/11/2026; y, como control, las
    otras dos subastas de ese día, que el CSV real sí tenía (leídas de la web del Tesoro)."""
    boe = resultados_boe((REALES / "BOE-A-2026-24268.txt").read_text(encoding="utf-8"))
    ok(sorted(boe) == [(0.7, True), (3.1, False), (3.4, False), (3.5, False)], "BOE-A-2026-24268: las cuatro subastas del 05/11/2026")
    campos = ("solicitado", "adjudicado", "precio_medio_ex", "precio_medio_compra", "marginal", "medio", "segunda_vuelta", "vencimiento")
    reales = {(f["cupon"], f["indexado"]): f for f in bonos.leer_csv(CSV_REAL) if f["fecha"] == "2026-11-05"}
    ok(all({k: reales[c][k] for k in campos} == boe[c] for c in ((3.5, False), (0.7, True))),
       "control: la O 3,50% y la O€i 0,70% del CSV real (leídas de la web del Tesoro) coinciden cifra a cifra con el BOE")
    rec = {(f["cupon"], f["indexado"]): f for f in bonos.leer_csv(bonos.RECUPERACION)}
    ok(sorted(rec) == [(3.1, False), (3.4, False)] and all({k: rec[c][k] for k in campos} == boe[c] for c in rec)
       and all(f["fecha"] == "2026-11-05" for f in rec.values()),
       "filas_recuperadas.csv: las dos subastas perdidas coinciden cifra a cifra con el BOE")


def memoria_y_proteccion(web: list[dict], em: list[dict]) -> None:
    crudo = list(csv.reader(CSV_REAL.open(newline="", encoding="utf-8")))
    previas = bonos.leer_csv(CSV_REAL)
    ok(len(previas) == 1489 and crudo[0] == [c for c, _ in bonos.COLUMNAS[:bonos.COLUMNAS_ANTES]], "CSV real del 21/11: 1.489 filas con las 19 columnas de antes")
    ok(all(bonos._fila_csv(f) == r + ["", "", ""] for f, r in zip(previas, crudo[1:])), "leer y volver a escribir el CSV real no cambia ninguna de sus 1.489 filas")
    ok(not _busca(previas, "2026-11-05", 3.4) and not _busca(previas, "2026-11-05", 3.1), "en el CSV real faltan las dos subastas del 05/11 (O 3,40% y O 3,10%)")
    historico, mensual = _excel_desde_csv(previas)
    tmp = Path(tempfile.mkdtemp())
    try:
        sal = tmp / "bonos"
        (sal / "datos").mkdir(parents=True)
        shutil.copy(CSV_REAL, sal / "datos" / bonos.CSV_SUBASTAS)

        # 1. La pasada del lunes 23/11, con las tablas del Tesoro del 21/11.
        bonos.AVISOS.clear()
        filas, c = bonos.calcular(web, mensual, historico, sal / "datos" / bonos.CSV_SUBASTAS)
        ok(len(filas) == 1491 and _resumen(c) == (1476, 15, 2, 0, 0, 0) and not bonos.AVISOS,
           f"lunes: 1.491 filas = 1.489 + 2 recuperadas; 1.476 iguales, 15 actualizadas, ninguna conservada ni duplicada ({_resumen(c)})")
        o340, o310 = _busca(filas, "2026-11-05", 3.4), _busca(filas, "2026-11-05", 3.1)
        ok(len(o340) == 1 and bonos._fila_csv(o340[0])[:19] == ["2026-11-05", "O 3,40%", "O", "10", "0", "0", "0", "0", "0", "3.4", "3.802", "3.807", "4343.23", "2552.46", "0.0", "96.714", "96.804", "2036-10-31", "web"],
           "recuperada: O 3,40% del 05/11 (BOE-A-2026-24268, punto 3) con plazo 10")
        ok(len(o310) == 1 and bonos._fila_csv(o310[0]) == ["2026-11-05", "O 3,10% (VR 4a 9 m)", "O", "5", "0", "0", "0", "0", "0", "3.1", "3.338", "3.345", "3243.97", "1343.89", "0.0", "98.97", "99.84", "2031-07-30", "web", "O 3,10% (VR 4a 9 m)", "VR 4a 9 m", "5"],
           "recuperada: O 3,10% (VR 4a 9 m) del 05/11 (BOE-A-2026-24268, punto 1) con plazo 5, el de su columna")
        plazos = defaultdict(lambda: None, {(f["fecha"], f["activo"]): (f["plazo"], f["mas_de"], f.get("columna")) for f in filas})
        ok(plazos[("2026-11-19", "O 3,20% (VR 8a 11m)")] == (10, False, 10) and plazos[("2026-11-05", "O€i 0,70% (VR 7a 1m)")] == (5, False, 5),
           "criterio único: las reaperturas con VR del 19/11 y del 05/11 llevan el plazo de su columna (10 y 5)")
        ok(plazos[("2026-10-15", "O-7a")] == (5, False, 5) and plazos[("2026-10-01", "O-20a")] == (15, False, 15) and plazos[("2026-01-15", "O->30a")] == (50, False, 50),
           "columnas_tesoro.csv: O 3,55% (VR 7a) del 15/10 en la columna 5, O 2,90% (VR 20a 1m) del 01/10 en la 15 y O 1,45% del 15/01 en la 50 (ya no «más de 30»)")
        ok(plazos[("2026-10-01", "O-3a")] == (3, False, None) and plazos[("2026-09-17", "O-8a")] == (8, False, None),
           "sin columna conocida, el plazo sigue siendo el de la etiqueta del Excel")
        rep = {}
        for f in filas:
            rep[(f["fecha"], f["activo"])] = rep.get((f["fecha"], f["activo"]), 0) + 1
        ok(sorted(k for k, v in rep.items() if v > 1) == [("2008-12-18", "O-30a (s)"), ("2011-09-15", "O-9a"), ("2011-10-06", "B-3a"), ("2012-01-12", "B-5a"),
                                                          ("2012-05-03", "O-5a"), ("2013-10-03", "B-5a"), ("2018-10-04", "O-10a")],
           "las siete repeticiones legítimas de fecha y activo (cupones distintos) siguen todas")
        # Control frente a pandas: filas anteriores que no están tal cual en el CSV nuevo, en las 19 columnas de antes.
        cols = [x for x, _ in bonos.COLUMNAS[:bonos.COLUMNAS_ANTES]]
        antes = pd.DataFrame(crudo[1:], columns=cols)
        despues = pd.DataFrame([bonos._fila_csv(f)[:19] for f in filas], columns=cols)
        m = antes.merge(despues.drop_duplicates(), how="outer", on=cols, indicator=True)
        solo_antes = sorted(map(tuple, m[m["_merge"] == "left_only"][["fecha", "activo"]].values.tolist()))
        solo_despues = sorted(map(tuple, m[m["_merge"] == "right_only"][["fecha", "activo"]].values.tolist()))
        cambian = sorted((p["fecha"], p["activo"]) for p, n in c["actualizadas"] if bonos._fila_csv(p)[:19] != bonos._fila_csv(n)[:19])
        ok(solo_antes == cambian == [("2026-01-15", "O->30a"), ("2026-10-01", "O-20a"), ("2026-10-15", "O-7a"), ("2026-11-05", "O€i 0,70% (VR 7a 1m)"), ("2026-11-19", "O 3,20% (VR 8a 11m)")],
           "control con pandas: en las 19 columnas de antes, solo cambian las cinco filas con plazo nuevo, las mismas que lista la comparación")
        ok(len(solo_despues) == 7 and ("2026-11-05", "O 3,40%") in solo_despues and ("2026-11-05", "O 3,10% (VR 4a 9 m)") in solo_despues,
           "control con pandas: en el CSV nuevo, esas cinco filas y las dos recuperadas")
        ok(len(antes) == len(antes.drop_duplicates()) == 1489, "control con pandas: el CSV real no tiene filas completas repetidas")

        # La salida completa de esa pasada: CSV, JSON, fragmento y lo que lee el pulso del Tesoro de la prima de riesgo.
        datos = {"subastas": filas, "ultimas": web, "en_emision": em,
                 "proximas": [{"subasta": "2026-12-10", "indexados": True, "peticiones": "2026-12-09", "pago": "2026-12-14", "emision": "2026-12-15"}],
                 "tenedores": {"ultimo": {"anio": 2026, "mes": 9, "personas_fisicas": 1.0, "total": 2.0},
                               "anios": {2025: {"personas_fisicas": 1.0, "total": 2.0}}},  # simulados: no se prueban aquí
                 "control": bonos.control_json(c)}
        ok(bonos.escribir(datos, "2026-11-23", sal), "la primera pasada con el arreglo cambia la huella (textos y plazos nuevos)")
        ok(not list((sal / "datos").glob(".*.tmp")) and not list(sal.glob(".*.tmp")), "escritura atómica: no quedan temporales")
        escrito = list(csv.reader((sal / "datos" / bonos.CSV_SUBASTAS).open(newline="", encoding="utf-8")))
        ok(escrito[0] == [x for x, _ in bonos.COLUMNAS] and escrito[0][:19] == crudo[0] and len(escrito) == 1492,
           "CSV nuevo: las 19 columnas de antes en el mismo orden y las tres nuevas al final")
        ok((sal / "datos" / bonos.CSV_SUBASTAS).read_bytes().count(b"\r\n") == 1492, "CSV nuevo: mismos finales de línea que el anterior")
        j = json.loads((sal / "datos" / "ultima.json").read_text(encoding="utf-8"))
        ok(j["control_csv"]["conservadas"] == 0 and j["control_csv"]["recuperadas"] == 2 and j["control_csv"]["actualizadas"] == 15,
           "ultima.json lleva el control de la comparación")
        ok(all(u["plazo"] == u["columna"] for u in j["ultimas"]), "ultima.json: en «ultimas», el plazo es la columna del Tesoro")
        frag = (sal / "fragmento-wp.html").read_text(encoding="utf-8")
        serie = frag[frag.find("subasta a subasta"):frag.find("La media de cada año")]
        ok(serie.find("<tr><td>19/11/2026</td><td>Obligación 3,20 % (VR 8a 11m)</td><td>3,842 %") > 0
           and serie.find("<tr><td>05/11/2026</td><td>Obligación 3,40 %</td><td>3,802 %") > serie.find("19/11/2026"),
           "fragmento: la serie a 10 años empieza en la subasta del 19/11 (la misma que el primer párrafo) y recupera la del 05/11")
        ok("la del 19 de noviembre de 2026" in frag.split("<h2>")[0] and "etiqueta de 10 años" not in frag, "fragmento: primer párrafo y serie dicen la misma última subasta a 10 años")
        sys.path.insert(0, str(AQUI.parent / "prima"))
        try:
            import prima
            t = prima.leer_tesoro(tmp)
            ok(t.get("obligaciones_10a", {}).get("fecha") == "2026-11-19" and t["obligaciones_10a"]["denominacion"] == "O 3,20% (VR 8a 11m)",
               "prima de riesgo: el pulso del Tesoro toma la subasta a 10 años del 19/11 (con la versión anterior no encontraba ninguna)")
        except ImportError as e:
            ok(False, f"no se puede importar prima para comprobar el pulso del Tesoro: {e}")

        # 2. Segunda pasada con los mismos datos: nada cambia.
        bytes1 = (sal / "datos" / bonos.CSV_SUBASTAS).read_bytes()
        filas2, c2 = _pasada(sal, web, mensual, historico)
        ok(_resumen(c2) == (1491, 0, 0, 0, 0, 0) and (sal / "datos" / bonos.CSV_SUBASTAS).read_bytes() == bytes1,
           "segunda pasada igual: 1.491 filas iguales y el CSV idéntico byte a byte")
        ok(not bonos.escribir({**datos, "subastas": filas2, "control": bonos.control_json(c2)}, "2026-11-24", sal), "segunda pasada: la huella no cambia")

        # 3. La tabla del Tesoro rota (subasta del 10/12, simulada): las del 19/11 se quedan por la memoria, iguales.
        rotada = [w for w in web if w["fecha"] != "2026-11-19"] + [{**w, "fecha": "2026-12-10", "medio": w["medio"] + 0.05, "marginal": w["marginal"] + 0.05,
                                                                    "segunda_vuelta": None} for w in web if w["fecha"] == "2026-11-19"]
        filas3, c3 = _pasada(sal, rotada, mensual, historico)
        ok(len(filas3) == 1494 and _resumen(c3) == (1491, 0, 0, 0, 0, 3) and not bonos.AVISOS,
           f"rotación de la tabla: las tres subastas del 19/11 siguen iguales y entran las tres del 10/12 ({_resumen(c3)})")
        ok([f["plazo"] for f in _busca(filas3, "2026-11-19", 3.2)] == [10], "rotación: la O 3,20% (VR 8a 11m) del 19/11 conserva el plazo de su columna")

        # 4. Llega el Excel mensual con noviembre (etiquetas e importes redondeados simulados): casa con lo guardado de la web.
        etiquetas = {("2026-11-05", 3.4): "O-10a", ("2026-11-05", 3.1): "O-5a", ("2026-11-05", 3.5): "O-15a", ("2026-11-05", 0.7): "O€i-7a",
                     ("2026-11-19", 2.6): "B-5a", ("2026-11-19", 3.75): "O-8a", ("2026-11-19", 3.2): "O-9a"}
        nov = []
        for f in filas3:
            k = (f["fecha"], f["cupon"])
            if k in etiquetas:
                a = etiquetas[k]
                nov.append({**{x: f[x] for x in CAMPOS_EXCEL}, "activo": a, "plazo": int(a.split("-")[1][:-1]), "fuente": "mensual",
                            "adjudicado": round(f["adjudicado"]), "solicitado": round(f["solicitado"]), "segunda_vuelta": 0.0})
        filas4, c4 = _pasada(sal, rotada, mensual + nov, historico)
        ok(len(filas4) == 1494 and _resumen(c4) == (1487, 7, 0, 0, 0, 0) and not bonos.AVISOS,
           f"llega el Excel: las siete subastas de noviembre se actualizan, ninguna se duplica ni se pierde ({_resumen(c4)})")
        o340 = _busca(filas4, "2026-11-05", 3.4)
        ok(len(o340) == 1 and tuple(o340[0].get(k) for k in ("activo", "plazo", "fuente", "adjudicado", "precio_medio_compra", "denominacion"))
           == ("O-10a", 10, "mensual+web", 2552.46, 96.804, "O 3,40%"),
           "con el Excel, la O 3,40% del 05/11 toma su etiqueta y conserva las cifras exactas, el precio y el nombre de la web")
        o320 = _busca(filas4, "2026-11-19", 3.2)
        ok(len(o320) == 1 and tuple(o320[0].get(k) for k in ("activo", "plazo", "columna", "vida_residual")) == ("O-9a", 10, 10, "VR 8a 11m"),
           "con el Excel, la reapertura del 19/11 sigue con el plazo de su columna (10), no el de la etiqueta (9)")

        # 5. El Excel deja de traer una fila: se conserva tal cual y el flujo avisa.
        quitada = next(f for f in historico if f["fecha"] == "2008-12-18" and f["activo"] == "O-30a (s)")
        antes5 = [bonos._fila_csv(f) for f in filas4 if f["fecha"] == "2008-12-18"]
        filas5, c5 = _pasada(sal, rotada, mensual + nov, [f for f in historico if f is not quitada])
        ok(len(filas5) == 1494 and len(c5["conservadas"]) == 1 and any("se conserva tal cual" in a for a in bonos.AVISOS)
           and [bonos._fila_csv(f) for f in filas5 if f["fecha"] == "2008-12-18"] == antes5,
           "una subasta que el Excel deja de traer se conserva igual, con aviso")

        # 6. Las filas repetidas del 04/12/2025 (etiquetas «-5y», «-10y», «-13y» del Excel mensual): cuando el mensual deje
        #    2025 (enero), el histórico trae cada subasta una vez y las repetidas se quitan sin perder ninguna subasta.
        mensual6 = [f for f in mensual + nov if not f["fecha"].startswith("2025")]
        historico6 = historico + [{**f, "fuente": "historico"} for f in mensual if f["fecha"].startswith("2025") and not f["activo"].endswith("y")]
        filas6, c6 = _pasada(sal, rotada, mensual6, historico6)
        ok(len(filas6) == 1491 and len(c6["duplicadas"]) == 3 and not c6["conservadas"]
           and sorted(p["activo"] for p, _ in c6["duplicadas"]) == ["B-5y", "O-13y", "O€i-10y"],
           "las tres filas repetidas de diciembre de 2025 se quitan como duplicadas; no se conserva ni se pierde ninguna subasta")
        ok(all(_busca(filas6, "2025-12-04", cup, ix) for cup, ix in ((2.7, False), (1.15, True), (0.85, False))), "las tres subastas del 04/12/2025 siguen, una vez cada una")

        # 7. Recuperar desde una copia antigua (formato de 19 columnas, como la del 17/11 del servidor), sin el archivo del
        #    repositorio: entran las dos subastas, y la columna de la reapertura sale de columnas_tesoro.csv.
        copia = tmp / "copia-17-11.csv"
        with copia.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerows(crudo)
            w.writerow(["2026-11-05", "O 3,10% (VR 4a 9 m)", "O", "4", "0", "0", "0", "0", "0", "3.1", "3.338", "3.345", "3243.97", "1343.89", "0.0", "98.97", "99.84", "2031-07-30", "web"])
            w.writerow(["2026-11-05", "O 3,40%", "O", "10", "0", "0", "0", "0", "0", "3.4", "3.802", "3.807", "4343.23", "2552.46", "0.0", "96.714", "96.804", "2036-10-31", "web"])
        sal7 = tmp / "otra" / "bonos"
        (sal7 / "datos").mkdir(parents=True)
        shutil.copy(CSV_REAL, sal7 / "datos" / bonos.CSV_SUBASTAS)
        filas7, c7 = _pasada(sal7, web, mensual, historico, recuperar=[copia], recuperacion=tmp / "no-existe.csv")
        ok(len(c7["recuperadas"]) == 2 and not c7["conservadas"] and [bonos._fila_csv(f) for f in filas7] == [bonos._fila_csv(f) for f in filas],
           "con --recuperar y la copia antigua, el CSV queda idéntico al de la recuperación del repositorio")
        _, c7b = _pasada(sal7, web, mensual, historico, recuperar=[copia])
        ok(not c7b["recuperadas"] and any("O 3,10% (VR 4a 9 m): plazo_anios: '4' -> '5'" in x for x in c7b["notas_recuperacion"]),
           "una segunda vez no añade nada y detalla en qué difiere la copia (el plazo antiguo de la reapertura)")
        lineas = bonos.comparar_archivos(sal / "datos" / bonos.CSV_SUBASTAS, copia)
        ok(" 0 que faltan" in lineas[0] and not any(x.startswith("  FALTA") for x in lineas), "--comparar con la copia: no falta ninguna fila de la copia")

        # 8. Errores de lectura: un CSV ajeno o una fila rota paran la pasada (no se escribe con memoria incompleta).
        roto = tmp / "roto.csv"
        roto.write_text("fecha,activo\n2026-01-01,X\n", encoding="utf-8")
        try:
            bonos.leer_csv(roto)
            ok(False, "un CSV sin las columnas del colector para la pasada")
        except bonos.DatosRaros:
            ok(True, "un CSV sin las columnas del colector para la pasada")
        roto.write_text(",".join(crudo[0]) + "\n" + ",".join(crudo[5][:4] + ["x"] + crudo[5][5:]) + "\n", encoding="utf-8")
        try:
            bonos.leer_csv(roto)
            ok(False, "una fila con un valor roto para la pasada y dice la línea")
        except bonos.DatosRaros as e:
            ok("línea 2" in str(e), "una fila con un valor roto para la pasada y dice la línea")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bonos.AVISOS.clear()


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
    ok(r[0]["adjudicado"] == 1589.84 and r[0]["marginal"] == 3.85 and r[2]["medio"] == 4.286, "el resto de la tabla se lee igual que antes")
    ok(r[2]["plazo"] == 10 and r[2]["columna"] == 10 and r[2]["vida_residual"] == "VR 9 a 11 m", "reapertura con VR: el plazo es la columna (10) y la vida residual queda en el nombre")
    # Páginas reales del Tesoro del 21/11/2026 (pruebas_tesoro/): el colector de main fallaba con «número con formato
    # inesperado: '[1]'» en obligaciones y bonos; con el arreglo, las tres tablas de resultados y la de valores en emisión se leen.
    reales = Path(__file__).resolve().parent / "pruebas_tesoro"
    lect = {g: bonos.leer_resultados(g, (reales / f"{g}-2026-11-21.html").read_text(encoding="utf-8")) for g in ("obligaciones", "bonos", "indexados")}
    ob, bo, ix = lect["obligaciones"], lect["bonos"], lect["indexados"]
    ok([x["columna"] for x in ob] == [10, 15, 30, 50] and [x["segunda_vuelta"] for x in ob] == [None, 0.0, 322.68, 232.97], "real 21/11, obligaciones: cuatro plazos y la 2.ª vuelta del 19/11 pendiente (None)")
    ok(ob[0]["denominacion"] == "O 3,20% (VR 8a 11m)" and ob[0]["plazo"] == 10 and ob[0]["fecha"] == "2026-11-19" and ob[0]["marginal"] == 3.85 and ob[0]["cobertura"] == 1.84, "real 21/11, obligaciones: la subasta del 19/11 completa, con plazo 10 (su columna) y no 8 (su vida residual)")
    ok([x["segunda_vuelta"] for x in bo] == [0.0, None, None] and bo[2]["denominacion"] == "O 3,75% (7A)" and bo[1]["medio"] == 3.475, "real 21/11, bonos: dos 2.ª vueltas pendientes y una obligación en la página de bonos")
    ok([x["plazo"] for x in bo] == [3, 5, 5], "real 21/11, bonos: «O 3,75% (7A)» con plazo 5, el de su columna")
    ok([x["plazo"] for x in ix] == [5, 10, 15] and ix[0]["indexado"] and ix[2]["segunda_vuelta"] == 133.24, "real 21/11, indexados: «O€i 0,70% (VR 7a 1m)» con plazo 5 (su columna), €i y 2.ª vuelta ya anunciada")
    ok(all(x["plazo"] == x["columna"] for x in ob + bo + ix), "real 21/11: en las tres tablas, plazo = columna del Tesoro")
    em = bonos.leer_en_emision((reales / "en-emision-2026-11-21.html").read_text(encoding="utf-8"))
    ok(len(em) == 10 and em[0] == {"valor": "Bono a 3 años", "cupon": 2.35, "vencimiento": "2029-03-31"} and em[-1]["vencimiento"] == "2071-10-31", "real 21/11, valores en emisión: diez valores, cupón y vencimiento")
    boe_frente_a_csv()
    memoria_y_proteccion(ob + bo + ix, em)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
