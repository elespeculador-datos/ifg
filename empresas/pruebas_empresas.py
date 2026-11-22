"""Comprobaciones sin red de la ficha integrada (empresas/empresas.py, contrato 1.0 con el chat de fichas) con salidas
simuladas de los colectores en el formato real de cada uno (cabeceras de CSV y claves de JSON copiadas de las salidas
publicadas)."""

import csv
import json
import os
import shutil
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


def fuentes(raiz: Path, cortos=True, directivos=True, accionistas=True, cnmv=True, filtro_juridicas=True, bme=False, pct_a="0.62"):
    if cortos:
        escribe(raiz, "cortos/datos/vigentes.csv",
                "lei,isin,emisor,tenedor,fecha_posicion,posicion_pct,estado\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora A LLP,2026-11-10,{pct_a},\"igual o superior al 0,5 %\"\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora B LLC,2026-11-17,0.5,\"igual o superior al 0,5 %\"\n"
                f"L1,{REP},\"REPSOL, S.A.\",Gestora C SA,2026-11-03,0.42,\"bajó del 0,5 %\"\n"
                f"L2,{IBE},IBERDROLA S.A.,Caisse de dépôt et placement du Québec,2026-11-12,0.55,\"igual o superior al 0,5 %\"\n"
                f"L2,{IBE},IBERDROLA S.A.,\"PEREZ GARCIA, JUAN\",2026-11-12,0.51,\"igual o superior al 0,5 %\"\n")
        escribe(raiz, "cortos/datos/historial_cambios.csv",
                "fecha_publicacion,isin,emisor,tenedor,tipo,antes_pct,ahora_pct,fecha_posicion\n"
                f"2026-11-18,{REP},\"REPSOL, S.A.\",Gestora B LLC,nueva,,0.5,2026-11-17\n"
                f"2026-11-11,{REP},\"REPSOL, S.A.\",Gestora A LLP,sube,0.55,0.62,2026-11-10\n"
                f"2026-11-04,{REP},\"REPSOL, S.A.\",Gestora C SA,deja de publicarse,0.5,,\n"
                f"2026-10-01,{REP},\"REPSOL, S.A.\",Gestora X,baja,0.7,0.6,2026-09-30\n"
                f"2026-11-13,{IBE},IBERDROLA S.A.,\"PEREZ GARCIA, JUAN\",nueva,,0.51,2026-11-12\n")
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
            f"r7,1,2026-11-15,2026-11-13,IBERDROLA,A2,L2,{IBE},m,vinculada,acciones,Venta,venta,discrecional,XMAD,10,15,EUR,150,0,0,",
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
    if bme:  # salida antigua del calendario de BME: no debe leerse nunca
        escribe(raiz, "dividendos/datos/proximos.csv",
                "fecha_ex,fecha_pago,empresa,company,isin,bruto,moneda,concepto,extraordinario,flexible,ejercicio\n"
                f"2026-12-15,2026-12-17,Repsol,REPSOL,{REP},0.5,EUR,A cuenta,False,False,2026\n")
        escribe(raiz, "dividendos/datos/ultimos_12m.csv", "isin,empresa,pagos,bruto_total,ultima_fecha_ex\n" f"{REP},Repsol,2,0.95,2026-07-07\n")
        escribe(raiz, "dividendos/datos/rentabilidad.csv", "isin,rentabilidad_ordinaria_pct\n" f"{REP},2.99\n")
    if cnmv:
        cab = "canal,nreg,fecha,emisor,categoria,texto,enlace,isin,empresa,ficha,caja,etiqueta,periodo,grupo\n"
        filas = [
            f"OIR,43719,2026-11-18T15:59:48,\"REPSOL, S.A.\",Programas de recompra,Operaciones del programa de recompra,https://cnmv/oir/43719,{REP},Repsol,repsol,recompras,Programa de recompra,,g1",
            f"OIR,43500,2026-10-30T08:00:00,\"REPSOL, S.A.\",Sobre negocio,Resultados del tercer trimestre,https://cnmv/oir/43500,{REP},Repsol,repsol,resultados,Resultados,3T 2026,g2",
            f"OIR,40000,2026-09-01T08:00:00,\"REPSOL, S.A.\",Programas de recompra,Antiguo,https://cnmv/oir/40000,{REP},Repsol,repsol,recompras,Programa de recompra,,g3",
            f"OIR,43650,2026-11-12T18:56:00,\"REPSOL, S.A.\",Otra información relevante,Dividendo a cuenta 2026,https://cnmv/oir/43650,{REP},Repsol,repsol,dividendos,Dividendo,,g6",
            f"OIR,30000,2025-10-01T08:00:00,\"REPSOL, S.A.\",Otra información relevante,Dividendo de hace más de un año,https://cnmv/oir/30000,{REP},Repsol,repsol,dividendos,Dividendo,,g7",
            f"IP,3413,2026-11-07T12:37:00,\"REPSOL, S.A.\",Sobre operaciones corporativas,Repsol niega una OPA,https://cnmv/ip/3413,{REP},Repsol,repsol,opas,OPA,,g8",
            f"OIR,43600,2026-11-02T08:00:00,BANCO SANTANDER S.A.,Dividendos,Dividendo a cuenta,https://cnmv/oir/43600,{SAN},Santander,santander,dividendos,Dividendo,,g4",
            f"OIR,41000,2026-09-20T08:00:00,BANCO SANTANDER S.A.,Programas de recompra,Fin de programa,https://cnmv/oir/41000,{SAN},Santander,santander,recompras,Programa de recompra,,g5",
            f"OIR,43244,2026-10-21T08:29:27,IBERDROLA S.A.,Sobre instrumentos financieros,Iberdrola Retribución Flexible,https://cnmv/oir/43244,{IBE},Iberdrola,iberdrola,dividendos,Dividendo flexible,,g9",
            # el mismo dividendo dos veces (aprobado y ajustado por la autocartera) y otro distinto con la misma fecha
            f"OIR,43001,2026-10-01T08:00:00,IBERDROLA S.A.,Otra información relevante,Dividendo a cuenta,https://cnmv/oir/43001,{IBE},Iberdrola,iberdrola,dividendos,Dividendo,,g10",
            f"OIR,43002,2026-10-05T08:00:00,IBERDROLA S.A.,Otra información relevante,Importe ajustado del dividendo a cuenta,https://cnmv/oir/43002,{IBE},Iberdrola,iberdrola,dividendos,Dividendo,,g11",
            f"OIR,43003,2026-10-06T08:00:00,IBERDROLA S.A.,Otra información relevante,Dividendo extraordinario,https://cnmv/oir/43003,{IBE},Iberdrola,iberdrola,dividendos,Dividendo,,g12",
            f"OIR,43004,2026-10-07T08:00:00,IBERDROLA S.A.,Otra información relevante,Recordatorio del dividendo a cuenta,https://cnmv/oir/43004,{IBE},Iberdrola,iberdrola,dividendos,Dividendo,,g13",
        ]
        escribe(raiz, "cnmv/datos/ibex35.csv", cab + "\n".join(filas) + "\n")
        escribe(raiz, "cnmv/datos/ultima.json", json.dumps({"actualizado": "2026-11-18T19:07", "historico": {
            "IP": {"desde": "2025-10-10", "completo": True}, "OIR": {"desde": "2025-10-08", "completo": True}}}))
        escribe(raiz, "cnmv/datos/dividendos.csv",
                "canal,nreg,fecha_comunicado,isin,empresa,tipo,importe_bruto,moneda,fecha_ex,fecha_registro,fecha_pago,extraccion,intentos,enlace\n"
                f"OIR,43650,2026-11-12,{REP},Repsol,Dividendo,0.5,EUR,2026-12-15,2026-12-16,2026-12-17,completa,1,https://cnmv/oir/43650\n"
                f"OIR,43600,2026-11-02,{SAN},Santander,Dividendo,,,,,2026-11-04,parcial,1,https://cnmv/oir/43600\n"
                f"OIR,43244,2026-10-21,{IBE},Iberdrola,Dividendo flexible,,,,,,flexible: ver comunicado,1,https://cnmv/oir/43244\n"
                f"OIR,43001,2026-10-01,{IBE},Iberdrola,Dividendo,5.65,EUR,2026-11-25,2026-11-26,2026-11-27,completa,1,https://cnmv/oir/43001\n"
                f"OIR,43002,2026-10-05,{IBE},Iberdrola,Dividendo,5.74867096,EUR,2026-11-25,2026-11-26,2026-11-27,completa,1,https://cnmv/oir/43002\n"
                f"OIR,43003,2026-10-06,{IBE},Iberdrola,Dividendo,0.5,EUR,2026-11-25,2026-11-26,2026-11-27,completa,1,https://cnmv/oir/43003\n"
                f"OIR,43004,2026-10-07,{IBE},Iberdrola,Dividendo,,,2026-11-25,,2026-11-27,parcial,1,https://cnmv/oir/43004\n")


def todas_las_claves(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from todas_las_claves(v)
    elif isinstance(x, list):
        for v in x:
            yield from todas_las_claves(v)


with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz, bme=True)
    empresas.AVISOS.clear()
    fichas = empresas.generar(raiz, HOY)
    por = {f["isin"]: f for f in fichas}
    ok(len(fichas) == 35 and REP in por and SAN in por, "Una ficha por empresa del IBEX 35 (35), aunque la fuente no tenga datos de alguna")
    f = por[REP]

    # Contrato 1.0 (campos que lee la ficha de la web)
    campos = {"contrato", "empresa", "isin", "ficha", "actualizado", "registro_oficial", "dividendos", "cortos", "directivos", "accionistas",
              "recompra", "cuatro_fuerzas", "perfil", "eventos", "fuentes", "licencia", "aviso", "huella", "version"}
    ok(set(f) == campos and f["contrato"] == "1.0", f"Contrato 1.0: exactamente los campos acordados ({sorted(set(f) ^ campos)})")
    ok(f["empresa"] == "Repsol" and f["ficha"] == "https://elespeculador.com/ibex35/repsol/", "Dirección real de la ficha: /ibex35/<ficha>/ (no /ibex-35/)")
    ok(all(x["ficha"].startswith("https://elespeculador.com/ibex35/") for x in fichas), "Las 35 fichas apuntan a /ibex35/")
    ok(set(f["fuentes"]) == {"registro_oficial", "dividendos", "recompra", "cortos", "directivos", "accionistas", "cuatro_fuerzas", "perfil"},
       "fuentes: estado y fecha de cada bloque")

    # Nada de BME, aunque la salida antigua del calendario esté en la carpeta
    texto = json.dumps(fichas, ensure_ascii=False)
    ok("BME" not in texto and "rentabilidad" not in texto.lower() and "dividendo" not in f and "2,99" not in texto,
       "Ni BME ni rentabilidad en ninguna ficha, aunque existan los ficheros antiguos de BME")
    ok("rentabilidad" not in set(todas_las_claves(fichas)), "Ninguna clave «rentabilidad»")

    # Cortos
    c = f["cortos"]
    ok(c["tenedores"] == 2 and abs(c["total_publicado"] - 1.12) < 1e-9 and c["fecha_dato"] == "2026-11-18",
       "Cortos: total publicado (posiciones ≥ 0,5 %), tenedores y fecha del dato de la CNMV")
    ok(c["posiciones"][0]["tenedor"] == "Gestora A LLP" and c["ultima_posicion"] == "2026-11-17" and c["fuente"].startswith("CNMV"),
       "Cortos: posiciones de mayor a menor, última posición y fuente")
    ok([x["tipo"] for x in c["cambios_30d"]] == ["nueva", "sube", "deja de publicarse"], "Cortos: cambios de 30 días, del más reciente al más antiguo")
    ok(por[SAN]["cortos"]["total_publicado"] == 0.0 and por[SAN]["cortos"]["posiciones"] == [], "Cortos: empresa sin cortos sale con ceros")
    ib = por[IBE]["cortos"]
    nombres = [p["tenedor"] for p in ib["posiciones"]] + [x["tenedor"] for x in ib["cambios_30d"]]
    ok("Caisse de dépôt et placement du Québec" in nombres and "PEREZ GARCIA, JUAN" not in json.dumps(por[IBE], ensure_ascii=False)
       and empresas.SIN_NOMBRE in nombres, "Cortos: una entidad sin forma societaria conserva el nombre; un nombre de persona física no se publica")
    ok(any("sin forma de persona jurídica" in a for a in empresas.AVISOS), "Cortos: aviso por el tenedor sin nombre")

    # Directivos
    di = f["directivos"]
    ok(di["compras_n"] == 2 and di["ventas_n"] == 1, "Directivos: 13 semanas; compra de julio fuera, plan fuera, sustituida fuera")
    ok(abs(di["compras_eur"] - 32900) < 1e-6 and abs(di["ventas_eur"] - 14500) < 1e-6 and abs(di["neto_eur"] - 18400) < 1e-6, "Directivos: importes y neto")
    ok(di["ultima_operacion"] == "2026-11-10" and di["operaciones_30d"] == 2 and di["semanas"] == 13, "Directivos: última operación y recuento de registros recientes")
    ok(por[IBE]["directivos"]["ventas_n"] == 1 and por[IBE]["directivos"]["compras_n"] == 0, "Directivos: venta de persona vinculada en otra empresa")

    # Accionistas
    a = f["accionistas"]
    ok(a["n"] == 2 and a["principales"][0]["accionista"] == "BLACKROCK INC" and a["principales"][0]["total_pct"] == 5.3, "Accionistas: ordenados por total, sin los de total cero")
    ok("1 participaciones de personas físicas" in a["nota"] and a["fuente"].startswith("CNMV"), "Accionistas: nota de personas físicas no publicadas y fuente")
    ok(por[IBE]["accionistas"] is None and por[IBE]["fuentes"]["accionistas"]["estado"] == "vacio", "Accionistas: empresa sin el filtro de personas jurídicas no se copia (bloque vacío)")
    ok(f["fuentes"]["accionistas"]["estado"] == "parcial", "Accionistas: estado parcial cuando alguna empresa va sin filtro")

    # Registro oficial (doce meses) y dividendos de la CNMV
    ro = f["registro_oficial"]
    ok([x["nreg"] for x in ro] == ["43719", "43650", "3413", "43500", "40000"], f"Registro oficial: doce meses, del más reciente al más antiguo ({[x['nreg'] for x in ro]})")
    ok(set(ro[0]) == {"fecha", "tipo", "titulo", "fuente", "enlace", "nreg", "grupo"} and ro[3]["tipo"] == "Resultados 3T 2026" and ro[2]["tipo"] == "OPA",
       "Registro oficial: campos del contrato y tipo con periodo")
    dv = f["dividendos"]
    ok(len(dv) == 1 and dv[0]["nreg"] == "43650" and dv[0]["fecha_comunicado"] == "2026-11-12" and dv[0]["fuente"] == "CNMV"
       and dv[0]["importe"] == 0.5 and dv[0]["moneda"] == "EUR" and dv[0]["fecha_ex"] == "2026-12-15" and dv[0]["fecha_pago"] == "2026-12-17"
       and dv[0]["lectura"] == "leído del comunicado" and dv[0]["enlace"] == "https://cnmv/oir/43650",
       "Dividendos: anuncio de la CNMV con importe, moneda y fechas leídos del propio comunicado")
    ds = por[SAN]["dividendos"][0]
    ok(ds["importe"] is None and ds["moneda"] is None and ds["fecha_pago"] == "2026-11-04" and ds["lectura"].startswith("parcial"),
       "Dividendos: lectura parcial, solo lo que se leyó con seguridad")
    di = por[IBE]["dividendos"][0]
    ok(di["importe"] is None and "flexible" in di["lectura"], "Dividendos: flexible sin importe y con su explicación")
    ok(por[IBE]["dividendos"][0]["tipo"] == "Dividendo flexible" and por[SAN]["dividendos"][0]["nreg"] == "43600", "Dividendos: flexible y de otra empresa")
    fr = f["fuentes"]["registro_oficial"]
    ok(fr["desde"] == "2025-11-19" and fr["alcance"].startswith("Comunicados a la CNMV") and fr["estado"] == "ok",
       "Registro oficial: con el histórico completo, desde hace doce meses, y con su alcance")
    ok(f["directivos"]["fecha_dato"] == "2026-11-18" and f["accionistas"]["fecha_dato"] == "2026-11-18" and f["recompra"]["fecha_dato"] == "2026-11-18"
       and f["cortos"]["fecha_dato"] == "2026-11-18", "Cada bloque con la fecha de su dato")
    ok(all(b is None or "fuente" in b for b in (f["cortos"], f["directivos"], f["accionistas"], f["recompra"]))
       and all("fuente" in x and "fecha" in x for x in f["registro_oficial"]) and all("fuente" in x and "fecha_comunicado" in x for x in f["dividendos"]),
       "Cada dato con su fuente y su fecha")
    ok(f["recompra"]["en_curso"] is True and f["recompra"]["ultimo_comunicado"]["nreg"] == "43719", "Recompra: el último comunicado de recompra, reciente -> en curso")
    ok(por[SAN]["recompra"]["en_curso"] is False and por[SAN]["recompra"]["ultimo_comunicado"]["nreg"] == "41000", "Recompra: comunicado de hace más de 45 días -> no en curso")
    ok(f["cuatro_fuerzas"] == [] and f["perfil"] is None and f["fuentes"]["cuatro_fuerzas"]["estado"] == "pendiente"
       and f["fuentes"]["perfil"]["estado"] == "pendiente", "Cuatro fuerzas y perfil: vacíos y «pendiente» mientras no haya filas")

    # Eventos
    tipos = [(e["fecha"], e["tipo"]) for e in f["eventos"]]
    ok(("2026-11-12", "insider_compra") in tipos and ("2026-11-05", "insider_venta") in tipos and ("2026-10-01", "insider_compra") not in tipos, "Eventos: operaciones de directivos por fecha de registro, 30 días")
    ok(("2026-11-18", "corto_nueva") in tipos and ("2026-11-04", "corto_sale") in tipos, "Eventos: cambios de cortos")
    ok(("2026-11-18", "comunicado_recompras") in tipos and ("2026-10-30", "comunicado_resultados") in tipos and ("2026-11-12", "comunicado_dividendos") in tipos
       and ("2026-11-07", "comunicado_opas") in tipos, "Eventos: comunicados con su tipo (también OPA)")
    ok(("2026-12-15", "dividendo_ex") in tipos and ("2026-12-17", "dividendo_pago") in tipos, "Eventos: fecha ex y pago del dividendo leído de la CNMV")
    evd = [e for e in f["eventos"] if e["tipo"] == "dividendo_ex"][0]
    ok(evd["detalle"] == "Dividendo de 0,5 € brutos por acción; pago el 17/12/2026." and evd["url"] == "https://cnmv/oir/43650" and evd["fuente"] == "CNMV",
       f"Eventos: detalle del dividendo con importe y la otra fecha ({evd['detalle']})")
    ok([e["tipo"] for e in por[SAN]["eventos"]].count("dividendo_pago") == 1 and not any(e["tipo"] == "dividendo_ex" for e in por[SAN]["eventos"]),
       "Eventos: dividendo parcial, solo la fecha que se leyó")
    exi = sorted(e["detalle"] + " " + e["url"] for e in por[IBE]["eventos"] if e["tipo"] == "dividendo_ex")
    ok(exi == ["Dividendo de 0,5 € brutos por acción; pago el 27/11/2026. https://cnmv/oir/43003",
               "Dividendo de 5,74867096 € brutos por acción; pago el 27/11/2026. https://cnmv/oir/43002"],
       f"Eventos: el mismo dividendo anunciado varias veces da un evento (el importe ajustado, más reciente; el recordatorio sin importe "
       f"no lo borra); otro dividendo con la misma fecha, otro evento ({exi})")
    ok(tipos == sorted(tipos, reverse=True), "Eventos: del más reciente al más antiguo")
    ev = [e for e in f["eventos"] if e["tipo"] == "insider_compra"][0]
    ok("un consejero" in ev["detalle"] and "30.100 €" in ev["detalle"] and ev["url"] == "https://cnmv/doc1" and ev["ficha"].endswith("/ibex35/repsol/"),
       "Eventos: detalle del directivo con cargo e importe, sin nombre, enlace al documento y a la ficha")
    ok([e for e in por[IBE]["eventos"] if e["tipo"] == "insider_venta"][0]["url"] == "", "Eventos: sin documento, sin enlace (no a una página en borrador)")
    ok([e for e in f["eventos"] if e["tipo"] == "corto_nueva"][0]["url"] == "https://elespeculador.com/posiciones-cortas-hoy/", "Eventos de cortos: enlace a la página publicada")
    ok(all(e["tipo"] in empresas.TIPOS_EVENTO for ff in fichas for e in ff["eventos"]), "Eventos: todos los tipos están en la lista TIPOS_EVENTO")

    # Huella
    ok(len(f["huella"]) == 12 and f["version"] == empresas.VERSION and f["actualizado"] == "2026-11-19", "Huella de 12 caracteres, versión y fecha")
    fichas2 = empresas.generar(raiz, HOY)
    ok({x["isin"]: x["huella"] for x in fichas2} == {x["isin"]: x["huella"] for x in fichas}, "La huella es estable entre dos pasadas con los mismos datos")
    fichas3 = empresas.generar(raiz, date(2026, 11, 20))
    ok({x["isin"]: x["huella"] for x in fichas3} == {x["isin"]: x["huella"] for x in fichas}, "La huella no depende de la fecha de la pasada si las ventanas no cambian de contenido")

    # Escritura, índice y registro de cambios
    salida = raiz / "empresas"
    res = empresas.escribir(fichas, HOY, salida)
    ok(len(res["cambiadas"]) == 35 and res["eventos_cambia"] and res["cambios"] == 0 and not (salida / "cambios.csv").exists(),
       "Primera escritura: 35 fichas; sin ficha anterior no hay cambios que anotar")
    ev_json = json.loads((salida / "eventos.json").read_text(encoding="utf-8"))
    ok(ev_json["n"] == len(ev_json["eventos"]) == sum(len(x["eventos"]) for x in fichas) and ev_json["desde"] == "2026-10-20" and ev_json["hasta"] == "2026-12-19", "eventos.json: recuento y ventana")
    res2 = empresas.escribir(empresas.generar(raiz, date(2026, 11, 20), salida), date(2026, 11, 20), salida)
    indice = json.loads((salida / "indice.json").read_text(encoding="utf-8"))
    ok(res2["cambiadas"] == [] and len(res2["iguales"]) == 35 and indice["comprobado"] == "2026-11-20" and indice["contrato"] == "1.0",
       "Segunda pasada sin cambios: no se reescribe ninguna ficha, pero indice.json dice que se comprobó")
    ok(json.loads((salida / f"{REP}.json").read_text(encoding="utf-8"))["actualizado"] == "2026-11-19", "La ficha sin cambios conserva la fecha de su último cambio")
    fuentes(raiz, pct_a="0.70")
    res3 = empresas.escribir(empresas.generar(raiz, date(2026, 11, 21), salida), date(2026, 11, 21), salida)
    filas = list(csv.DictReader((salida / "cambios.csv").open(encoding="utf-8")))
    campos_cambiados = {(x["isin"], x["campo"], x["antes"], x["despues"]) for x in filas}
    ok(REP in res3["cambiadas"] and (REP, "cortos.posicion[Gestora A LLP]", "0.62", "0.7") in campos_cambiados
       and (REP, "cortos.total_publicado", "1.12", "1.2") in campos_cambiados, f"cambios.csv: cada cifra que cambia, con antes y después ({sorted(campos_cambiados)})")
    ok(all(x["fecha"] == "2026-11-21" and x["fuente"].startswith("CNMV") for x in filas), "cambios.csv: fecha de la pasada y fuente")
    pagina = (salida / "index.html").read_text(encoding="utf-8")
    ok("Repsol" in pagina and "ES0173516115.json" in pagina and "1,20 %" in pagina and "BME" not in pagina, "Página: fila de Repsol con cortos y enlace al JSON, sin BME")

    # Último dato bueno: si un colector falla, su bloque se conserva marcado «anterior»
    shutil.rmtree(raiz / "cortos")
    empresas.AVISOS.clear()
    f4 = {x["isin"]: x for x in empresas.generar(raiz, date(2026, 11, 22), salida)}[REP]
    previa = json.loads((salida / f"{REP}.json").read_text(encoding="utf-8"))
    ok(f4["cortos"] == previa["cortos"] and f4["fuentes"]["cortos"] == {"estado": "anterior", "fecha": "2026-11-18"},
       "Último dato bueno: sin salida de cortos, la ficha conserva el bloque anterior, marcado «anterior» y con su fecha")
    ok(any(e["tipo"] == "corto_nueva" for e in f4["eventos"]), "Último dato bueno: también los eventos de cortos dentro de la ventana")
    f5 = {x["isin"]: x for x in empresas.generar(raiz, date(2026, 11, 22))}[REP]
    ok(f5["cortos"] is None and f5["fuentes"]["cortos"]["estado"] == "vacio", "Sin ficha anterior, el bloque va vacío y la web lo oculta")

# Registro oficial con el histórico aún incompleto: desde la fecha más reciente de los dos canales
with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz)
    escribe(raiz, "cnmv/datos/ultima.json", json.dumps({"actualizado": "2026-11-18T19:07", "historico": {
        "IP": {"desde": "2026-03-02", "completo": False}, "OIR": {"desde": "2026-05-11", "completo": False}}}))
    f = {x["isin"]: x for x in empresas.generar(raiz, HOY)}[REP]
    ok(f["fuentes"]["registro_oficial"]["desde"] == "2026-05-11", "Registro oficial incompleto: «desde» es la fecha más reciente de los dos canales")

# Fuentes ausentes
with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz, directivos=False, accionistas=False)
    empresas.AVISOS.clear()
    fichas = empresas.generar(raiz, HOY)
    f = {x["isin"]: x for x in fichas}[REP]
    ok(f["directivos"] is None and f["accionistas"] is None and f["cortos"] is not None, "Fuentes ausentes: secciones en null, las presentes se rellenan")
    ok(f["fuentes"]["directivos"]["estado"] == "vacio" and len([a for a in empresas.AVISOS if "ausente" in a]) == 2, "Fuentes ausentes: estado y un aviso por fuente")
    ok(all(e["tipo"].startswith(("corto_", "comunicado_", "dividendo_")) for e in f["eventos"]), "Fuentes ausentes: solo eventos de las fuentes presentes")

with tempfile.TemporaryDirectory() as d:
    try:
        empresas.generar(Path(d), HOY)
        ok(False, "Sin ninguna fuente debe parar")
    except empresas.DatosRaros:
        ok(True, "Sin ninguna fuente, DatosRaros")

# Cuatro fuerzas y perfil: tablas de Datos con documento y página
with tempfile.TemporaryDirectory() as d:
    raiz = Path(d)
    fuentes(raiz)
    fz, pf = raiz / "cuatro_fuerzas.csv", raiz / "perfil.csv"
    fz.write_text(",".join(empresas.COLUMNAS_FUERZAS) + "\n"
                  f"{REP},divisa,Ingresos fuera de la zona euro,41,% de los ingresos,Ingresos fuera de la zona euro: 41 % del total,2025,"
                  "Informe financiero anual 2025,212,https://cnmv/ifa/rep,2026-02-19,dos extracciones coincidentes,2026-11-30\n", encoding="utf-8")
    pf.write_text(",".join(empresas.COLUMNAS_PERFIL) + "\n" f"{REP},Madrid,31/12,https://ejemplo/ri,CNMV y web de la empresa,2026-11-30\n", encoding="utf-8")
    viejo = (empresas.CUATRO_FUERZAS, empresas.PERFIL)
    empresas.CUATRO_FUERZAS, empresas.PERFIL = fz, pf
    try:
        por = {x["isin"]: x for x in empresas.generar(raiz, HOY)}
        r = por[REP]
        ok(r["cuatro_fuerzas"][0]["cifra"] == "41" and r["cuatro_fuerzas"][0]["pagina"] == "212" and r["fuentes"]["cuatro_fuerzas"]["estado"] == "ok",
           "Cuatro fuerzas: la fila de la empresa con cifra, documento y página")
        ok(r["perfil"]["sede"] == "Madrid" and por[SAN]["perfil"] is None and por[SAN]["cuatro_fuerzas"] == []
           and por[SAN]["fuentes"]["perfil"]["estado"] == "pendiente", "Perfil: solo para la empresa con fila; las demás, pendiente")
        pf.write_text("isin,sede\n" f"{REP},Madrid\n", encoding="utf-8")
        try:
            empresas.generar(raiz, HOY)
            ok(False, "Tabla de perfil sin sus columnas: debe parar")
        except empresas.DatosRaros:
            ok(True, "Tabla de perfil sin sus columnas: DatosRaros")
    finally:
        empresas.CUATRO_FUERZAS, empresas.PERFIL = viejo

# Utilidades
ok(empresas._eur(30100) == "30.100 €" and empresas._eur(None) == "—" and empresas._pct(0.5) == "0,50 %" and empresas._fecha_es("2026-11-06T08:59") == "06/11/2026", "Formatos de euros, porcentajes y fechas")
ok(empresas._dia("2026-11-06T08:59:25") == "2026-11-06" and empresas._dia(None) == "" and empresas._num("") is None and empresas._num("1.5") == 1.5, "Utilidades de fecha y número")
ok(empresas._num("nan") is None and empresas._num("inf") is None, "Sin NaN ni infinitos: el JSON es siempre válido")
ok(len(empresas.universo()) == 35, "El universo del repositorio tiene 35 empresas")
ok(empresas.es_entidad("Marshall Wace LLP") and empresas.es_entidad("Caisse de dépôt et placement du Québec") and not empresas.es_entidad("GARCIA PEREZ, JUAN"),
   "Regla de persona jurídica para tenedores de cortos")

print(f"{TOTAL - len(FALLOS)}/{TOTAL} comprobaciones superadas")
sys.exit(1 if FALLOS else 0)
