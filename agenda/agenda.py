"""Agenda semanal de catalizadores: las citas de la semana que históricamente concentran la atención del mercado.

Indicador 15 del catálogo de Datos de El Especulador. Junta cinco calendarios públicos y publica
la semana en curso (de lunes a domingo) y la siguiente:

  <salida>/fragmento-wp.html    lo que marca la semana, el día a día y la semana que viene, entre
                                <!-- agenda:inicio HUELLA --> y <!-- agenda:fin -->
  <salida>/boletin.html         bloque corto para el boletín del lunes (Brevo): solo las citas destacadas
  <salida>/index.html           página propia de la salida
  <salida>/datos/eventos.json   las dos semanas, versionado, con el estado de cada fuente
  <salida>/datos/eventos.csv    lo mismo en tabla
  <salida>/datos/fuentes/*.json la última lectura buena de cada fuente (estado del colector)

Fuentes (todas gratuitas y con reutilización verificada; ver LEEME.md):
  - Tesoro Público: calendario de subastas de Letras y de Bonos y Obligaciones, tomado de las salidas
    de letras/ y bonos/ (datos/proximas_subastas.csv) si están al lado de la de este colector.
  - INE: fechas de publicación de las operaciones que siguen los mercados (API Tempus3,
    PUBLICACIONFECHA_PUBLICACION), con la hora que da el propio INE.
  - BCE: calendario de reuniones del Consejo de Gobierno (solo el día de la decisión de política monetaria).
  - Reserva Federal: calendario de reuniones del FOMC (día de la decisión; se marca si hay proyecciones).
  - Eurostat: calendario de difusión (iCalendar), solo los euroindicadores que siguen los mercados.

Reglas: sin predicción ni recomendación; si una fuente falla se usa su última lectura buena (hasta 35
días) y se avisa; si ninguna responde, el colector se para sin publicar. La huella solo cambia cuando
cambian las citas de las dos semanas (o la semana en curso).

Uso:
  python agenda/agenda.py --salida docs/agenda                      descarga y publica
  python agenda/agenda.py --salida docs/agenda --local carpeta       usa respuestas ya descargadas (pruebas)
  python agenda/agenda.py --salida docs/agenda --fecha 2026-11-23    fija el día (pruebas)
  python agenda/agenda.py --salida docs/agenda --tesoro /var/www/datos   carpeta con letras/ y bonos/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

VERSION = "1.0.1"
MADRID = ZoneInfo("Europe/Madrid")
NUEVA_YORK = ZoneInfo("America/New_York")
PAGINA_WP = "https://elespeculador.com/agenda-semanal/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/agenda/"
PAGINA_LETRAS = "https://elespeculador.com/letras-del-tesoro/"
PAGINA_BONOS = "https://elespeculador.com/bonos-y-obligaciones-del-estado/"
CABECERAS = {"User-Agent": "ElEspeculadorAgenda/" + VERSION + " (+https://elespeculador.com; +https://github.com/elespeculador-datos/ifg)"}
DIAS_CACHE = 35          # una lectura antigua de una fuente vale hasta aquí si la fuente no responde
HORIZONTE_DIAS = 14      # dos semanas: la que está en curso y la siguiente

URL_INE = "https://servicios.ine.es/wstempus/js/ES/PUBLICACIONFECHA_PUBLICACION/{id}"
URL_INE_CALENDARIO = "https://www.ine.es/dynt3/Calendario/es/calenHTML.htm"  # la anterior (dyngs/INEbase/es/calendario.htm) da 404 desde noviembre de 2026
URL_BCE = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
URL_FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
URL_EUROSTAT = "https://ec.europa.eu/eurostat/o/calendars/eventsIcal?theme="
URL_EUROSTAT_CALENDARIO = "https://ec.europa.eu/eurostat/web/main/news/release-calendar"
URL_TESORO_CALENDARIO = "https://www.tesoro.es/deuda-publica/subastas/calendario"

# Publicaciones del INE que se siguen: identificador de la publicación en Tempus3 -> (nombre corto, peso).
# Peso 1 = destacada (entra en «lo que marca la semana» y en el boletín); 2 = se lista en el día a día.
INE_PUBLICACIONES = {
    8: ("IPC", 1),
    25: ("avance del PIB trimestral", 1),
    14: ("PIB trimestral (Contabilidad Nacional)", 1),
    15: ("EPA: paro y empleo", 1),
    10: ("producción industrial", 2),
    5: ("comercio al por menor", 2),
    4: ("actividad del sector servicios", 2),
    11: ("precios industriales", 2),
    3: ("hipotecas", 2),
    21: ("precios de la vivienda", 2),
    26: ("cuentas no financieras de hogares y empresas", 2),
}
# Euroindicadores de Eurostat que se siguen: (texto que debe contener el título, en minúsculas; nombre; peso).
# Se comprueban en este orden, así que lo más concreto («flash») va antes que lo general.
EUROSTAT_DESTACADOS = [
    ("flash estimate inflation", "inflación de la zona euro (estimación preliminar)", 1),
    ("inflation (hicp)", "inflación de la zona euro (IPCA definitivo)", 2),
    ("flash estimate gdp", "PIB y empleo de la zona euro (estimación preliminar)", 1),
    ("gdp and employment", "PIB y empleo de la zona euro", 2),
    ("unemployment", "paro de la zona euro", 2),
    ("industrial production", "producción industrial de la zona euro", 2),
    ("retail trade", "comercio al por menor de la zona euro", 2),
]
# Horas habituales (hora de Madrid) que no vienen en el calendario de la fuente: se publican como
# «hora habitual», nunca como dato de la cita. Comprobadas el 18/11/2026: el BCE publica las decisiones
# a las 14:15 CET y empieza la rueda de prensa a las 14:45 (nota de prensa del 27/06/2022); Eurostat
# difunde sus primeras publicaciones a las 11:00 CET (protocolo de imparcialidad); la Fed publica el
# comunicado del FOMC «for release at 2:00 p.m.» hora de Washington (cabecera de cada comunicado).
# La hora del INE la da la propia API (época en milisegundos) y se convierte a Madrid.
HORA_HABITUAL = {"bce": "14:15", "eurostat": "11:00"}
HORA_FED_LOCAL = (14, 0)
AVISOS: list[str] = []
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MESES_EN = {m[:3]: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                                  "september", "october", "november", "december"])}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class DatosRaros(Exception):
    """Ninguna fuente responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga
def _get(url: str, esperas: list[int] | None = None, dormir=time.sleep) -> str:
    """Descarga con reintentos crecientes. Devuelve el texto o lanza DatosRaros."""
    esperas = [10, 30, 60] if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(url, headers=CABECERAS, timeout=(20, 90))
            if r.status_code == 200 and r.text.strip():
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres"
        except requests.RequestException as e:
            ultimo = str(e)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar {url}: {ultimo}")


# --------------------------------------------------------------------------- lectores (texto -> eventos)
# Un evento es un diccionario con: fecha (AAAA-MM-DD), hora (HH:MM de Madrid o None), hora_habitual (bool),
# fuente, titulo, detalle (lo que añade la fuente: plazos, proyecciones...), original (el texto de la fuente),
# peso (1 destacada, 2 normal), url.
def evento(fecha: str, fuente: str, titulo: str, peso: int, url: str, hora: str | None = None,
           hora_habitual: bool = False, detalle: str = "", original: str = "") -> dict:
    date.fromisoformat(fecha)
    return {"fecha": fecha, "hora": hora, "hora_habitual": bool(hora and hora_habitual), "fuente": fuente,
            "titulo": titulo, "detalle": detalle, "original": original, "peso": int(peso), "url": url}


def _periodo_ine(nombre: str) -> tuple[str, bool]:
    """«Índice de Precios de Consumo. Avance. Noviembre 2026» -> («de noviembre de 2026», True)."""
    partes = [p.strip() for p in nombre.split(".") if p.strip()]
    avance = any(p.lower() == "avance" for p in partes)
    ultimo = partes[-1] if partes else ""
    m = re.fullmatch(r"([A-Za-zÁÉÍÓÚáéíóú]+)\s+(\d{4})", ultimo)
    if m and m.group(1).lower() in MESES:
        return f"de {m.group(1).lower()} de {m.group(2)}", avance
    m = re.fullmatch(r"Trimestre\s+([1-4])/(\d{4})", ultimo)
    if m:
        return f"del {'primer segundo tercer cuarto'.split()[int(m.group(1)) - 1]} trimestre de {m.group(2)}", avance
    m = re.fullmatch(r"(\d{4})", ultimo)
    if m:
        return f"de {m.group(1)}", avance
    return f"({ultimo})" if ultimo else "", avance


def leer_ine(texto: str, publicacion: int, desde: date, hasta: date) -> list[dict]:
    """Fechas de publicación de una publicación del INE (JSON de Tempus3) dentro de la ventana."""
    try:
        filas = json.loads(texto)
    except json.JSONDecodeError as e:
        raise DatosRaros(f"INE, publicación {publicacion}: la respuesta no es JSON ({e})")
    if not isinstance(filas, list) or (filas and not isinstance(filas[0], dict)):
        raise DatosRaros(f"INE, publicación {publicacion}: la respuesta no es una lista de fechas")
    nombre, peso = INE_PUBLICACIONES[publicacion]
    out = []
    for f in filas:
        if "Fecha" not in f or "Nombre" not in f:
            raise DatosRaros(f"INE, publicación {publicacion}: falta Fecha o Nombre en {str(f)[:120]}")
        t = datetime.fromtimestamp(int(f["Fecha"]) / 1000, tz=timezone.utc).astimezone(MADRID)
        if not desde <= t.date() <= hasta:
            continue
        if f.get("Anyo") and t.year - int(f["Anyo"]) > 1:
            AVISOS.append(f"INE, publicación {publicacion}: se ignora «{f['Nombre']}» fechada el {t.date().isoformat()} (periodo muy anterior)")
            continue
        periodo, avance = _periodo_ine(str(f["Nombre"]))
        titulo = f"INE: {nombre} {periodo}".rstrip() + (" (avance)" if avance and "avance" not in nombre.lower() else "")
        out.append(evento(t.date().isoformat(), "ine", titulo, peso, URL_INE_CALENDARIO, hora=t.strftime("%H:%M"),
                          original=str(f["Nombre"])))
    return out


def leer_bce(html: str, desde: date, hasta: date) -> list[dict]:
    """Reuniones del Consejo de Gobierno del BCE: solo el día de la decisión de política monetaria."""
    pares = re.findall(r"<dt>\s*(\d{2})/(\d{2})/(\d{4})\s*</dt>\s*<dd>(.*?)</dd>", html, re.S)
    if not pares:
        raise DatosRaros("BCE: el calendario no tiene la lista de fechas esperada (<dt>dd/mm/aaaa</dt>)")
    out = []
    for d, m, a, texto in pares:
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto)).strip()
        bajo = texto.lower()
        if "monetary policy meeting" not in bajo or "non-monetary" in bajo:
            continue
        if "day 1" in bajo and "press conference" not in bajo:
            continue
        fecha = f"{a}-{m}-{d}"
        if not desde <= date.fromisoformat(fecha) <= hasta:
            continue
        detalle = "con rueda de prensa" if "press conference" in bajo else ""
        out.append(evento(fecha, "bce", "BCE: decisión de tipos de interés del Consejo de Gobierno", 1, URL_BCE,
                          hora=HORA_HABITUAL["bce"], hora_habitual=True, detalle=detalle, original=texto))
    return out


def leer_fed(html: str, desde: date, hasta: date) -> list[dict]:
    """Reuniones del FOMC: el día de la decisión (el último de la reunión); con proyecciones si lleva asterisco."""
    bloques = re.findall(r'<a id="\d+">(\d{4}) FOMC Meetings</a>(.*?)(?=<a id="\d+">\d{4} FOMC Meetings</a>|\Z)', html, re.S)
    if not bloques:
        raise DatosRaros("Fed: la página no tiene los bloques «AAAA FOMC Meetings» esperados")
    out = []
    for anio, cuerpo in bloques:
        reuniones = re.findall(r'fomc-meeting__month[^>]*>\s*(?:<strong>)?\s*([A-Za-z/]+)\s*(?:</strong>)?\s*</div>\s*'
                               r'<div class="fomc-meeting__date[^>]*>\s*([^<]+?)\s*</div>', cuerpo)
        for mes_txt, dias_txt in reuniones:
            meses = [MESES_EN[x.strip().lower()[:3]] for x in mes_txt.split("/") if x.strip().lower()[:3] in MESES_EN]
            if not meses:
                continue
            nums = [int(x) for x in re.findall(r"\d{1,2}", dias_txt)]
            if not nums:
                continue
            proyecciones = "*" in dias_txt
            if "notation vote" in dias_txt.lower():
                continue
            dia = nums[-1]
            mes = meses[-1] if len(meses) > 1 else meses[0]
            if len(meses) == 1 and len(nums) > 1 and nums[-1] < nums[0]:
                mes = mes % 12 + 1   # «31-1»: la reunión acaba el mes siguiente
            try:
                fecha = date(int(anio), mes, dia)
            except ValueError:
                continue
            if not desde <= fecha <= hasta:
                continue
            local = datetime(fecha.year, fecha.month, fecha.day, *HORA_FED_LOCAL, tzinfo=NUEVA_YORK).astimezone(MADRID)
            detalle = "con proyecciones económicas y rueda de prensa" if proyecciones else "con rueda de prensa"
            out.append(evento(fecha.isoformat(), "fed", "Reserva Federal: decisión de tipos del FOMC", 1, URL_FED,
                              hora=local.strftime("%H:%M"), hora_habitual=True, detalle=detalle,
                              original=f"{anio} FOMC meeting {mes_txt} {dias_txt.strip()}"))
    return out


def _ics_eventos(texto: str) -> list[dict]:
    """Bloques VEVENT de un iCalendar, con las líneas desplegadas y los escapes resueltos."""
    lineas: list[str] = []
    for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linea[:1] in (" ", "\t") and lineas:
            lineas[-1] += linea[1:]
        else:
            lineas.append(linea)
    out, actual = [], None
    for linea in lineas:
        if linea == "BEGIN:VEVENT":
            actual = {}
        elif linea == "END:VEVENT":
            if actual is not None:
                out.append(actual)
            actual = None
        elif actual is not None and ":" in linea:
            clave, valor = linea.split(":", 1)
            nombre = clave.split(";")[0].upper()
            valor = valor.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").replace("\\\\", "\\")
            actual[nombre] = valor
            if nombre == "DTSTART":
                actual["_params"] = clave
    return out


def leer_eurostat(texto: str, desde: date, hasta: date) -> list[dict]:
    """Euroindicadores del calendario de difusión de Eurostat (iCalendar) dentro de la ventana."""
    if "BEGIN:VCALENDAR" not in texto:
        raise DatosRaros("Eurostat: la respuesta no es un iCalendar")
    out = []
    for ev in _ics_eventos(texto):
        if "euro indicators release" not in ev.get("X-CATEGORY", "").lower():
            continue
        m = re.match(r"(\d{4})(\d{2})(\d{2})", ev.get("DTSTART", ""))
        if not m:
            continue
        fecha = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if not desde <= fecha <= hasta:
            continue
        resumen = ev.get("SUMMARY", "").strip()
        bajo = resumen.lower()
        for patron, nombre, peso in EUROSTAT_DESTACADOS:
            if patron in bajo:
                out.append(evento(fecha.isoformat(), "eurostat", f"Eurostat: {nombre}", peso, URL_EUROSTAT_CALENDARIO,
                                  hora=HORA_HABITUAL["eurostat"], hora_habitual=True, original=resumen))
                break
    return out


def leer_tesoro(carpeta: Path | None, desde: date, hasta: date) -> list[dict]:
    """Subastas del calendario del Tesoro, de las salidas de letras/ y bonos/ (CSV de próximas subastas)."""
    out = []
    if carpeta is None:
        return out
    for colector, titulo, pagina in (("letras", "Tesoro: subasta de Letras", PAGINA_LETRAS),
                                     ("bonos", "Tesoro: subasta de Bonos y Obligaciones", PAGINA_BONOS)):
        ruta = carpeta / colector / "datos" / "proximas_subastas.csv"
        if not ruta.exists():
            AVISOS.append(f"No está {ruta}: la agenda sale sin las subastas de {colector}")
            continue
        with ruta.open(encoding="utf-8", newline="") as fh:
            filas = list(csv.DictReader(fh))
        if not filas or "subasta" not in filas[0]:
            AVISOS.append(f"{ruta} no tiene la columna «subasta»: se ignora")
            continue
        for f in filas:
            try:
                fecha = date.fromisoformat(f["subasta"])
            except ValueError:
                continue
            if not desde <= fecha <= hasta:
                continue
            detalle = ""
            if colector == "letras" and f.get("plazos_meses"):
                detalle = f"a {f['plazos_meses']} meses"
            elif colector == "bonos":
                detalle = "puede incluir indexados" if str(f.get("puede_incluir_indexados", "")).strip() in ("1", "True", "true") else ""
            out.append(evento(fecha.isoformat(), "tesoro", titulo, 2, pagina, detalle=detalle,
                              original=f"calendario del Tesoro {f.get('subasta')} ({colector})"))
    return out


# --------------------------------------------------------------------------- fuentes con memoria
def _cache(carpeta: Path, fuente: str) -> Path:
    return carpeta / "datos" / "fuentes" / f"{fuente}.json"


def con_memoria(salida: Path, fuente: str, hoy: date, leer, descargar) -> tuple[list[dict], dict]:
    """Lee la fuente; si falla, recupera la última lectura buena (hasta DIAS_CACHE) y avisa.

    Devuelve (eventos de toda la lectura, estado de la fuente). Los eventos guardados cubren el horizonte
    completo de la lectura, así la ventana se puede recortar después con cualquier fecha.
    """
    ruta = _cache(salida, fuente)
    try:
        eventos = leer(descargar())
        estado = {"estado": "leída", "consultado": hoy.isoformat(), "eventos": len(eventos)}
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"fuente": fuente, "consultado": hoy.isoformat(), "eventos": eventos},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        return eventos, estado
    except (DatosRaros, requests.RequestException, ValueError, KeyError) as e:
        motivo = str(e)[:300]
    if ruta.exists():
        guardado = json.loads(ruta.read_text(encoding="utf-8"))
        consultado = date.fromisoformat(guardado["consultado"])
        edad = (hoy - consultado).days
        if edad <= DIAS_CACHE:
            AVISOS.append(f"{fuente}: no responde ({motivo}); se usa la lectura del {consultado.isoformat()}")
            return guardado["eventos"], {"estado": f"última lectura buena, del {consultado.isoformat()}",
                                          "consultado": consultado.isoformat(), "eventos": len(guardado["eventos"])}
    AVISOS.append(f"{fuente}: no responde ({motivo}) y no hay lectura reciente guardada; la agenda sale sin esta fuente")
    return [], {"estado": "sin datos: " + motivo, "consultado": None, "eventos": 0}


# --------------------------------------------------------------------------- cálculo
def ventana(hoy: date) -> tuple[date, date, date, date]:
    """Lunes y domingo de la semana en curso y de la siguiente."""
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes, lunes + timedelta(days=6), lunes + timedelta(days=7), lunes + timedelta(days=13)


def juntar(listas: list[list[dict]], desde: date, hasta: date) -> list[dict]:
    """Une, recorta a la ventana, quita duplicados y ordena por fecha, hora (las sin hora al final) y peso."""
    vistos, out = set(), []
    for lista in listas:
        for e in lista:
            if not desde <= date.fromisoformat(e["fecha"]) <= hasta:
                continue
            clave = (e["fecha"], e["fuente"], e["titulo"])
            if clave in vistos:
                continue
            vistos.add(clave)
            out.append(dict(e))
    return sorted(out, key=lambda e: (e["fecha"], e["hora"] is None, e["hora"] or "", e["peso"], e["titulo"]))


def huella(eventos: list[dict], lunes: date) -> str:
    base = {"semana": lunes.isoformat(), "version": VERSION,
            "eventos": [[e["fecha"], e["hora"], e["fuente"], e["titulo"], e["detalle"], e["peso"]] for e in eventos]}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _dia(d: date) -> str:
    return f"{DIAS[d.weekday()].capitalize()} {d.day}"


def _rango(a: date, b: date) -> str:
    if a.month == b.month:
        return f"del {a.day} al {b.day} de {MESES[b.month - 1]} de {b.year}"
    if a.year == b.year:
        return f"del {a.day} de {MESES[a.month - 1]} al {b.day} de {MESES[b.month - 1]} de {b.year}"
    return f"del {a.day} de {MESES[a.month - 1]} de {a.year} al {b.day} de {MESES[b.month - 1]} de {b.year}"


def _html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _linea(e: dict, con_dia: bool = False) -> str:
    hora = ""
    if e["hora"]:
        hora = f"<strong>{e['hora']}</strong>" + (" <span class=\"has-small-font-size\">(hora habitual)</span>" if e["hora_habitual"] else "") + " · "
    dia = f"{_dia(date.fromisoformat(e['fecha']))}: " if con_dia else ""
    detalle = f" <span class=\"has-small-font-size\">({_html(e['detalle'])})</span>" if e["detalle"] else ""
    titulo = _html(e["titulo"])
    if e["fuente"] == "tesoro":
        titulo = f'<a href="{e["url"]}">{titulo}</a>'
    return f"<li>{dia}{hora}{titulo}{detalle}</li>"


def fragmento(res: dict, fecha_pub: str) -> str:
    lunes, domingo = date.fromisoformat(res["semana_inicio"]), date.fromisoformat(res["semana_fin"])
    lunes2, domingo2 = date.fromisoformat(res["siguiente_inicio"]), date.fromisoformat(res["siguiente_fin"])
    semana = [e for e in res["eventos"] if e["fecha"] <= res["semana_fin"]]
    siguiente = [e for e in res["eventos"] if e["fecha"] > res["semana_fin"]]
    destacados = [e for e in semana if e["peso"] == 1]
    partes = [f"<!-- agenda:inicio {res['huella']} -->",
              f'<p class="has-small-font-size">Semana {_rango(lunes, domingo)}. Actualizado el {_f(fecha_pub)}. Horas de Madrid.</p>',
              "<h3>Lo que marca la semana</h3>"]
    if destacados:
        partes.append("<ul>" + "".join(_linea(e, con_dia=True) for e in destacados) + "</ul>")
    else:
        partes.append("<p>Esta semana no hay ninguna de las citas destacadas (IPC, PIB, EPA, BCE, Reserva Federal, "
                      "inflación de la zona euro). Abajo, el resto de la agenda.</p>")
    partes.append("<h3>Día a día</h3>")
    for i in range(7):
        d = lunes + timedelta(days=i)
        del_dia = [e for e in semana if e["fecha"] == d.isoformat()]
        if not del_dia and d.weekday() >= 5:
            continue
        partes.append(f"<h4>{_dia(d)} de {MESES[d.month - 1]}</h4>")
        partes.append("<ul>" + "".join(_linea(e) for e in del_dia) + "</ul>" if del_dia else "<p>Sin citas en la agenda.</p>")
    partes.append(f"<h3>La semana que viene ({_rango(lunes2, domingo2)})</h3>")
    if siguiente:
        partes.append("<ul>" + "".join(_linea(e, con_dia=True) for e in siguiente) + "</ul>")
    else:
        partes.append("<p>Todavía sin citas en los calendarios consultados.</p>")
    fuentes = res["fuentes"]
    estado = "; ".join(f"{n}: {v['estado']}" for n, v in fuentes.items())
    partes.append('<h3 id="metodo">Qué es esta agenda y de dónde sale</h3>'
                  "<p>Reúne, para la semana en curso y la siguiente, las citas públicas que históricamente concentran la atención "
                  "de los mercados españoles: subastas del Tesoro, publicaciones del INE, decisiones de tipos del BCE y de la "
                  "Reserva Federal y los euroindicadores de Eurostat. Las citas destacadas son las que, en el histórico, más "
                  "atención reciben: IPC, PIB, EPA, las dos decisiones de tipos y la inflación de la zona euro. No es una lista "
                  "exhaustiva ni una previsión: recoge fechas publicadas por cada organismo, sin opinar sobre lo que pasará. "
                  "Las horas marcadas como «habitual» son las que cada organismo usa de ordinario y no vienen en su calendario; "
                  "las del INE las da el propio INE.</p>"
                  f'<p class="has-small-font-size">Fuentes: Tesoro Público (<a href="{URL_TESORO_CALENDARIO}">calendario de subastas</a>, '
                  f'a través de las páginas de Letras y de Bonos de El Especulador); INE (<a href="{URL_INE_CALENDARIO}">calendario de '
                  f'publicaciones</a>, API Tempus3, licencia CC BY 4.0: «Elaboración propia con datos extraídos del sitio web del INE: '
                  f'www.ine.es»); BCE (<a href="{URL_BCE}">calendario del Consejo de Gobierno</a>); Reserva Federal '
                  f'(<a href="{URL_FED}">calendario del FOMC</a>); Eurostat (<a href="{URL_EUROSTAT_CALENDARIO}">calendario de difusión</a>). '
                  f"Estado de cada fuente en esta pasada: {_html(estado)}. La selección y la redacción son de El Especulador "
                  f"(CC BY 4.0). Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>")
    partes.append("<!-- agenda:fin -->")
    return "\n".join(partes)


def boletin(res: dict) -> str:
    """Bloque corto para el boletín del lunes: las citas destacadas de la semana y un enlace a la agenda completa."""
    lunes, domingo = date.fromisoformat(res["semana_inicio"]), date.fromisoformat(res["semana_fin"])
    semana = [e for e in res["eventos"] if e["fecha"] <= res["semana_fin"]]
    destacados = [e for e in semana if e["peso"] == 1] or semana[:5]
    lineas = []
    for e in destacados:
        hora = f" ({e['hora']}{' h, hora habitual' if e['hora_habitual'] else ' h'})" if e["hora"] else ""
        lineas.append(f"<li><strong>{_dia(date.fromisoformat(e['fecha']))}</strong>: {_html(e['titulo'])}{hora}</li>")
    cuerpo = "<ul>" + "".join(lineas) + "</ul>" if lineas else "<p>Semana sin citas destacadas en los calendarios públicos.</p>"
    return (f"<p><strong>La agenda de la semana</strong> ({_rango(lunes, domingo)}, horas de Madrid)</p>\n{cuerpo}\n"
            f'<p><a href="{PAGINA_WP}">Agenda completa, día a día</a> · Contenido informativo; no es asesoramiento financiero.</p>\n')


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Agenda semanal de catalizadores de los mercados españoles (El Especulador)",
        "description": "Citas públicas de la semana en curso y la siguiente: subastas del Tesoro, publicaciones del INE, "
                       "decisiones de tipos del BCE y de la Reserva Federal y euroindicadores de Eurostat, con fecha y hora.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de los calendarios del Tesoro Público, el INE, el BCE, la Reserva Federal y Eurostat",
        "license": "https://creativecommons.org/licenses/by/4.0/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/eventos.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/eventos.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    """Escribe los ficheros de salida. Si la huella no cambia y no se fuerza, no toca nada."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "eventos.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    cambia = antes.get("huella") != res["huella"]
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "boletin.html", "datos/eventos.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    with (dd / "eventos.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "hora_madrid", "hora_habitual", "fuente", "titulo", "detalle", "original", "peso", "url"])
        for e in res["eventos"]:
            w.writerow([e["fecha"], e["hora"] or "", "1" if e["hora_habitual"] else "0", e["fuente"], e["titulo"], e["detalle"],
                        e.get("original", ""), e["peso"], e["url"]])
    previo.write_text(json.dumps({
        "version": VERSION, "fecha_publicacion": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "huella": res["huella"], "semana_inicio": res["semana_inicio"], "semana_fin": res["semana_fin"],
        "siguiente_inicio": res["siguiente_inicio"], "siguiente_fin": res["siguiente_fin"],
        "zona_horaria": "Europe/Madrid", "eventos": res["eventos"], "fuentes": res["fuentes"],
        "fuente": "Tesoro Público (calendario de subastas), INE (API Tempus3), BCE (calendario del Consejo de Gobierno), "
                  "Reserva Federal (calendario del FOMC), Eurostat (calendario de difusión)",
        "condiciones": "Fechas publicadas por cada organismo, reproducidas sin modificar; las horas marcadas como habituales "
                       "no vienen en el calendario de la fuente. Selección y textos de El Especulador (CC BY 4.0). "
                       "Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- agenda:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    (salida / "boletin.html").write_text(boletin(res), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agenda semanal de los mercados: Tesoro, INE, BCE, Fed y Eurostat | El Especulador</title>
<meta name="description" content="Las citas de la semana que históricamente concentran la atención de los mercados españoles: subastas del Tesoro, IPC, PIB y EPA del INE, decisiones del BCE y de la Reserva Federal y euroindicadores de Eurostat.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:900px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h3{{font-size:1.15rem;margin-top:1.6em}} h4{{margin:1em 0 .2em}} ul{{margin:.2em 0 .6em}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Agenda semanal de los mercados</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/eventos.csv">las citas de las dos semanas</a> · <a href="datos/eventos.json">JSON</a>. Fechas publicadas por el Tesoro Público, el INE, el BCE, la Reserva Federal y Eurostat; selección y textos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def calcular(salida: Path, hoy: date, tesoro: Path | None, local: Path | None = None) -> dict:
    """Lee todas las fuentes (o la carpeta --local) y devuelve el resultado listo para escribir."""
    lunes, domingo, lunes2, domingo2 = ventana(hoy)
    desde, hasta = lunes, lunes + timedelta(days=HORIZONTE_DIAS * 4)   # se guarda de sobra; la ventana se recorta luego

    def fichero(nombre: str):
        def _leer():
            ruta = local / nombre
            if not ruta.exists():
                raise DatosRaros(f"falta {ruta}")
            return ruta.read_text(encoding="utf-8")
        return _leer

    def ine_todas(_: str | None = None) -> list[dict]:
        out = []
        for pid in INE_PUBLICACIONES:
            texto = fichero(f"ine_{pid}.json")() if local else _get(URL_INE.format(id=pid))
            out.extend(leer_ine(texto, pid, desde, hasta))
        return out

    fuentes_def = [
        ("ine", lambda t: ine_todas(), lambda: ""),
        ("bce", lambda t: leer_bce(t, desde, hasta), fichero("bce.html") if local else (lambda: _get(URL_BCE))),
        ("fed", lambda t: leer_fed(t, desde, hasta), fichero("fed.html") if local else (lambda: _get(URL_FED))),
        ("eurostat", lambda t: leer_eurostat(t, desde, hasta), fichero("eurostat.ics") if local else (lambda: _get(URL_EUROSTAT))),
    ]
    listas, estados = [], {}
    tes = leer_tesoro(tesoro, desde, hasta)
    listas.append(tes)
    estados["tesoro"] = {"estado": "leída de las páginas de Letras y Bonos" if tes else "sin subastas en la ventana o sin salidas de letras/ y bonos/",
                         "consultado": hoy.isoformat(), "eventos": len(tes)}
    for nombre, leer, descargar in fuentes_def:
        ev, estado = con_memoria(salida, nombre, hoy, leer, descargar)
        listas.append(ev)
        estados[nombre] = estado
    eventos = juntar(listas, lunes, domingo2)
    leidas = [n for n, v in estados.items() if v["estado"].startswith("leída") or v["estado"].startswith("última")]
    if not any(n in leidas for n in ("ine", "bce", "fed", "eurostat")):
        raise DatosRaros("Ninguna fuente externa responde y no hay lecturas guardadas: no se publica la agenda")
    return {"semana_inicio": lunes.isoformat(), "semana_fin": domingo.isoformat(), "siguiente_inicio": lunes2.isoformat(),
            "siguiente_fin": domingo2.isoformat(), "eventos": eventos, "fuentes": estados, "huella": huella(eventos, lunes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="carpeta con respuestas ya descargadas: ine_<id>.json, bce.html, fed.html, eurostat.ics (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en Madrid)")
    ap.add_argument("--tesoro", help="carpeta que contiene letras/ y bonos/ (por defecto, la carpeta madre de --salida)")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie (tras cambiar el código)")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(MADRID).date()
    salida = Path(a.salida)
    res = calcular(salida, hoy, Path(a.tesoro) if a.tesoro else salida.resolve().parent, Path(a.local) if a.local else None)
    cambia = escribir(res, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    n_sem = sum(1 for e in res["eventos"] if e["fecha"] <= res["semana_fin"])
    print(f"Semana del {res['semana_inicio']}: {n_sem} citas ({sum(1 for e in res['eventos'] if e['fecha'] <= res['semana_fin'] and e['peso'] == 1)} destacadas); "
          f"semana siguiente: {len(res['eventos']) - n_sem}. Fuentes: " + ", ".join(f"{k} {v['eventos']}" for k, v in res["fuentes"].items())
          + f". {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
