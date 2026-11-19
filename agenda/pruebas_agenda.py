"""Comprobaciones sin red de la agenda semanal (indicador 15).

  python agenda/pruebas_agenda.py

Datos simulados con valores conocidos (regla 7 del catálogo): cada lector recupera las citas que se
pusieron en respuestas con el formato real de la fuente (INE Tempus3, calendario del BCE, FOMC,
iCalendar de Eurostat, CSV del Tesoro), la ventana es de lunes a domingo, la unión quita duplicados
y ordena, la huella solo cambia si cambian las citas, la memoria de fuentes cubre una caída, y la
escritura no reescribe si la huella no cambia.
"""
from __future__ import annotations

import csv
import importlib
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agenda  # noqa: E402

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 25)          # miércoles: la semana va del lunes 23 al domingo 29


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


# --------------------------------------------------------------------------- datos simulados
def ms(a: int, m: int, d: int, h: int = 8, mi: int = 0) -> int:
    """Milisegundos de época en UTC, como da Tempus3 (el INE publica a las 09:00 de Madrid = 08:00 UTC en invierno)."""
    return int(datetime(a, m, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def ine_json(pid: int, filas: list[tuple[str, int, int, int]]) -> str:
    """Filas (Nombre, Fecha ms, FK_Periodo, Anyo) con la forma exacta de PUBLICACIONFECHA_PUBLICACION."""
    return json.dumps([{"Id": 1000 + i, "FK_Publicacion": pid, "Nombre": n, "Fecha": f, "FK_Periodo": p, "Anyo": a}
                       for i, (n, f, p, a) in enumerate(filas)], ensure_ascii=False)


BCE_HTML = """<html><body><main><div class="title"><h1>Schedules for the meetings of the Governing Council</h1></div>
<div class="definition-list -zebra"><dl>
<dt> \t 25/11/2026 </dt> <dd>         Governing Council of the ECB: non-monetary policy meeting (in Frankfurt)<br> </dd>
<dt> \t 26/11/2026 </dt> <dd>         General Council meeting of the ECB in Frankfurt<br> </dd>
<dt> \t 02/12/2026 </dt> <dd>         Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)<br> </dd>
<dt> \t 03/12/2026 </dt> <dd>         Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference<br> </dd>
<dt> \t 03/02/2027 </dt> <dd>         Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)<br> </dd>
<dt> \t 04/02/2027 </dt> <dd>         Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference<br> </dd>
</dl></div></main></body></html>"""

FED_HTML = """<html><body>
<p><a href="#42828">2026</a> | <a href="#42827">2025</a><br />Future Year: <a href="#45694">2027</a></p>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="42828">2026 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting" ">
  <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>January</strong></div>
  <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">27-28</div>
  <div class="col-xs-12 col-md-4 col-lg-2"><strong>Statement:</strong></div></div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
  <div class="fomc-meeting--shaded fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>November</strong></div>
  <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">24-25*</div></div>
<div class="row fomc-meeting" ">
  <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>December</strong></div>
  <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">8-9*</div></div>
</div>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="42827">2025 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting" ">
  <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>August</strong></div>
  <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">22 (notation vote)</div></div>
</div>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="45694">2027 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting" ">
  <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>Jan/Feb</strong></div>
  <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">31-1</div></div>
</div></body></html>"""

EUROSTAT_ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Eurostat//Release calendar//EN",
    "BEGIN:VEVENT", "DTSTAMP:20261007T095523Z", "DTSTART;VALUE=DATE:20261202",
    "SUMMARY:Flash estimate inflation euro area", "CATEGORIES:Purple Category", "X-THEME:economy",
    "X-CATEGORY:Data release\\,Euro indicators release\\,Statistics Explained", "UID:1@x", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261126", "SUMMARY:Living conditions in Europe – monetary",
    " poverty among the elderly", "X-THEME:population", "X-CATEGORY:News article\\,Statistics Explained", "UID:2@x", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261127", "SUMMARY:Unemployment", "X-THEME:population",
    "X-CATEGORY:Data release\\,Euro indicators release", "UID:3@x", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261127", "SUMMARY:Flash estimate GDP and employment - EU and euro",
    "  area", "X-THEME:economy", "X-CATEGORY:Euro indicators release", "UID:4@x", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261128", "SUMMARY:Producer prices in industry", "X-THEME:industry",
    "X-CATEGORY:Euro indicators release", "UID:5@x", "END:VEVENT",
    "END:VCALENDAR", ""])


def tesoro_csvs(carpeta: Path) -> None:
    for c, cab, filas in (("letras", ["subasta", "plazos_meses", "peticiones_particulares_hasta", "pago_particulares", "emision"],
                           [["2026-11-10", "3 y 9", "2026-11-06", "2026-11-12", "2026-11-13"],
                            ["2026-12-01", "6 y 12", "2026-11-27", "2026-12-03", "2026-12-04"],
                            ["2026-12-09", "3 y 9", "2026-12-04", "2026-12-10", "2026-12-11"]]),
                          ("bonos", ["subasta", "puede_incluir_indexados", "peticiones_particulares_hasta", "pago_particulares", "emision"],
                           [["2026-11-26", "1", "2026-11-25", "2026-11-30", "2026-12-01"],
                            ["2026-12-03", "0", "2026-12-02", "2026-12-07", "2026-12-09"]])):
        d = carpeta / c / "datos"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "proximas_subastas.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cab)
            w.writerows(filas)


def carpeta_local(raiz: Path) -> Path:
    """Respuestas simuladas de todas las fuentes, como las espera --local."""
    loc = raiz / "local"
    loc.mkdir()
    (loc / "ine_8.json").write_text(ine_json(8, [
        ("Índice de Precios de Consumo. Octubre 2026", ms(2026, 11, 13), 10, 2026),
        ("Índice de Precios de Consumo. Avance. Noviembre 2026", ms(2026, 11, 27), 11, 2026),
        ("Índice de Precios de Consumo. Noviembre 2026", ms(2026, 12, 15), 11, 2026),
        ("Índice de Precios de Consumo. Junio 2020", ms(2026, 11, 24, 11, 30), 6, 2020),
    ]), encoding="utf-8")
    (loc / "ine_14.json").write_text(ine_json(14, [("Contabilidad Nacional Trimestral de España. Trimestre 3/2026", ms(2026, 12, 23), 21, 2026)]), encoding="utf-8")
    (loc / "ine_3.json").write_text(ine_json(3, [("Hipotecas Mensual. Septiembre 2026", ms(2026, 11, 25), 9, 2026)]), encoding="utf-8")
    for pid in agenda.INE_PUBLICACIONES:
        if not (loc / f"ine_{pid}.json").exists():
            (loc / f"ine_{pid}.json").write_text("[]", encoding="utf-8")
    (loc / "bce.html").write_text(BCE_HTML, encoding="utf-8")
    (loc / "fed.html").write_text(FED_HTML, encoding="utf-8")
    (loc / "eurostat.ics").write_text(EUROSTAT_ICS, encoding="utf-8")
    return loc


# --------------------------------------------------------------------------- lectores
def prueba_ine():
    desde, hasta = date(2026, 11, 23), date(2027, 1, 31)
    ev = agenda.leer_ine(ine_json(8, [
        ("Índice de Precios de Consumo. Octubre 2026", ms(2026, 11, 13), 10, 2026),
        ("Índice de Precios de Consumo. Avance. Noviembre 2026", ms(2026, 11, 27), 11, 2026),
        ("Índice de Precios de Consumo. Noviembre 2026", ms(2026, 12, 15), 11, 2026),
        ("Índice de Precios de Consumo. Junio 2020", ms(2026, 11, 24, 11, 30), 6, 2020),
    ]), 8, desde, hasta)
    ok([e["fecha"] for e in ev] == ["2026-11-27", "2026-12-15"], f"INE: ventana y periodo antiguo descartado: {[e['fecha'] for e in ev]}")
    ok(ev[0]["titulo"] == "INE: IPC de noviembre de 2026 (avance)", f"INE: título del avance: {ev[0]['titulo']}")
    ok(ev[1]["titulo"] == "INE: IPC de noviembre de 2026", f"INE: título definitivo: {ev[1]['titulo']}")
    ok(ev[0]["hora"] == "09:00" and not ev[0]["hora_habitual"], f"INE: hora de Madrid desde la época UTC: {ev[0]['hora']}")
    ok(ev[0]["peso"] == 1 and ev[0]["fuente"] == "ine" and ev[0]["detalle"] == "" and ev[0]["original"].startswith("Índice de Precios"), "INE: IPC destacado, nombre original aparte")
    ok(any("Junio 2020" in a for a in agenda.AVISOS), "INE: aviso por la fila con periodo muy anterior")
    # verano: 07:00 UTC son las 09:00 de Madrid
    ev = agenda.leer_ine(ine_json(10, [("Índice de Producción Industrial. Mayo 2027", ms(2027, 7, 7, 7), 5, 2027)]), 10, desde, date(2027, 12, 31))
    ok(ev and ev[0]["hora"] == "09:00" and ev[0]["titulo"] == "INE: producción industrial de mayo de 2027", f"INE: horario de verano: {ev}")
    ev = agenda.leer_ine(ine_json(25, [("Z_Avance del PIB trimestral. Trimestre 4/2026", ms(2027, 1, 29), 22, 2026)]), 25, desde, date(2027, 12, 31))
    ok(ev and ev[0]["titulo"] == "INE: avance del PIB trimestral del cuarto trimestre de 2026", f"INE: trimestre sin «(avance)» repetido: {ev[0]['titulo'] if ev else ev}")
    ev = agenda.leer_ine(ine_json(14, [("Contabilidad Nacional Trimestral de España. Trimestre 3/2026", ms(2026, 12, 23), 21, 2026)]), 14, desde, hasta)
    ok(ev[0]["titulo"] == "INE: PIB trimestral (Contabilidad Nacional) del tercer trimestre de 2026", f"INE: trimestre: {ev[0]['titulo']}")
    for malo in ("no es json", '{"a": 1}', '[{"Id": 1}]'):
        try:
            agenda.leer_ine(malo, 8, desde, hasta)
            ok(False, f"INE: respuesta rara aceptada: {malo!r}")
        except agenda.DatosRaros:
            ok(True, "")
    ok(agenda.leer_ine("[]", 8, desde, hasta) == [], "INE: lista vacía, sin citas")


def prueba_bce():
    ev = agenda.leer_bce(BCE_HTML, date(2026, 11, 23), date(2027, 2, 28))
    ok([e["fecha"] for e in ev] == ["2026-12-03", "2027-02-04"], f"BCE: solo el día 2 de las reuniones de política monetaria: {[e['fecha'] for e in ev]}")
    ok(ev[0]["hora"] == "14:15" and ev[0]["hora_habitual"] and ev[0]["peso"] == 1, "BCE: hora habitual y destacada")
    ok(ev[0]["detalle"] == "con rueda de prensa", f"BCE: detalle: {ev[0]['detalle']}")
    ok(agenda.leer_bce(BCE_HTML, date(2026, 11, 23), date(2026, 11, 29)) == [], "BCE: fuera de ventana, nada")
    try:
        agenda.leer_bce("<html><body>sin lista</body></html>", date(2026, 1, 1), date(2027, 1, 1))
        ok(False, "BCE: página sin lista aceptada")
    except agenda.DatosRaros:
        ok(True, "")


def prueba_fed():
    ev = agenda.leer_fed(FED_HTML, date(2026, 11, 23), date(2027, 3, 1))
    ok([e["fecha"] for e in ev] == ["2026-11-25", "2026-12-09", "2027-02-01"], f"Fed: último día de cada reunión, también «31-1» de enero a febrero: {[e['fecha'] for e in ev]}")
    ok(ev[0]["hora"] == "20:00" and ev[0]["hora_habitual"], f"Fed: 14:00 de Washington son las 20:00 de Madrid en noviembre: {ev[0]['hora']}")
    ok(ev[0]["detalle"].startswith("con proyecciones"), f"Fed: asterisco = proyecciones: {ev[0]['detalle']}")
    todos = agenda.leer_fed(FED_HTML, date(2025, 1, 1), date(2027, 12, 31))
    ok(not any(e["fecha"].startswith("2025-08") for e in todos), "Fed: la votación por notación no es una cita")
    ok(any(e["fecha"] == "2026-01-28" and e["detalle"] == "con rueda de prensa" for e in todos), "Fed: reunión sin asterisco, sin proyecciones")
    ev = agenda.leer_fed(FED_HTML.replace("December", "July").replace("8-9*", "28-29"), date(2026, 7, 1), date(2026, 7, 31))
    ok(ev and ev[0]["hora"] == "20:00", f"Fed: en verano también 20:00 (EDT frente a CEST): {ev}")
    try:
        agenda.leer_fed("<html>nada</html>", date(2026, 1, 1), date(2027, 1, 1))
        ok(False, "Fed: página sin bloques aceptada")
    except agenda.DatosRaros:
        ok(True, "")


def prueba_eurostat():
    ev = sorted(agenda.leer_eurostat(EUROSTAT_ICS, date(2026, 11, 23), date(2026, 12, 6)), key=lambda e: (e["fecha"], e["titulo"]))
    titulos = [(e["fecha"], e["titulo"]) for e in ev]
    ok(titulos == [("2026-11-27", "Eurostat: PIB y empleo de la zona euro (estimación preliminar)"), ("2026-11-27", "Eurostat: paro de la zona euro"),
                   ("2026-12-02", "Eurostat: inflación de la zona euro (estimación preliminar)")], f"Eurostat: solo euroindicadores seguidos, línea plegada incluida: {titulos}")
    ok(all(e["hora"] == "11:00" and e["hora_habitual"] for e in ev), "Eurostat: hora habitual 11:00")
    ok([e["peso"] for e in ev] == [1, 2, 1], f"Eurostat: pesos: {[e['peso'] for e in ev]}")
    ok(ev[0]["detalle"] == "" and ev[0]["original"] == "Flash estimate GDP and employment - EU and euro area", f"Eurostat: el título original va aparte: {ev[0]['original']}")
    try:
        agenda.leer_eurostat("<html>no es ics</html>", date(2026, 1, 1), date(2027, 1, 1))
        ok(False, "Eurostat: HTML aceptado como iCalendar")
    except agenda.DatosRaros:
        ok(True, "")
    bloques = agenda._ics_eventos("BEGIN:VEVENT\r\nSUMMARY:a\\, b\\; c\r\n continúa\r\nEND:VEVENT\r\n")
    ok(bloques == [{"SUMMARY": "a, b; ccontinúa"}], f"iCalendar: escapes y plegado (la línea plegada se une sin espacio, RFC 5545): {bloques}")


def prueba_tesoro():
    raiz = Path(tempfile.mkdtemp())
    tesoro_csvs(raiz)
    ev = agenda.leer_tesoro(raiz, date(2026, 11, 23), date(2026, 12, 6))
    ok([(e["fecha"], e["detalle"]) for e in ev] == [("2026-12-01", "a 6 y 12 meses"), ("2026-11-26", "puede incluir indexados"), ("2026-12-03", "")],
       f"Tesoro: subastas de la ventana con su detalle: {[(e['fecha'], e['detalle']) for e in ev]}")
    ok(all(e["peso"] == 2 and e["fuente"] == "tesoro" for e in ev), "Tesoro: peso 2")
    ok(ev[0]["url"] == agenda.PAGINA_LETRAS and ev[1]["url"] == agenda.PAGINA_BONOS, "Tesoro: enlaza a las páginas propias")
    antes = len(agenda.AVISOS)
    ok(agenda.leer_tesoro(raiz / "no_existe", date(2026, 1, 1), date(2027, 1, 1)) == [] and len(agenda.AVISOS) == antes + 2, "Tesoro: sin salidas, aviso por colector")
    ok(agenda.leer_tesoro(None, date(2026, 1, 1), date(2027, 1, 1)) == [], "Tesoro: sin carpeta, nada")


# --------------------------------------------------------------------------- unión, ventana y huella
def prueba_union():
    lunes, domingo, lunes2, domingo2 = agenda.ventana(HOY)
    ok((lunes, domingo, lunes2, domingo2) == (date(2026, 11, 23), date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 6)), f"ventana: {lunes} {domingo} {lunes2} {domingo2}")
    ok(agenda.ventana(date(2026, 11, 29))[0] == date(2026, 11, 23) and agenda.ventana(date(2026, 11, 30))[0] == date(2026, 11, 30), "ventana: el domingo sigue en su semana; el lunes abre otra")
    a = agenda.evento("2026-11-25", "ine", "INE: hipotecas de septiembre de 2026", 2, "u", hora="09:00")
    b = agenda.evento("2026-11-25", "fed", "Reserva Federal: decisión de tipos del FOMC", 1, "u", hora="20:00", hora_habitual=True)
    c = agenda.evento("2026-11-25", "tesoro", "Tesoro: subasta de Bonos y Obligaciones", 2, "u")
    d = agenda.evento("2026-11-24", "eurostat", "Eurostat: paro de la zona euro", 2, "u", hora="11:00", hora_habitual=True)
    fuera = agenda.evento("2026-12-07", "bce", "BCE", 1, "u")
    union = agenda.juntar([[a, b], [c, a], [d, fuera]], lunes, domingo2)
    ok([e["titulo"][:4] for e in union] == ["Euro", "INE:", "Rese", "Teso"], f"unión: sin duplicados, por fecha y hora, las sin hora al final: {[e['titulo'][:4] for e in union]}")
    h1 = agenda.huella(union, lunes)
    ok(h1 == agenda.huella(agenda.juntar([[a, b], [c, a], [d, fuera]], lunes, domingo2), lunes), "huella: estable")
    ok(h1 != agenda.huella(union, lunes2), "huella: cambia al cambiar de semana")
    ok(h1 != agenda.huella(union[:-1], lunes), "huella: cambia si cambian las citas")
    otra = dict(b)
    otra["hora"] = "19:00"
    ok(h1 != agenda.huella(agenda.juntar([[a, otra], [c], [d]], lunes, domingo2), lunes), "huella: cambia si cambia una hora")
    try:
        agenda.evento("2026-13-01", "x", "x", 1, "u")
        ok(False, "evento: fecha imposible aceptada")
    except ValueError:
        ok(True, "")


# --------------------------------------------------------------------------- cálculo completo, memoria y escritura
def prueba_calcular_y_escribir():
    raiz = Path(tempfile.mkdtemp())
    loc = carpeta_local(raiz)
    tesoro_csvs(raiz)
    salida = raiz / "agenda"
    res = agenda.calcular(salida, HOY, raiz, loc)
    fechas = [(e["fecha"], e["fuente"]) for e in res["eventos"]]
    ok(res["semana_inicio"] == "2026-11-23" and res["siguiente_fin"] == "2026-12-06", "calcular: ventana de dos semanas")
    ok(fechas == [("2026-11-25", "ine"), ("2026-11-25", "fed"), ("2026-11-26", "tesoro"), ("2026-11-27", "ine"), ("2026-11-27", "eurostat"), ("2026-11-27", "eurostat"),
                  ("2026-12-01", "tesoro"), ("2026-12-02", "eurostat"), ("2026-12-03", "bce"), ("2026-12-03", "tesoro")], f"calcular: las citas de las dos semanas en orden: {fechas}")
    ok(all(res["fuentes"][f]["estado"] == "leída" for f in ("ine", "bce", "fed", "eurostat")), f"calcular: fuentes leídas: {res['fuentes']}")
    ok(all((salida / "datos" / "fuentes" / f"{f}.json").exists() for f in ("ine", "bce", "fed", "eurostat")), "calcular: memoria de cada fuente guardada")
    guardado = json.loads((salida / "datos" / "fuentes" / "ine.json").read_text(encoding="utf-8"))
    ok(any(e["fecha"] == "2026-12-23" for e in guardado["eventos"]), "memoria: guarda más allá de las dos semanas")

    cambia = agenda.escribir(res, HOY, salida)
    ok(cambia, "escribir: primera vez, datos nuevos")
    frag = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
    ok(frag.startswith(f"<!-- agenda:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- agenda:fin -->"), "fragmento: marcas con huella")
    ok("Semana del 23 al 29 de noviembre de 2026" in frag and "La semana que viene (del 30 de noviembre al 6 de diciembre de 2026)" in frag, "fragmento: rangos de las dos semanas")
    ok("<h3>Lo que marca la semana</h3><ul><li>Miércoles 25: <strong>20:00</strong>" in frag.replace("\n", ""), "fragmento: destacados con día y hora")
    ok("(hora habitual)" in frag and "<strong>09:00</strong> · INE: hipotecas" in frag, "fragmento: hora habitual marcada; la del INE sin marca")
    ok("<h4>Lunes 23 de noviembre</h4>\n<p>Sin citas en la agenda.</p>" in frag, "fragmento: día laborable sin citas")
    ok("Sábado 28" not in frag and "Domingo 29" not in frag, "fragmento: fin de semana sin citas no se lista")
    ok(f'<a href="{agenda.PAGINA_BONOS}">Tesoro: subasta de Bonos y Obligaciones</a>' in frag, "fragmento: el Tesoro enlaza a la página propia")
    ok('<script type="application/ld+json">' in frag and "Dataset" in frag, "fragmento: JSON-LD")
    ok("no es asesoramiento" in frag and "históricamente" in frag and "se moverá" not in frag, "fragmento: marco educativo")
    ok("ine: leída" in frag and "tesoro: leída" in frag, "fragmento: estado de las fuentes")
    bol = (salida / "boletin.html").read_text(encoding="utf-8")
    ok("La agenda de la semana" in bol and "Reserva Federal" in bol and "hipotecas" not in bol and agenda.PAGINA_WP in bol, "boletín: solo destacadas y enlace a la agenda")
    ok("<strong>Viernes 27</strong>: INE: IPC de noviembre de 2026 (avance) (09:00 h)" in bol, f"boletín: línea del IPC: {bol}")
    j = json.loads((salida / "datos" / "eventos.json").read_text(encoding="utf-8"))
    ok(j["version"] == agenda.VERSION and j["huella"] == res["huella"] and len(j["eventos"]) == 10 and j["zona_horaria"] == "Europe/Madrid", "JSON: versión, huella, citas")
    with (salida / "datos" / "eventos.csv").open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    ok(len(filas) == 10 and filas[1]["hora_habitual"] == "1" and filas[0]["hora_habitual"] == "0", "CSV: una fila por cita con la marca de hora habitual")
    ok("<h1>Agenda semanal de los mercados</h1>" in (salida / "index.html").read_text(encoding="utf-8"), "index.html")

    ok(not agenda.escribir(res, HOY + timedelta(days=1), salida), "escribir: misma huella al día siguiente, no reescribe")
    ok(json.loads((salida / "datos" / "eventos.json").read_text(encoding="utf-8"))["fecha_publicacion"] == HOY.isoformat(), "escribir: fecha de publicación conservada")
    ok(agenda.escribir(res, HOY + timedelta(days=1), salida, forzar=True) is False, "escribir: forzado reescribe pero no es dato nuevo")
    res2 = agenda.calcular(salida, HOY + timedelta(days=1), raiz, loc)
    ok(res2["huella"] == res["huella"], "calcular: el jueves, con las mismas fuentes, misma huella")
    res3 = agenda.calcular(salida, date(2026, 11, 30), raiz, loc)
    ok(res3["huella"] != res["huella"] and res3["semana_inicio"] == "2026-11-30", "calcular: el lunes siguiente cambia la semana y la huella")

    # memoria: una fuente que se cae usa la última lectura buena; sin ninguna, se para
    (loc / "fed.html").write_text("<html>caída</html>", encoding="utf-8")
    agenda.AVISOS.clear()
    res4 = agenda.calcular(salida, date(2026, 12, 1), raiz, loc)
    ok(res4["fuentes"]["fed"]["estado"].startswith("última lectura buena, del 2026-11-30"), f"memoria: la Fed cae y se usa la lectura guardada: {res4['fuentes']['fed']}")
    ok([e["fecha"] for e in res4["eventos"] if e["fuente"] == "fed"] == ["2026-12-09"] and any("fed: no responde" in a for a in agenda.AVISOS), "memoria: las citas de la Fed siguen y hay aviso")
    viejo = salida / "datos" / "fuentes" / "fed.json"
    g = json.loads(viejo.read_text(encoding="utf-8"))
    g["consultado"] = (HOY - timedelta(days=agenda.DIAS_CACHE + 1)).isoformat()
    viejo.write_text(json.dumps(g), encoding="utf-8")
    res5 = agenda.calcular(salida, HOY, raiz, loc)
    ok(res5["fuentes"]["fed"]["estado"].startswith("sin datos") and not any(e["fuente"] == "fed" for e in res5["eventos"]), "memoria: lectura demasiado vieja, la fuente sale sin citas")
    for f in ("bce.html", "eurostat.ics"):
        (loc / f).write_text("roto", encoding="utf-8")
    for pid in agenda.INE_PUBLICACIONES:
        (loc / f"ine_{pid}.json").write_text("roto", encoding="utf-8")
    for f in ("ine", "bce", "eurostat", "fed"):
        (salida / "datos" / "fuentes" / f"{f}.json").unlink()
    try:
        agenda.calcular(salida, HOY, raiz, loc)
        ok(False, "sin ninguna fuente externa, se publica igual")
    except agenda.DatosRaros:
        ok(True, "")


def prueba_entorno():
    os.environ["ESPEC_DATOS_BASE"] = "https://datos.elespeculador.com/"
    importlib.reload(agenda)
    ok(agenda.PAGES == "https://datos.elespeculador.com/agenda/", f"PAGES con ESPEC_DATOS_BASE: {agenda.PAGES}")
    del os.environ["ESPEC_DATOS_BASE"]
    importlib.reload(agenda)
    ok(agenda.PAGES.startswith("https://elespeculador-datos.github.io/ifg/"), "sin variable, GitHub Pages")


if __name__ == "__main__":
    prueba_ine()
    prueba_bce()
    prueba_fed()
    prueba_eurostat()
    prueba_tesoro()
    prueba_union()
    prueba_calcular_y_escribir()
    prueba_entorno()
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
