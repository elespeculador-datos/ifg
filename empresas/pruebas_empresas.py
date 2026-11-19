"""Comprobaciones sin red de la ficha integrada (empresas/empresas.py) con salidas simuladas de los cinco colectores,
en el formato real de cada uno (cabeceras de CSV y claves de JSON copiadas de las salidas publicadas)."""

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import empresas  # noqa: E402

FALLOS = []
TOTAL = 0


def ok(cond, texto):
    global TOTAL
    TOTAL += 1
    if not cond:
        FALLOS.append(texto)
        print("FALLA:", texto)


HOY = date(2026, 11, 19)
REP, SAN, IBE = "ES0173516115", "ES0113900J37", "ES0144580Y14"


def escribe(raiz: Path, rel: str, texto: str):
    r = raiz / rel
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text(texto, encoding="utf-8")


def fuentes(raiz: Path, cortos=True, directivos=True, accionistas=True, dividendos=True, cnmv=True, filtro_juridicas=True):
    if cortos:
        escribe(raiz, "cortos/datos/vigentes.csv",
                "lei,isin,emisor,tenedor,fecha_posicion,posicion_pct,estado\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora A LLP,2026-11-10,0.62,\"igual o superior al 0,5 %\"\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora B LLC,2026-11-17,0.5,\"igual o superior al 0,5 %\"\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora C SA,2026-11-03,0.42,\"bajó del 0,5 %\"\n"
                f"L2,{IBE},IBERDROLA S.A.,Gestora D,2026-11-12,0.55,\"igual o superior al 0,5 %\"\n")
        escribe(raiz, "cortos/datos/historial_cambios.csv",
                "fecha_publicacion,isin,emisor,tenedor,tipo,antes_pct,ahora_pct,fecha_posicion\n"
                f"2026-11-18,{REP},\"REPSOL, S.A.\",Gestora B LLC,nueva,,0.5,2026-11-17\n"
                f"2026-11-11,{REP},\"REPSOL, S.A.\",Gestora A LLP,sube,0.55,0.62,2026-11-10\n"
                f"2026-11-04,{REP},\"REPSOL, S.A.\",Gestora C SA,deja de publicarse,0.5,,\n"
                f"2026-10-01,{REP},\"REPSOL, S.A.\",Gestora X,baja,0.7,0.6,2026-09-30\n")
        escribe(raiz, "cortos/datos/ultima.json", json.dumps({"fecha_publicacion": "2026-11-18", "posiciones": 4}))
    if directivos:
        cab = ("registro,linea,fecha_registro,fecha_operacion,emisor,nif,lei,isin,motivo,cargo_tipo,instrumento,operacion,sentido,tipo,lugar,"
               "volumen,precio,divisa,importe_eur,modificacion,sustituida,documento\n")
        filas = [
            f"r1,1,2026-11-12,2026-11-10,REPSOL,A1,L1,{REP},m,consejero,acciones,Compra,compra,discrecional,XMAD,1000,30.1,EUR,30100,0,0,https://cnmv/doc1",
            f"r2,1,2026-11-05,2026-11-03,REPSOL,A1,L1,{REP},m,directivo,acciones,Venta,venta,discrecional,XMAD,500,29,EUR,14500,0,0,https://cnmv/doc2",
            f"r3,1,2026-10-01,2026-09-29,REPSOL,A1,L1,{REP},m,consejero,acciones,Compra,compra,discrecional,XMAD,100,28,EUR,2800,0,0,https://cnmv/doc3",
            f"r4,1,2026-07-15,2026-07-14,REPSOL,A1,L1,{REP},m,consejero,acciones,Compra,compra,discrecional,XMAD,100,28,EUR,2800,0,0,https://cnmv/doc4",
            f"r5,1,2026-11-14,2026-11-13,REPSOL,A1,L1,{REP},m,directivo,acciones,Compra,compra,plan,XOFF,100,28,EUR,2800,0,0,https://cnmv/doc5",
            f"r6,1,2026-11-14,2026-11-13,REPSOL,A1,L1,{REP},m,directivo,acciones,Compra,compra,discrecional,XMAD,999,28,EUR,27972,0,1,https://cnmv/doc6",
            f"r7,1,2026-11-15,2026-11-13,IBERDROLA,A2,L2,{IBE},m,vinculada,acciones,Venta,venta,discrecional,XMAD,10,15,EUR,150,0,0,https://cnmv/doc7",
        ]
        escribe(raiz, "directivos/datos/operaciones.csv", cab + "\n".join(filas) + "\n")
        escribe(raiz, "directivos/datos/ultima.json", json.dumps({"fecha": "2026-11-18"}))
    if accionistas:
        emp_rep = {"empresa": "Repsol", "isin": REP, "consulta": "2026-11-18", "derechos_voto": 1200000000, "fecha_derechos_voto": "2026-10-01",
                   "accionistas": [{"accionista": "BLACKROCK INC", "acciones": 5.1, "directo": 0, "indirecto": 5.1, "instrumentos": 0.2, "total": 5.3, "fecha": "2026-09-01", "info": ""},
                                   {"accionista": "SACYR, S.A.", "acciones": 3.0, "directo": 3.0, "indirecto": 0, "instrumentos": 0, "total": 3.0, "fecha": "2026-05-02", "info": ""},
                                   {"accionista": "ANTIGUA SA", "acciones": 0, "directo": 0, "indirecto": 0, "instrumentos": 0, "total": 0, "fecha": "2025-01-01", "info": ""}]}
        if filtro_juridicas:
            emp_rep["fisicas_excluidas"] = 1
        emp_ibe = {"empresa": "Iberdrola", "isin": IBE, "consulta": "2026-11-18", "accionistas": [{"accionista": "QATAR INVESTMENT AUTHORITY", "acciones": 8.7, "total": 8.7, "fecha": "2026-02-02"}]}
        escribe(raiz, "accionistas/datos/ultima.json", json.dumps({"fecha": "2026-11-18", "empresas": [emp_rep, emp_ibe, {"empresa": "Fuera", "isin": "XX", "fuera": True}]}))
    if dividendos:
        escribe(raiz, "dividendos/datos/proximos.csv",
                "fecha_ex,fecha_pago,empresa,company,isin,bruto,moneda,concepto,extraordinario,flexible,ejercicio\n"
                f"2026-12-15,2026-12-17,Repsol,REPSOL,{REP},0.5,EUR,A cuenta,False,False,2026\n"
                f"2027-01-07,2027-01-09,Repsol,REPSOL,{REP},0.5,EUR,Complementario,False,False,2026\n"
                f"2026-11-10,2026-11-12,Repsol,REPSOL,{REP},0.45,EUR,Pasado,False,False,2026\n"
                f"2026-12-01,,Iberdrola,IBERDROLA,{IBE},0.25,EUR,Flexible,False,True,2026\n")
        escribe(raiz, "dividendos/datos/ultimos_12m.csv",
                "isin,empresa,pagos,bruto_total,ultima_fecha_ex\n" f"{REP},Repsol,2,0.95,2026-07-07\n")
        escribe(raiz, "dividendos/datos/ultima.json", json.dumps({"generado": "2026-11-18T17:10:00+00:00", "proximos": 4}))
    if cnmv:
        cab = "canal,nreg,fecha,emisor,categoria,texto,enlace,isin,empresa,ficha,caja,etiqueta,periodo,grupo\n"
        filas = [
            f"OIR,43719,2026-11-18T15:59:48,\"REPSOL, S.A.\",Programas de recompra,Operaciones del programa de recompra,https://cnmv/oir/43719,{REP},Repsol,repsol,recompras,Programa de recompra,,g1",
            f"OIR,43500,2026-10-30T08:00:00,\"REPSOL, S.A.\",Sobre negocio,Resultados del tercer trimestre,https://cnmv/oir/43500,{REP},Repsol,repsol,resultados,Resultados,3T 2026,g2",
            f"OIR,40000,2026-09-01T08:00:00,\"REPSOL, S.A.\",Programas de recompra,Antiguo,https://cnmv/oir/40000,{REP},Repsol,repsol,recompras,Programa de recompra,,g3",
            f"OIR,43600,2026-11-02T08:00:00,BANCO SANTANDER S.A.,Dividendos,Dividendo a cuenta,https://cnmv/oir/43600,{SAN},Santander,santander,dividendos,Dividendo,,g4",
            f"OIR,41000,2026-09-20T08:00:00,BANCO SANTANDER S.A.,Programas de recompra,Fin de programa,https://cnmv/oir/41000,{SAN},Santander,santander,recompras,Programa de recompra,,g5",
        ]
        escribe(raiz, "cnmv/datos/ibex35.csv", cab + "\n".join(filas) + "\n")
        escribe(raiz, "cnmv/datos/ultima.json", json.dumps({"actualizado": "2026-11-18T19:07"}))


with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz)
    empresas.AVISOS.clear()
    fichas = empresas.generar(raiz, HOY)
    por = {f["isin"]: f for f in fichas}
    ok(len(fichas) == 35 and REP in por and SAN in por, "Una ficha por empresa del IBEX 35 (35), aunque la fuente no tenga datos de alguna")
    f = por[REP]
    ok(f["empresa"] == "Repsol" and f["ficha"] == "https://elespeculador.com/ibex-35/repsol/", "Nombre corto y dirección de la ficha de la web")

    # Cortos
    c = f["cortos"]
    ok(c["tenedores"] == 2 and abs(c["suma_pct"] - 1.12) < 1e-9, "Cortos: solo las posiciones iguales o superiores al 0,5 % cuentan y se suman")
    ok(c["posiciones"][0]["tenedor"] == "Gestora A LLP" and c["ultima_fecha"] == "2026-11-17", "Cortos: ordenadas por tamaño; última fecha de posición")
    ok([x["tipo"] for x in c["cambios_30d"]] == ["nueva", "sube", "deja de publicarse"], "Cortos: cambios de los últimos 30 días, del más reciente al más antiguo; el de octubre queda fuera")
    ok(por[SAN]["cortos"] == {"suma_pct": 0.0, "tenedores": 0, "posiciones": [], "ultima_fecha": None, "cambios_30d": []}, "Cortos: empresa sin cortos sale con ceros, no con null")

    # Directivos
    di = f["directivos"]
    ok(di["compras_n"] == 2 and di["ventas_n"] == 1, "Directivos: 13 semanas; compra de julio fuera, plan fuera, sustituida fuera")
    ok(abs(di["compras_eur"] - 32900) < 1e-6 and abs(di["ventas_eur"] - 14500) < 1e-6 and abs(di["neto_eur"] - 18400) < 1e-6, "Directivos: importes y neto")
    ok(di["ultima_operacion"] == "2026-11-10" and di["operaciones_30d"] == 2 and di["semanas"] == 13, "Directivos: última operación y recuento de registros recientes")
    ok(por[IBE]["directivos"]["ventas_n"] == 1 and por[IBE]["directivos"]["compras_n"] == 0, "Directivos: venta de persona vinculada en otra empresa")
    ok(por[SAN]["directivos"]["compras_n"] == 0 and por[SAN]["directivos"]["ultima_operacion"] is None, "Directivos: empresa sin operaciones")

    # Accionistas
    a = f["accionistas"]
    ok(a["n"] == 2 and a["principales"][0]["accionista"] == "BLACKROCK INC" and a["principales"][0]["total_pct"] == 5.3, "Accionistas: ordenados por total, sin los de total cero")
    ok(a["derechos_voto"] == 1200000000 and a["fecha"] == "2026-10-01", "Accionistas: derechos de voto y su fecha")
    ok("1 participaciones de personas físicas" in a["nota"], "Accionistas: la nota dice cuántas personas físicas no se publican")
    ok(por[IBE]["accionistas"] is None, "Accionistas: empresa sin el campo fisicas_excluidas (salida sin filtro) no se copia")
    ok(any("sin el filtro de personas jurídicas" in x for x in empresas.AVISOS), "Accionistas: aviso por las empresas sin filtro")
    ok(f["fuentes"]["accionistas"]["estado"] == "parcial", "Accionistas: estado parcial cuando alguna empresa va sin filtro")

    # Dividendos
    dv = f["dividendo"]
    ok(dv["proximo"]["fecha_ex"] == "2026-12-15" and dv["proximo"]["bruto"] == 0.5 and dv["proximo"]["concepto"] == "A cuenta", "Dividendo: el próximo es el primero con fecha ex desde hoy; el pasado no cuenta")
    ok(dv["ultimos_12m"] == {"pagos": 2, "bruto_total": 0.95, "ultima_fecha_ex": "2026-07-07"}, "Dividendo: últimos doce meses")
    ok(por[IBE]["dividendo"]["proximo"]["flexible"] is True and por[IBE]["dividendo"]["proximo"]["fecha_pago"] is None and por[IBE]["dividendo"]["ultimos_12m"] is None, "Dividendo: flexible sin fecha de pago ni histórico")
    ok(por[SAN]["dividendo"] == {"proximo": None, "ultimos_12m": None}, "Dividendo: empresa sin dividendos anunciados")

    # CNMV: recompra, resultados, comunicados
    ok(f["recompra"]["en_curso"] is True and f["recompra"]["ultimo_comunicado"]["nreg"] == "43719", "Recompra: el último comunicado de recompra, reciente -> en curso")
    ok(por[SAN]["recompra"]["en_curso"] is False and por[SAN]["recompra"]["ultimo_comunicado"]["nreg"] == "41000", "Recompra: comunicado de hace más de 45 días -> no en curso")
    ok(f["resultados"]["periodo"] == "3T 2026", "Resultados: el último comunicado de resultados")
    ok([x["nreg"] for x in f["comunicados_30d"]] == ["43719", "43500"], "Comunicados de los últimos 30 días, del más reciente al más antiguo")

    # Eventos
    tipos = [(e["fecha"], e["tipo"]) for e in f["eventos"]]
    ok(("2026-12-15", "dividendo_ex") in tipos and ("2026-12-17", "dividendo_pago") in tipos, "Eventos: fecha ex y pago próximos entran (ventana de 30 días hacia delante)")
    ok(("2027-01-07", "dividendo_ex") not in tipos, "Eventos: dividendo a más de 30 días queda fuera")
    ok(("2026-11-12", "insider_compra") in tipos and ("2026-11-05", "insider_venta") in tipos and ("2026-10-01", "insider_compra") not in tipos, "Eventos: operaciones de directivos por fecha de registro, 30 días")
    ok(("2026-11-18", "corto_nueva") in tipos and ("2026-11-04", "corto_sale") in tipos, "Eventos: cambios de cortos")
    ok(("2026-11-18", "comunicado_recompras") in tipos and ("2026-10-30", "comunicado_resultados") in tipos, "Eventos: comunicados")
    ok(tipos == sorted(tipos, reverse=True), "Eventos: del más reciente al más antiguo")
    ev = [e for e in f["eventos"] if e["tipo"] == "insider_compra"][0]
    ok("un consejero" in ev["detalle"] and "30.100 €" in ev["detalle"] and ev["url"] == "https://cnmv/doc1" and "Gestora" not in ev["detalle"], "Eventos: detalle del directivo con cargo e importe, sin nombre")
    ev = [e for e in f["eventos"] if e["tipo"] == "dividendo_ex"][0]
    ok("0,5 EUR" in ev["detalle"] and ev["empresa"] == "Repsol" and ev["ficha"].endswith("/repsol/"), "Eventos: detalle del dividendo y enlace a la ficha")
    ok(all(e["tipo"] in empresas.TIPOS_EVENTO for ff in fichas for e in ff["eventos"]), "Eventos: todos los tipos están en la lista TIPOS_EVENTO")
    ok(por[SAN]["eventos"][0]["tipo"] == "comunicado_dividendos", "Eventos: comunicado de dividendos de Santander")

    # Huella y fuentes
    ok(len(f["huella"]) == 12 and f["version"] == empresas.VERSION and f["fecha"] == "2026-11-19", "Huella de 12 caracteres, versión y fecha")
    ok(f["fuentes"]["cortos"] == {"estado": "ok", "fecha": "2026-11-18"} and f["fuentes"]["cnmv"]["fecha"] == "2026-11-18T19:07", "Estado y fecha de cada fuente")
    fichas2 = empresas.generar(raiz, HOY)
    ok({x["isin"]: x["huella"] for x in fichas2} == {x["isin"]: x["huella"] for x in fichas}, "La huella es estable entre dos pasadas con los mismos datos")
    fichas3 = empresas.generar(raiz, date(2026, 11, 20))
    ok({x["isin"]: x["huella"] for x in fichas3} == {x["isin"]: x["huella"] for x in fichas}, "La huella no depende de la fecha de la pasada si las ventanas no cambian de contenido")

    # Escritura
    salida = raiz / "empresas"
    res = empresas.escribir(fichas, HOY, salida)
    ok(len(res["cambiadas"]) == 35 and res["eventos_cambia"] and (salida / "eventos.json").exists() and (salida / "indice.json").exists() and (salida / "index.html").exists(), "Primera escritura: 35 fichas, eventos, índice y página")
    ev_json = json.loads((salida / "eventos.json").read_text(encoding="utf-8"))
    ok(ev_json["n"] == len(ev_json["eventos"]) == sum(len(x["eventos"]) for x in fichas) and ev_json["desde"] == "2026-10-20" and ev_json["hasta"] == "2026-12-19", "eventos.json: recuento y ventana")
    ok(ev_json["eventos"][0]["fecha"] >= ev_json["eventos"][-1]["fecha"] and "tipos" in ev_json, "eventos.json: orden y diccionario de tipos")
    res2 = empresas.escribir(fichas, date(2026, 11, 20), salida)
    ok(res2["cambiadas"] == [] and len(res2["iguales"]) == 35 and not res2["eventos_cambia"], "Segunda escritura sin cambios: nada se reescribe")
    ok(json.loads((salida / f"{REP}.json").read_text(encoding="utf-8"))["fecha"] == "2026-11-19", "La ficha sin cambios conserva la fecha de su última escritura")
    res3 = empresas.escribir(fichas, date(2026, 11, 20), salida, forzar=True)
    ok(len(res3["cambiadas"]) == 35, "--forzar reescribe todo")
    pagina = (salida / "index.html").read_text(encoding="utf-8")
    ok("Repsol" in pagina and "ES0173516115.json" in pagina and "1,12 %" in pagina and "15/12/2026" in pagina, "Página: fila de Repsol con cortos, próxima fecha ex y enlace al JSON")
    indice = json.loads((salida / "indice.json").read_text(encoding="utf-8"))
    ok(len(indice["empresas"]) == 35 and indice["empresas"][0]["json"].endswith(".json"), "indice.json: 35 empresas con dirección del JSON")

# Fuentes ausentes
with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz, directivos=False, accionistas=False, dividendos=False)
    empresas.AVISOS.clear()
    fichas = empresas.generar(raiz, HOY)
    f = {x["isin"]: x for x in fichas}[REP]
    ok(f["directivos"] is None and f["accionistas"] is None and f["dividendo"] is None and f["cortos"] is not None, "Fuentes ausentes: secciones en null, las presentes se rellenan")
    ok(f["fuentes"]["directivos"]["estado"] == "ausente" and len([a for a in empresas.AVISOS if "ausente" in a]) == 3, "Fuentes ausentes: estado y un aviso por fuente")
    ok(all(e["tipo"].startswith(("corto_", "comunicado_")) for e in f["eventos"]), "Fuentes ausentes: solo eventos de las fuentes presentes")

with tempfile.TemporaryDirectory() as d:
    try:
        empresas.generar(Path(d), HOY)
        ok(False, "Sin ninguna fuente debe parar")
    except empresas.DatosRaros:
        ok(True, "Sin ninguna fuente, DatosRaros")

# Accionistas con filtro en todas: estado ok
with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz)
    j = json.loads((raiz / "accionistas/datos/ultima.json").read_text(encoding="utf-8"))
    for e in j["empresas"]:
        if not e.get("fuera"):
            e["fisicas_excluidas"] = 0
    (raiz / "accionistas/datos/ultima.json").write_text(json.dumps(j), encoding="utf-8")
    empresas.AVISOS.clear()
    fichas = empresas.generar(raiz, HOY)
    f = {x["isin"]: x for x in fichas}
    ok(f[IBE]["accionistas"]["principales"][0]["accionista"] == "QATAR INVESTMENT AUTHORITY" and f[IBE]["accionistas"]["nota"] == "Solo personas jurídicas.", "Accionistas con filtro: se copian y la nota es la simple")
    ok(f[REP]["fuentes"]["accionistas"]["estado"] == "ok" and not empresas.AVISOS, "Accionistas con filtro en todas: estado ok y sin avisos")

# Utilidades
ok(empresas._eur(30100) == "30.100 €" and empresas._eur(None) == "—" and empresas._pct(0.5) == "0,50 %" and empresas._fecha_es("2026-11-06T08:59") == "06/11/2026", "Formatos de euros, porcentajes y fechas")
ok(empresas._dia("2026-11-06T08:59:25") == "2026-11-06" and empresas._dia(None) == "" and empresas._num("") is None and empresas._num("1.5") == 1.5, "Utilidades de fecha y número")
ok(len(empresas.universo()) == 35, "El universo del repositorio tiene 35 empresas")

print(f"{TOTAL - len(FALLOS)}/{TOTAL} comprobaciones superadas")
sys.exit(1 if FALLOS else 0)
