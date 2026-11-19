"""Comprobaciones sin red del colector de directivos (indicador 10).

  python directivos/pruebas_directivos.py

Datos simulados con el formato real de la CNMV (listado por fechas y texto de pdftotext del formulario
estándar) y valores conocidos: el lector del listado no guarda nombres, el lector del PDF saca las filas,
la clasificación discrecional/plan/derivado/fuera de mercado, la recogida con estado (no vuelve a bajar
lo ya leído, apunta los PDF que fallan, amplía la cobertura hacia atrás), la serie semanal, la ventana de
13 semanas, el percentil (caso de control contra scipy si está), la huella y la escritura.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import directivos as d  # noqa: E402

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 18)


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


# --------------------------------------------------------------------------- fixtures con el formato real
def bloque(i: int, fecha: str, emisor: str, nif: str, nombre: str, motivo: str, registro: str) -> str:
    return f'''<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_elementoPrimerNivel" class="blocks-single">
<ul id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_sublistaIzquierda" class="col-12 col-sm-12 single">
<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_liFechaRegistro" class="fecha-no-icon"> {fecha} </li>
<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_liTituloCabecera"> <a id="x" href="datosentidad.aspx?nif={nif}" target="_self"><span id="y" class="tit-small">{emisor}</span></a> </li>
<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_lisubTituloCabecera"> <span class="resumen"> <span id="z" class="negrita" lang="es">Declarante: {nombre}</span> </span></li>
<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl{i:02d}_liSubtituloRegistro" class="padding-r resumen"> <a id="w" href="https://www.cnmv.es/webservices/verdocumento/ver?e=ABC{registro}%2b" target="_blank">Motivo de la notificación: {motivo}</a> </li>
<li class="padding-r resumen"> Número de registro: {registro} </li>
</ul></li>'''


def listado(pagina: int, total: int, filas: list[tuple]) -> str:
    cuerpo = "".join(bloque(i + 1, *f) for i, f in enumerate(filas))
    return f'''<html><body><div class="paginador"><span class="PagActivaTXT">Página {pagina} de {total}</span></div>
<ul id="listaElementosPrimernivel">{cuerpo}</ul><p>Para notificaciones anteriores al 1 de mayo de 2018</p></body></html>'''


def pdf_texto(nombre: str, cargo: str, emisor: str, lei: str, filas: list[str], otra: str = "", pdmr: bool = True, inicial: str = "Inicial") -> str:
    marca_p = "[√]" if pdmr else "[    ]"
    marca_v = "[    ]" if pdmr else "[√]"
    cuerpo = "\n".join(filas)
    return f"""                      Formulario                                         Standard Form
                      MODELO DE NOTIFICACIÓN DE LAS                      STANDARD FORM FOR NOTIFICATION

1. DATOS DE LA PERSONA CON RESPONSABILIDAD DE DIRECCIÓN - PERSONA ESTRECHAMENTE VINCULADA | DETAILS
OF THE PERSON DISCHARGING MANAGERIAL RESPONSABILITIES (PDMR) - PERSON CLOSELY ASSOCIATED

 a) Nombre y apellidos - Razón social | Name and surname - Company name

  {nombre}

2. MOTIVO DE LA NOTIFICACIÓN | REASON FOR THE NOTIFICACTION

  {marca_p}      Persona con responsabilidad de dirección | Person discharging managerial responsibilities (PDMR)

  {marca_v}   Persona estrechamente vinculada | Person closely associated

 a) Cargo - posición | Job title

      {cargo}

 b) Notiﬁcación inicial - Modiﬁcación | Initial Notiﬁcation - Amendment

      {inicial}

3. DATOS DEL EMISOR, EL PARTICIPANTE DEL MERCADO DE DERECHOS DE EMISIÓN, LA PLATAFORMA DE SUBASTA, EL
SUBASTADOR O LA ENTIDAD SUPERVISORA DE LAS SUBASTAS | DETAILS OF THE ISSUER

 a) Identiﬁcación | Name:

      {emisor}

 b) LEI:

      {lei}

                                                                                                          1/2
                    Formulario

4. DATOS DE LA OPERACIÓN O LAS OPERACIONES (El siguiente cuadro se repetirá para: i) cada tipo de instrumento
ﬁnanciero; ii) cada tipo de operación; iii) cada fecha, y iv) cada lugar en que se hayan realizado operaciones) | DETAILS OF THE
TRANSACTIONS

   Código de
 Identiﬁcación    Naturaleza del
del instrumento    instrumento     Naturaleza de
                                                                     Lugar de la operación
   ﬁnanciero         ﬁnanciero      la operación        Fecha                                Volumen   Precio Unitario    Divisa
       4.a)             4.b)             4.c)           4.d)               4.e)                4.f)         4.g)          4.h)


{cuerpo}
                                                       Total Agregado
                                                              ...
                                                                                              25,00        19,30
                                                   Aggregated information
                                                              5)

 Otra información | Additional information
    {otra}

                                                                                                                         2/2
"""


F_COMPRA = " ES0113900J37        Acción          Compra            10/11/2026           XMAD              1.000,00        3,45           EUR"
F_VENTA = " ES0113900J37        Acción          Venta             12/11/2026           XMAD              500,00        3,50           EUR"
F_PLAN = " ES0137650018        Acción          Compra            16/11/2026           XMAD              25,00        19,30           EUR"
F_FUERA = " ES0148396007        Acción          Compra            11/11/2026           Fuera de un centro de negociación              2.000,00        27,10           EUR"
F_DERIV = " ES0148396007        Opciones sobre acciones          Compra            11/11/2026           XMAD              100,00        1,20           EUR"
F_USD = " ES0109067019        Acción          Compra            13/11/2026           XNYS              10,00        50,00           USD"
F_VENTA2 = " ES0109067019        Acción          Venta             14/11/2026           XMAD              300,00        1,10           EUR"


def fixtures(loc: Path) -> None:
    """Listado de los últimos 21 días (hoy-21..hoy) en dos páginas, y los PDF (texto) de cada registro."""
    desde, hasta = (HOY - timedelta(days=d.DIAS_RECIENTES)).isoformat(), HOY.isoformat()
    p1 = [("18/11/2026", "FLUIDRA, S.A.", "A-17728593", "CLARA VALERA JAQUES", "Persona con Responsabilidad de Dirección", "2026146046"),
          ("17/11/2026", "BANCO SANTANDER, S.A.", "A-39000013", "JUAN NADIE NADIE", "Persona con Responsabilidad de Dirección", "2026146001"),
          ("17/11/2026", "BANCO SANTANDER, S.A.", "A-39000013", "ANA NADIE NADIE", "Persona estrechamente vinculada", "2026146002")]
    p2 = [("12/11/2026", "AMADEUS IT GROUP, S.A.", "A-84236934", "PEPE NADIE", "Persona con Responsabilidad de Dirección", "2026145900"),
          ("12/11/2026", "AMADEUS IT GROUP, S.A.", "A-84236934", "PEPE NADIE", "Persona con Responsabilidad de Dirección", "2026145901"),
          ("11/11/2026", "ENAGAS, S.A.", "A-28294726", "LUISA NADIE", "Persona con Responsabilidad de Dirección", "2026145800"),
          ("11/11/2026", "ENAGAS, S.A.", "A-28294726", "LUISA NADIE", "Persona con Responsabilidad de Dirección", "2026145801"),
          ("10/11/2026", "ROTO, S.A.", "A-00000000", "NADIE", "Persona con Responsabilidad de Dirección", "2026145700")]
    (loc / f"listado_{desde}_{hasta}_0.html").write_text(listado(1, 2, p1), encoding="utf-8")
    (loc / f"listado_{desde}_{hasta}_1.html").write_text(listado(2, 2, p2), encoding="utf-8")
    (loc / "doc_2026146046.txt").write_text(pdf_texto("CLARA VALERA JAQUES", "STRATEGY, INVESTOR RELATIONS AND FP&A SENIOR DIRECTOR", "FLUIDRA, S.A.", "95980020140005026620", [F_PLAN],
                                                     "LA OPERACIÓN DECLARADA EN ESTA COMUNICACIÓN DERIVA DE LA IMPLEMENTACIÓN DEL PLAN GLOBAL DE COMPRA INCENTIVADA DE ACCIONES PARA EMPLEADOS"), encoding="utf-8")
    (loc / "doc_2026146001.txt").write_text(pdf_texto("JUAN NADIE NADIE", "CONSEJERO", "BANCO SANTANDER, S.A.", "5493006QMFDDMYWIAM13", [F_COMPRA]), encoding="utf-8")
    (loc / "doc_2026146002.txt").write_text(pdf_texto("ANA NADIE NADIE", "", "BANCO SANTANDER, S.A.", "5493006QMFDDMYWIAM13", [F_VENTA], pdmr=False), encoding="utf-8")
    (loc / "doc_2026145900.txt").write_text(pdf_texto("PEPE NADIE", "CONSEJERO DELEGADO", "AMADEUS IT GROUP, S.A.", "", [F_FUERA]), encoding="utf-8")
    (loc / "doc_2026145901.txt").write_text(pdf_texto("PEPE NADIE", "CONSEJERO DELEGADO", "AMADEUS IT GROUP, S.A.", "", [F_DERIV]), encoding="utf-8")
    (loc / "doc_2026145800.txt").write_text(pdf_texto("LUISA NADIE", "DIRECTORA GENERAL", "ENAGAS, S.A.", "", [F_USD, F_VENTA2]), encoding="utf-8")
    (loc / "doc_2026145801.txt").write_text(pdf_texto("LUISA NADIE", "DIRECTORA GENERAL", "ENAGAS, S.A.", "", [F_VENTA2], inicial="Modificación"), encoding="utf-8")
    # el registro 2026145700 no tiene PDF: debe quedar pendiente


# --------------------------------------------------------------------------- lectores
def prueba_listado():
    html = listado(1, 3, [("18/11/2026", "FLUIDRA, S.A.", "A-17728593", "CLARA VALERA JAQUES", "Persona con Responsabilidad de Dirección", "2026146046"),
                          ("17/11/2026", "REPSOL, S.A.", "A78374725", "LUIS NADIE", "Persona estrechamente vinculada", "2026145733")])
    filas, pag, tot = d.leer_listado(html)
    ok((pag, tot) == (1, 3) and len(filas) == 2, f"listado: paginación y filas: {pag}/{tot}, {len(filas)}")
    ok(filas[0] == {"registro": "2026146046", "fecha_registro": "2026-11-18", "emisor": "FLUIDRA, S.A.", "nif": "A17728593", "motivo": "directivo",
                    "documento": "https://www.cnmv.es/webservices/verdocumento/ver?e=ABC2026146046%2b"}, f"listado: campos: {filas[0]}")
    ok(filas[1]["motivo"] == "vinculada" and filas[1]["nif"] == "A78374725", "listado: persona vinculada y NIF sin guion")
    ok(not any("VALERA" in str(v) or "NADIE" in str(v) for f in filas for v in f.values()), "listado: no guarda el nombre del declarante")
    ok(d.leer_listado("<html>No se han encontrado resultados</html>") == ([], 1, 1), "listado: sin resultados")
    try:
        d.leer_listado("<html><body>otra cosa</body></html>")
        ok(False, "listado: página rara aceptada")
    except d.DatosRaros:
        ok(True, "")


def prueba_pdf():
    t = pdf_texto("CLARA VALERA JAQUES", "STRATEGY, INVESTOR RELATIONS AND FP&A SENIOR DIRECTOR", "FLUIDRA, S.A.", "95980020140005026620", [F_PLAN],
                  "LA OPERACIÓN DECLARADA EN ESTA COMUNICACIÓN DERIVA DE LA IMPLEMENTACIÓN DEL PLAN GLOBAL DE COMPRA INCENTIVADA DE ACCIONES PARA EMPLEADOS DE FLUIDRA")
    det = d.leer_notificacion(t, "directivo")
    ok(det["filas"] == [{"isin": "ES0137650018", "instrumento": "Acción", "operacion": "Compra", "fecha_operacion": "2026-11-16", "lugar": "XMAD", "volumen": 25.0, "precio": 19.3, "divisa": "EUR"}],
       f"PDF: fila de operación: {det['filas']}")
    ok(det["lei"] == "95980020140005026620" and det["emisor_pdf"] == "FLUIDRA, S.A." and det["cargo_tipo"] == "directivo" and not det["modificacion"], f"PDF: cabecera: {det}")
    ok("PLAN GLOBAL" in det["otra_informacion"], "PDF: otra información")
    ok("VALERA" not in json.dumps(det), "PDF: el detalle no lleva el nombre")
    det = d.leer_notificacion(pdf_texto("X", "CONSEJERO", "ENAGAS, S.A.", "", [F_USD, F_VENTA2], inicial="Modificación"), "directivo")
    ok(len(det["filas"]) == 2 and det["filas"][0]["divisa"] == "USD" and det["filas"][1]["volumen"] == 300.0 and det["modificacion"], f"PDF: dos filas y modificación: {det['filas']}")
    ok(det["cargo_tipo"] == "consejero", "PDF: consejero")
    ok(d.leer_notificacion(pdf_texto("X", "", "B", "", [F_VENTA], pdmr=False), "vinculada")["cargo_tipo"] == "vinculada", "PDF: vinculada")
    fuera = d.leer_notificacion(pdf_texto("X", "CEO", "AMADEUS IT GROUP, S.A.", "", [F_FUERA]), "directivo")["filas"]
    ok(fuera and fuera[0]["lugar"] == "Fuera de un centro de negociación" and fuera[0]["volumen"] == 2000.0, f"PDF: lugar con espacios y miles: {fuera}")
    # sin filas legibles pero con total agregado
    t = pdf_texto("X", "CEO", "B, S.A.", "", ["  ES0113900J37   Acción   Compra   10/11/2026   XMAD   (ver abajo)"])
    det = d.leer_notificacion(t, "directivo")
    ok(len(det["filas"]) == 1 and det["filas"][0].get("agregado") and det["filas"][0]["volumen"] == 25.0 and det["filas"][0]["operacion"] == "compra", f"PDF: recurso al total agregado: {det['filas']}")
    ok(d._numero("1.234,56") == 1234.56 and d._numero("25,00") == 25.0 and d._numero("1.000") == 1000.0 and d._numero("19.30") == 19.3 and d._numero("...") is None, "números")


def prueba_clasificacion():
    casos = [(("Acción", "Compra", "XMAD", ""), "discrecional"), (("Acción", "Venta", "XMAD", ""), "discrecional"), (("Acción", "Compra", "BATE", ""), "discrecional"),
             (("Acción", "Compra", "XMAD", "plan de compra incentivada"), "plan"), (("Acción", "Entrega de acciones", "XMAD", ""), "plan"),
             (("Acción", "Compra", "Fuera de un centro de negociación", ""), "fuera_mercado"), (("Acción", "Compra", "XOFF", ""), "fuera_mercado"), (("Acción", "Compra", "", ""), "fuera_mercado"),
             (("Opciones sobre acciones", "Compra", "XMAD", ""), "derivado"), (("Derechos de suscripción", "Venta", "XMAD", ""), "derivado"),
             (("Acción", "Herencia", "XMAD", ""), "otro"), (("Acción", "Pignoración", "XMAD", ""), "otro"), (("Shares", "Sale", "XLON", ""), "discrecional"),
             (("Acción", "Suscripción", "XMAD", ""), "otro"), (("Acción", "Ejercicio de opciones", "XMAD", ""), "plan"),
             (("Acción", "Adquisición", "XMAD", "Retribución variable en acciones"), "plan")]
    for (i, o, l, t), esperado in casos:
        r = d._tipo_operacion(i, o, l, t)
        ok(r == esperado, f"clasificación {i}/{o}/{l}/{t!r}: {r} (esperado {esperado})")
    n = {"registro": "1", "fecha_registro": "2026-11-17", "emisor": "B, S.A.", "nif": "A1", "motivo": "directivo", "documento": "u"}
    det = d.leer_notificacion(pdf_texto("X", "CONSEJERO", "B, S.A.", "LEI00000000000000001", [F_COMPRA, F_USD]), "directivo")
    ops = d.operaciones_de(n, det)
    ok(ops[0]["importe_eur"] == 3450.0 and ops[0]["sentido"] == "compra" and ops[0]["tipo"] == "discrecional" and ops[0]["linea"] == 1, f"operaciones: importe en euros: {ops[0]}")
    ok(ops[1]["importe_eur"] is None and ops[1]["divisa"] == "USD" and ops[1]["linea"] == 2, "operaciones: sin importe en euros si la divisa no es EUR")
    ok(set(ops[0]) == set(d.CAMPOS), "operaciones: mismos campos que el CSV")
    # modificación que sustituye a la inicial (caso real de Puig: la inicial decía compra; la modificación, venta)
    ini = d.operaciones_de({"registro": "2026140993", "fecha_registro": "2026-11-03", "emisor": "PUIG BRANDS, S.A.", "nif": "A1", "motivo": "directivo", "documento": "u"},
                           d.leer_notificacion(pdf_texto("X", "CFO", "PUIG BRANDS, S.A.", "", [F_COMPRA]), "directivo"))
    mod = d.operaciones_de({"registro": "2026141576", "fecha_registro": "2026-11-04", "emisor": "PUIG BRANDS, S.A.", "nif": "A1", "motivo": "directivo", "documento": "u"},
                           d.leer_notificacion(pdf_texto("X", "CFO", "PUIG BRANDS, S.A.", "", [F_COMPRA.replace("Compra", "Venta ")], inicial="Modificación"), "directivo"))
    otra = d.operaciones_de({"registro": "2026141000", "fecha_registro": "2026-11-03", "emisor": "OTRA, S.A.", "nif": "A2", "motivo": "directivo", "documento": "u"},
                            d.leer_notificacion(pdf_texto("X", "CFO", "OTRA, S.A.", "", [F_COMPRA]), "directivo"))
    todas = ini + mod + otra
    n = d.marcar_sustituidas(todas)
    ok(n == 1 and ini[0]["sustituida"] == "1" and mod[0]["sustituida"] == "0" and otra[0]["sustituida"] == "0" and mod[0]["sentido"] == "venta", f"sustituidas: la inicial deja de contar: {n} {[o['sustituida'] for o in todas]}")
    res = d.calcular(todas, HOY, {})
    ok(res["totales"]["operaciones"] == 2 and res["totales"]["sustituidas"] == 1 and res["actual"] is None, "calcular: la sustituida no cuenta")
    ok(d.leer_listado(listado(1, 1, [("18/11/2026", "PROSEGUR, COMPA&#209;IA DE SEGURIDAD, S.A.", "A1", "N", "Persona con Responsabilidad de Dirección", "1")]))[0][0]["emisor"] == "PROSEGUR, COMPAÑIA DE SEGURIDAD, S.A.", "listado: entidades HTML resueltas")
    ok(d._tipo_operacion("Acción", "Compra", "XXXX", "") == "fuera_mercado", "clasificación: XXXX es fuera de mercado")


# --------------------------------------------------------------------------- recogida con estado
def prueba_recoger():
    raiz = Path(tempfile.mkdtemp())
    loc = raiz / "local"
    loc.mkdir()
    fixtures(loc)
    salida = raiz / "directivos"
    d.AVISOS.clear()
    rec = d.recoger(salida, HOY, loc, max_documentos=100, dormir=lambda s: None)
    ops = rec["operaciones"]
    ok(rec["descargados"] == 7 and rec["nuevos"] == 7 and rec["fallos"] == 1 and rec["pendientes"] == 1, f"recoger: 7 PDF, 1 pendiente: {{k: v for k, v in rec.items() if k != 'operaciones'}}")
    ok(len(ops) == 8, f"recoger: 8 líneas de operaciones (una notificación con dos filas): {len(ops)}")
    tipos = sorted((o["registro"], o["tipo"]) for o in ops)
    ok(tipos == [("2026145800", "discrecional"), ("2026145800", "discrecional"), ("2026145801", "discrecional"), ("2026145900", "fuera_mercado"), ("2026145901", "derivado"),
                 ("2026146001", "discrecional"), ("2026146002", "discrecional"), ("2026146046", "plan")], f"recoger: tipos: {tipos}")
    csv_txt = (salida / "datos" / "operaciones.csv").read_text(encoding="utf-8")
    ok("NADIE" not in csv_txt and "VALERA" not in csv_txt and "Declarante" not in csv_txt, "recoger: el CSV no lleva nombres")
    pend = d.cargar_pendientes(salida / "datos" / "pendientes.csv")
    ok(list(pend) == ["2026145700"] and pend["2026145700"]["intentos"] == "1", f"recoger: pendiente apuntado: {pend}")
    cob = json.loads((salida / "datos" / "cobertura.json").read_text(encoding="utf-8"))
    ok(cob["desde"] == (HOY - timedelta(days=d.DIAS_RECIENTES)).isoformat() and cob["ultima_pasada"] == HOY.isoformat() and not cob["completo_hasta_inicio"], f"recoger: cobertura: {cob}")
    # segunda pasada: nada nuevo que bajar; el pendiente se reintenta y vuelve a fallar
    rec2 = d.recoger(salida, HOY, loc, max_documentos=100, dormir=lambda s: None)
    ok(rec2["descargados"] == 0 and rec2["nuevos"] == 0 and len(rec2["operaciones"]) == 8, f"recoger: segunda pasada sin descargas: {rec2['descargados']} {rec2['nuevos']}")
    ok(d.cargar_pendientes(salida / "datos" / "pendientes.csv")["2026145700"]["intentos"] == "2", "recoger: el pendiente suma un intento")
    # aparece el PDF del pendiente: se lee y sale de pendientes
    (loc / "doc_2026145700.txt").write_text(pdf_texto("NADIE", "CONSEJERO", "ROTO, S.A.", "", [F_COMPRA]), encoding="utf-8")
    rec3 = d.recoger(salida, HOY, loc, max_documentos=100, dormir=lambda s: None)
    ok(rec3["nuevos"] == 1 and rec3["pendientes"] == 0 and len(rec3["operaciones"]) == 9, f"recoger: pendiente resuelto: {rec3['nuevos']} {rec3['pendientes']}")
    # tope de documentos: con 2 por pasada, la primera pasada deja la ventana reciente incompleta y la cobertura no avanza
    raiz2 = Path(tempfile.mkdtemp())
    loc2 = raiz2 / "local"
    loc2.mkdir()
    fixtures(loc2)
    rec4 = d.recoger(raiz2 / "directivos", HOY, loc2, max_documentos=2, dormir=lambda s: None)
    cob4 = json.loads((raiz2 / "directivos" / "datos" / "cobertura.json").read_text(encoding="utf-8"))
    ok(rec4["descargados"] == 2 and cob4["desde"] is None, f"recoger: con tope, la cobertura no se da por leída: {rec4['descargados']} {cob4}")
    rec5 = d.recoger(raiz2 / "directivos", HOY, loc2, max_documentos=100, dormir=lambda s: None)
    ok(rec5["descargados"] == 5 and len(rec5["operaciones"]) == 8, f"recoger: la pasada siguiente completa la ventana sin repetir: {rec5['descargados']}")
    return salida, loc


def prueba_tramos():
    cob = {}
    tr = d.tramos_pendientes(cob, HOY)
    ok(tr[0] == (HOY - timedelta(days=d.DIAS_RECIENTES), HOY) and tr[1][1] == HOY - timedelta(days=d.DIAS_RECIENTES + 1) and tr[-1][0] == d.INICIO_REGISTRO, f"tramos: desde hoy hacia 2018: {tr[:2]} … {tr[-1]}")
    ok(all(tr[i][0] - timedelta(days=1) == tr[i + 1][1] for i in range(1, len(tr) - 1)), "tramos: contiguos")
    tr2 = d.tramos_pendientes({"desde": "2018-05-01"}, HOY)
    ok(tr2 == [(HOY - timedelta(days=d.DIAS_RECIENTES), HOY)], "tramos: registro completo, solo la ventana reciente")


# --------------------------------------------------------------------------- cálculo
def op(fecha: str, sentido: str, importe: float, nif: str = "A1", tipo: str = "discrecional", registro: str | None = None, cargo: str = "consejero") -> dict:
    return {"registro": registro or fecha.replace("-", "") + sentido[:1] + nif, "linea": 1, "fecha_registro": fecha, "fecha_operacion": fecha, "emisor": f"EMPRESA {nif}, S.A.",
            "nif": nif, "lei": "", "isin": "ES0000000000", "motivo": "directivo", "cargo_tipo": cargo, "instrumento": "Acción",
            "operacion": sentido.capitalize(), "sentido": sentido, "tipo": tipo, "lugar": "XMAD", "volumen": 1.0, "precio": importe, "divisa": "EUR",
            "importe_eur": importe, "modificacion": "0", "documento": "https://www.cnmv.es/x"}


def prueba_calculo():
    # dos años de serie: cada semana 3 compras de 100 € y 1 venta de 50 €, salvo las últimas 13 semanas con 1 compra y 3 ventas
    ops = []
    inicio = date(2024, 11, 18)
    s = inicio
    while s <= HOY:
        ultimas = s > HOY - timedelta(weeks=13)
        for k in range(1 if ultimas else 3):
            ops.append(op(s.isoformat(), "compra", 100.0, nif=f"A{k}", registro=f"{s}c{k}"))
        for k in range(3 if ultimas else 1):
            ops.append(op(s.isoformat(), "venta", 50.0, nif=f"B{k}", registro=f"{s}v{k}"))
        s += timedelta(days=7)
    ops.append(op("2026-11-10", "compra", 999.0, nif="P1", tipo="plan"))   # no cuenta
    serie = d.serie_semanal(ops, HOY)
    ok(serie[0]["semana"] == "2024-11-18" and serie[-1]["semana"] == "2026-11-16" and len(serie) == 105, f"serie: semanas: {serie[0]['semana']} … {serie[-1]['semana']} ({len(serie)})")
    ok(serie[0]["compras_n"] == 3 and serie[0]["ventas_n"] == 1 and serie[0]["neto_eur"] == 250.0 and serie[0]["proporcion_compras"] == 75.0, f"serie: primera semana: {serie[0]}")
    ok(serie[-1]["compras_n"] == 1 and serie[-1]["ventas_n"] == 3 and serie[-1]["proporcion_compras"] == 25.0, f"serie: última semana: {serie[-1]}")
    v = d.ventana_13(serie, len(serie) - 1)
    ok(v == {"compras_n": 13, "ventas_n": 39, "compras_eur": 1300.0, "ventas_eur": 1950.0, "neto_eur": -650.0, "proporcion_compras": 25.0}, f"ventana 13: {v}")
    ok(d.ventana_13(serie, 5) is None, "ventana 13: sin trece semanas, nada")
    res = d.calcular(ops, HOY, {"desde": "2024-11-01"})
    ok(res["actual"] == v and res["percentil_proporcion"] == 0 and res["semanas_de_historia"] == 92, f"calcular: percentil 0 tras 92 ventanas al 75 %: {res['percentil_proporcion']} ({res['semanas_de_historia']})")
    emp = {e["nif"]: e for e in res["empresas_13_semanas"]}
    ok(emp["A0"]["compras_n"] == 13 and emp["A0"]["neto_eur"] == 1300.0 and emp["B1"]["ventas_n"] == 13 and emp["B1"]["neto_eur"] == -650.0, f"calcular: por empresa: {emp.get('A0')} {emp.get('B1')}")
    ok(emp["P1"]["otras_n"] == 1 and emp["P1"]["compras_n"] == 0, "calcular: el plan no entra en el neto pero se cuenta aparte")
    ok(res["mes_anterior"]["desde"] == "2026-10-01" and res["mes_anterior"]["hasta"] == "2026-10-31" and res["mes_anterior"]["compras_n"] == 4, f"calcular: mes anterior: {res['mes_anterior']}")
    h1 = res["huella"]
    ok(h1 == d.calcular(ops, HOY, {"desde": "2024-11-01"})["huella"], "huella: estable")
    ok(h1 != d.calcular(ops + [op("2026-11-17", "compra", 10.0, nif="Z9")], HOY, {})["huella"], "huella: cambia con una operación nueva")
    ok(h1 != d.calcular(ops, HOY + timedelta(days=7), {})["huella"], "huella: cambia al cambiar de semana")
    # agregado por sector propio (cortos/sectores.csv): Repsol y Santander clasificados, el ISIN de relleno queda «sin sector»
    ok(d.SECTORES is not None and len(d.SECTORES) >= 59, "sectores: la tabla sectorial se carga")
    def con_isin(o, isin):
        return dict(o, isin=isin)
    ops_s = ops + [con_isin(op("2026-11-10", "compra", 5000.0, nif="REP", registro="s1"), "ES0173516115"),
                   con_isin(op("2026-11-11", "compra", 3000.0, nif="IBE", registro="s2"), "ES0144580Y14"),
                   con_isin(op("2026-11-12", "venta", 7000.0, nif="SAN", registro="s3"), "ES0113900J37"),
                   con_isin(op("2026-10-20", "compra", 800.0, nif="REP", registro="s4"), "ES0173516115")]
    res_s = d.calcular(ops_s, HOY, {})
    sec = {g["sector"]: g for g in res_s["sectores_13_semanas"]["sectores"]}
    ok(sec["energia-utilities"]["compras_n"] == 3 and sec["energia-utilities"]["empresas"] == 2 and sec["energia-utilities"]["neto_eur"] == 8800.0, f"sectores: energía agrega Repsol e Iberdrola: {sec.get('energia-utilities')}")
    ok(sec["financiero-seguros"]["ventas_n"] == 1 and sec["financiero-seguros"]["neto_eur"] == -7000.0 and sec["financiero-seguros"]["proporcion_compras"] == 0.0, "sectores: financiero con una venta")
    ok("sin-sector" in sec and sec["sin-sector"]["compras_n"] == 13 and res_s["sectores_13_semanas"]["sin_sector"] == ["ES0000000000"], "sectores: el ISIN de relleno va a «sin sector» y se lista")
    ok(res_s["sectores_13_semanas"]["sectores"][0]["sector"] == "energia-utilities", "sectores: ordenados por neto")
    ok(any("sin sector" in a for a in d.AVISOS), "sectores: aviso por emisores sin clasificar")
    ok(res_s["sectores_mes_anterior"]["desde"] == "2026-10-01" and {g["sector"] for g in res_s["sectores_mes_anterior"]["sectores"]} >= {"energia-utilities", "sin-sector"}, "sectores: agregado del mes anterior")
    frag_s = d.fragmento(res_s, HOY.isoformat())
    ok("<h2>Por sector (13 semanas)</h2>" in frag_s and "Energía y utilities" in frag_s and "clasificación propia" in frag_s, "fragmento: tabla por sector")
    rm_s = d.resumen_mensual(res_s)
    ok("Por sectores:" in rm_s and "energía y utilities" in rm_s, f"resumen mensual: frase sectorial: {rm_s[-400:]}")
    ok("Por sectores" not in d.resumen_mensual(d.calcular(ops, HOY, {})) or "sin sector" not in d.resumen_mensual(d.calcular(ops, HOY, {})), "resumen mensual: «sin sector» no protagoniza la frase")
    guardado = d.SECTORES
    d.SECTORES = None
    ok(d.calcular(ops, HOY, {})["sectores_13_semanas"] is None and "Por sector" not in d.fragmento(d.calcular(ops, HOY, {}), HOY.isoformat()), "sectores: sin tabla sectorial no se publica el agregado")
    d.SECTORES = guardado
    # caso de control del percentil contra scipy
    try:
        from scipy import stats
        hist = [75.0] * 92
        ok(d.percentil(25.0, hist) == round(stats.percentileofscore(hist, 25.0, kind="weak")) and d.percentil(75.0, hist) == round(stats.percentileofscore(hist, 75.0, kind="weak")),
           "percentil: coincide con scipy (weak)")
        hist = [10, 20, 30, 40, 50]
        ok(d.percentil(35, hist) == round(stats.percentileofscore(hist, 35, kind="weak")), "percentil: caso de control 2")
    except ImportError:
        print("aviso: scipy no está; caso de control del percentil no ejecutado")
    ok(d.percentil(1.0, []) is None, "percentil: sin historia")
    return ops


def prueba_escribir(ops):
    raiz = Path(tempfile.mkdtemp())
    salida = raiz / "directivos"
    res = d.calcular(ops, HOY, {"desde": "2018-05-01", "completo_hasta_inicio": True})
    ok(d.escribir(res, HOY, salida), "escribir: primera vez")
    frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
    ok(frag.startswith(f"<!-- directivos:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- directivos:fin -->"), "fragmento: marcas")
    ok("13 compras</strong> y <strong>39 ventas</strong>" in frag and "percentil 0 de la serie semanal desde 2024" in frag, "fragmento: frase con percentil")
    ok("<h2>Las empresas con más compra neta" in frag and "Empresa A0" in frag and "Empresa B1" in frag, "fragmento: tablas por empresa con nombre limpio")
    ok("plan de acciones o retribución" in frag and 'rel="nofollow"' in frag, "fragmento: últimas notificaciones con tipo y enlace")
    ok("completo desde el inicio del formulario europeo" in frag and "no es asesoramiento" in frag and "sin predicción" in frag.lower(), "fragmento: método y avisos")
    ok("NADIE" not in frag and "Declarante" not in frag, "fragmento: sin nombres")
    ok('<script type="application/ld+json">' in frag, "fragmento: JSON-LD")
    rm = (salida / "resumen-mensual.html").read_text(encoding="utf-8")
    ok("octubre de 2026" in rm and "4 compras discrecionales" in rm and d.PAGINA_WP in rm, f"resumen mensual: {rm[:200]}")
    j = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
    ok(j["version"] == d.VERSION and j["huella"] == res["huella"] and "serie" not in j and len(j["recientes"]) <= 60 and j["actual"]["compras_n"] == 13, "JSON: versión, huella, sin la serie larga")
    with (salida / "datos" / "serie_semanal.csv").open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    ok(len(filas) == 105 and filas[-1]["proporcion_compras"] == "25.0", "CSV semanal")
    ok(not d.escribir(res, HOY + timedelta(days=1), salida), "escribir: misma huella, no reescribe")
    ok("Comprobado el 18/11/2026" in (salida / "index.html").read_text(encoding="utf-8"), "index.html")


if __name__ == "__main__":
    prueba_listado()
    prueba_pdf()
    prueba_clasificacion()
    prueba_recoger()
    prueba_tramos()
    ops = prueba_calculo()
    prueba_escribir(ops)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
