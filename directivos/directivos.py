"""Compras y ventas de directivos: lo que comunican a la CNMV quienes mejor conocen la empresa.

Indicador 10 del catálogo de Datos de El Especulador. Lee el registro de la CNMV de notificaciones de
operaciones de administradores, directivos y personas vinculadas (artículo 19 del Reglamento (UE)
596/2014 y Reglamento de Ejecución (UE) 2016/523): el listado por fechas y el PDF estándar de cada
notificación. Guarda cada operación SIN el nombre del declarante (solo emisor, motivo de la notificación,
tipo de cargo, operación y número de registro: el documento público queda enlazado) y publica:

  <salida>/fragmento-wp.html          lectura de las últimas 13 semanas, empresas con más compra y más
                                      venta neta, operaciones recientes y método, entre
                                      <!-- directivos:inicio HUELLA --> y <!-- directivos:fin -->
  <salida>/resumen-mensual.html       bloque corto del mes (agregado, sin empresas): el anzuelo gratuito
  <salida>/index.html                 página propia de la salida
  <salida>/datos/ultima.json          resumen versionado (13 semanas por empresa, serie semanal, estado)
  <salida>/datos/operaciones.csv      todas las operaciones leídas (estado del colector; sin nombres)
  <salida>/datos/serie_semanal.csv    compras y ventas discrecionales por semana desde el primer dato
  <salida>/datos/cobertura.json       qué tramo de fechas del registro se ha leído ya
  <salida>/datos/pendientes.csv       notificaciones cuyo PDF no se pudo leer (se reintentan)

Qué cuenta como «discrecional»: acciones (no derivados ni derechos), compra o venta (no entregas,
canjes, herencias, préstamos ni pignoraciones), en un centro de negociación (no «fuera de mercado») y sin
que la notificación diga que viene de un plan de retribución, de incentivos o de compra para empleados.
Lo demás se guarda con su tipo y no entra en el neto. El criterio es declarado y revisable.

Cada pasada lee los últimos DIAS_RECIENTES días (las notificaciones llegan con retraso) y, si queda
tramo por leer hacia atrás hasta INICIO_REGISTRO, sigue rellenando hasta MAX_DOCUMENTOS por pasada.
Sin predicción ni recomendación. Fuente gratuita en cnmv.es (hay que decirlo en cualquier producto de pago).

Uso:
  python directivos/directivos.py --salida docs/directivos                   pasada normal
  python directivos/directivos.py --salida docs/directivos --local carpeta    pruebas con respuestas guardadas
  python directivos/directivos.py --salida docs/directivos --max-documentos 50
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_mod
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

VERSION = "1.1.2"
PAGINA_WP = "https://elespeculador.com/compras-y-ventas-de-directivos/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/directivos/"
URL_LISTADO = "https://www.cnmv.es/portal/consultas/directivos-resultado.aspx"
URL_REGISTRO = "https://www.cnmv.es/portal/consultas/directivos-consulta?lang=es"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos; +https://elespeculador.com)", "Accept-Language": "es-ES,es;q=0.9"}
INICIO_REGISTRO = date(2018, 5, 1)   # desde aquí el registro usa el formulario del Reglamento 2016/523
DIAS_RECIENTES = 21                  # ventana que se relee en cada pasada (las notificaciones llegan tarde)
MAX_DOCUMENTOS = 300                 # PDF por pasada (relleno gradual hacia atrás)
TRAMO_DIAS = 45                      # tamaño de cada tramo del relleno
PAUSA = 0.7                          # segundos entre peticiones a la CNMV
SEMANAS = 13

# Clasificación sectorial propia de El Especulador (cortos/sectores.csv); si no está, el agregado por sector no se publica.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cortos"))
    import sectores as _sectores
    SECTORES = _sectores.cargar()
except Exception:  # noqa: BLE001
    _sectores, SECTORES = None, None
SEMANAS_MINIMAS = 52                 # el percentil solo se publica con 52 ventanas anteriores (SEMANAS_MINIMAS + SEMANAS semanas de serie)
AVISOS: list[str] = []
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# El lugar de la operación es un código de centro de negociación (XMAD, XMCE, BATE, TRQX...) o un texto como
# «Fuera de un centro de negociación» / XOFF: solo lo segundo saca la operación del neto discrecional.
FUERA = ("fuera", "off", "xoff", "xxxx", "otc", "no aplica", "n/a")
PALABRAS_PLAN = ("plan ", "plan de", "incentiv", "retribu", "remuner", "bonus", "entrega gratuita", "gratuita", "vesting", "consolidaci",
                 "stock option", "opciones sobre", "ejercicio de", "préstamo", "prestamo", "pignor", "garantía", "garantia", "donación", "donacion",
                 "herencia", "sucesi", "canje", "scrip", "dividendo flexible", "ampliación", "ampliacion", "permuta", "aportación", "aportacion",
                 "employee", "share plan", "incentive", "compensation", "restricted", "performance shares", "matching")
INSTRUMENTO_ACCION = ("acci", "share", "stock")
COMPRA = ("compra", "adquisici", "purchase", "acquisition", "buy")
VENTA = ("venta", "enajenaci", "transmisi", "sale", "disposal", "sell")
OPERACION_PLAN = ("entrega", "ejercicio", "canje", "permuta", "exercise", "delivery", "vesting", "award")


class DatosRaros(Exception):
    """La CNMV no responde o el registro no tiene la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga
def _get(sesion: requests.Session, url: str, params: dict | None = None, esperas: list[int] | None = None,
         dormir=time.sleep, binario: bool = False):
    esperas = [10, 30, 60, 120] if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = sesion.get(url, params=params, headers=CABECERAS, timeout=(20, 90))
            if r.status_code == 200 and (r.content if binario else r.text.strip()):
                return r.content if binario else r.text
            ultimo = f"HTTP {r.status_code}, {len(r.content)} bytes"
        except requests.RequestException as e:
            ultimo = str(e)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar {url}: {ultimo}")


# --------------------------------------------------------------------------- lectores
def leer_listado(html: str) -> tuple[list[dict], int, int]:
    """Una página del registro -> (notificaciones, página actual, páginas totales). Sin el nombre del declarante."""
    m = re.search(r"P[áa]gina (\d+) de (\d+)", html)
    bloques = re.findall(r'(?s)<li id="ctl00_ContentPrincipal_wucRegistros_repListaPrincipal_ctl\d+_elementoPrimerNivel"(.*?)N[úu]mero de registro:\s*(\d+)', html)
    if not m and not bloques:
        if re.search(r"(?i)no se han encontrado|sin resultados|no hay resultados", html):
            return [], 1, 1
        raise DatosRaros("El listado de la CNMV no tiene la forma esperada (ni paginación ni registros)")
    out = []
    for b, num in bloques:
        fecha = re.search(r'fecha-no-icon">\s*(\d{2})/(\d{2})/(\d{4})', b)
        emisor = re.search(r'class="tit-small">([^<]+)<', b)
        nif = re.search(r'datosentidad\.aspx\?nif=([^"&]+)', b)
        motivo = re.search(r'href="(https://www\.cnmv\.es/webservices/verdocumento/ver\?e=[^"]+)"[^>]*>\s*Motivo de la notificaci[óo]n:\s*([^<]+)<', b)
        if not (fecha and emisor and motivo):
            AVISOS.append(f"Registro {num}: bloque incompleto en el listado, se ignora")
            continue
        texto_motivo = motivo.group(2).strip().lower()
        out.append({"registro": num, "fecha_registro": f"{fecha.group(3)}-{fecha.group(2)}-{fecha.group(1)}",
                    "emisor": re.sub(r"\s+", " ", html_mod.unescape(emisor.group(1))).strip(), "nif": (nif.group(1) if nif else "").replace("-", ""),
                    "motivo": "vinculada" if "vinculad" in texto_motivo else "directivo",
                    "documento": motivo.group(1).replace("&amp;", "&")})
    return out, int(m.group(1)) if m else 1, int(m.group(2)) if m else 1


def texto_pdf(contenido: bytes) -> str:
    """Texto con disposición del PDF (poppler)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(contenido)
        f.flush()
        r = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise DatosRaros(f"pdftotext no pudo leer el PDF: {r.stderr[:200]}")
    return r.stdout


def _numero(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if not s or s in ("...", "-", "—"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _tipo_cargo(cargo: str, motivo: str) -> str:
    c = cargo.lower()
    if motivo == "vinculada":
        return "vinculada"
    if "consejer" in c or ("director" in c and "board" in c) or "board member" in c or "non-executive" in c or "presidente del consejo" in c or "chairman" in c:
        return "consejero"
    if any(k in c for k in ("president", "ceo", "chief", "director general", "consejero delegado", "secretario", "vicepresident", "director", "cfo", "coo", "managing", "head", "gerente", "responsable")):
        return "directivo"
    return "directivo"


def _tipo_operacion(instrumento: str, operacion: str, lugar: str, otra: str) -> str:
    """discrecional | plan | derivado | fuera_mercado | otro."""
    i, o, l, t = instrumento.lower(), operacion.lower(), lugar.lower(), otra.lower()
    if not any(k in i for k in INSTRUMENTO_ACCION) or any(k in i for k in ("derecho", "opci", "deriv", "warrant", "bono", "obligaci", "cfd", "swap", "futuro", "right")):
        return "derivado"
    if any(k in o for k in OPERACION_PLAN):
        return "plan"
    if not (any(k in o for k in COMPRA) or any(k in o for k in VENTA)):
        return "otro"
    if any(k in t for k in PALABRAS_PLAN):
        return "plan"
    if not l or any(k in l for k in FUERA):
        return "fuera_mercado"
    return "discrecional"


def leer_notificacion(texto: str, motivo: str) -> dict:
    """Del texto del PDF estándar saca cargo, emisor, LEI, las filas de operaciones y «otra información». Nunca el nombre."""
    t = texto.replace("\ufb01", "fi").replace("\ufb02", "fl")
    cargo = ""
    m = re.search(r"Cargo\s*-\s*posici[óo]n\s*\|\s*Job title\s*\n+\s*(.+)", t)
    if m:
        cargo = re.sub(r"\s+", " ", m.group(1)).strip()
    emisor = ""
    m = re.search(r"a\)\s*Identificaci[óo]n\s*\|\s*Name:?\s*\n+\s*(.+)", t)
    if m:
        emisor = re.sub(r"\s+", " ", m.group(1)).strip()
    lei = ""
    m = re.search(r"b\)\s*LEI:?\s*\n+\s*([A-Z0-9]{20})", t)
    if m:
        lei = m.group(1)
    m = re.search(r"Initial Notification\s*-\s*Amendment\s*\n+\s*(.+)", t, re.I)
    modificacion = bool(m and "modif" in m.group(1).lower() and "inicial" not in m.group(1).lower())
    otra = ""
    m = re.search(r"Otra informaci[óo]n\s*\|\s*Additional information\s*\n(.*?)(?:\n\s*\d/\d\s*$|\Z)", t, re.S)
    if m:
        otra = re.sub(r"\s+", " ", m.group(1)).strip()
    filas = []
    patron = re.compile(r"^\s*([A-Z]{2}[A-Z0-9]{9}\d)\s+(.+?)\s{2,}(.+?)\s{2,}(\d{2}/\d{2}/\d{4})\s+(.+?)\s{2,}([\d.,]+)\s+([\d.,]+)\s+([A-Z]{3})\s*$", re.M)
    for isin, instr, oper, fecha, lugar, vol, precio, divisa in patron.findall(t):
        d, mth, y = fecha.split("/")
        filas.append({"isin": isin, "instrumento": instr.strip(), "operacion": oper.strip(), "fecha_operacion": f"{y}-{mth}-{d}",
                      "lugar": lugar.strip(), "volumen": _numero(vol), "precio": _numero(precio), "divisa": divisa})
    if not filas:
        # formulario con la tabla partida en varias líneas: ISIN en una, resto en otras; se intenta por campos sueltos
        isin = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", t[t.find("4. DATOS DE LA OPERACI"):] if "4. DATOS DE LA OPERACI" in t else t)
        fecha = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", t[t.find("4. DATOS DE LA OPERACI"):] if "4. DATOS DE LA OPERACI" in t else "")
        agregado = re.search(r"Total Agregado.*?\n(?:.*\n){0,4}?\s*([\d.,]+)\s+([\d.,]+)\s*$", t, re.M)
        if isin and fecha and agregado:
            d, mth, y = fecha.group(1).split("/")
            oper = "compra" if re.search(r"(?i)\bcompra\b|\badquisici", t) else ("venta" if re.search(r"(?i)\bventa\b|\benajenaci|\btransmisi", t) else "")
            filas.append({"isin": isin.group(1), "instrumento": "Acción" if re.search(r"(?i)acci[óo]n", t) else "", "operacion": oper,
                          "fecha_operacion": f"{y}-{mth}-{d}", "lugar": "", "volumen": _numero(agregado.group(1)), "precio": _numero(agregado.group(2)),
                          "divisa": "EUR", "agregado": True})
    return {"cargo_tipo": _tipo_cargo(cargo, motivo), "emisor_pdf": emisor, "lei": lei, "modificacion": modificacion, "otra_informacion": otra[:300], "filas": filas}


def operaciones_de(notif: dict, detalle: dict) -> list[dict]:
    """Una fila de operaciones por cada fila de la notificación, ya clasificada y sin datos personales."""
    out = []
    for i, f in enumerate(detalle["filas"]):
        tipo = _tipo_operacion(f["instrumento"], f["operacion"], f["lugar"], detalle["otra_informacion"])
        o = f["operacion"].lower()
        sentido = "compra" if any(k in o for k in COMPRA) else ("venta" if any(k in o for k in VENTA) else "otro")
        importe = round(f["volumen"] * f["precio"], 2) if f["volumen"] is not None and f["precio"] is not None else None
        out.append({"registro": notif["registro"], "linea": i + 1, "fecha_registro": notif["fecha_registro"], "fecha_operacion": f["fecha_operacion"],
                    "emisor": notif["emisor"], "nif": notif["nif"], "lei": detalle["lei"], "isin": f["isin"], "motivo": notif["motivo"],
                    "cargo_tipo": detalle["cargo_tipo"], "instrumento": f["instrumento"], "operacion": f["operacion"], "sentido": sentido, "tipo": tipo,
                    "lugar": f["lugar"], "volumen": f["volumen"], "precio": f["precio"], "divisa": f["divisa"],
                    "importe_eur": importe if f["divisa"] == "EUR" else None, "modificacion": "1" if detalle["modificacion"] else "0",
                    "sustituida": "0", "documento": notif["documento"]})
    return out


# --------------------------------------------------------------------------- estado
CAMPOS = ["registro", "linea", "fecha_registro", "fecha_operacion", "emisor", "nif", "lei", "isin", "motivo", "cargo_tipo", "instrumento", "operacion",
          "sentido", "tipo", "lugar", "volumen", "precio", "divisa", "importe_eur", "modificacion", "sustituida", "documento"]


def marcar_sustituidas(operaciones: list[dict]) -> int:
    """Una notificación de modificación sustituye a la inicial: las filas anteriores del mismo emisor con el mismo
    ISIN, fecha, volumen y precio (registradas en los 90 días previos) quedan marcadas y fuera de los cálculos.
    No hace falta el nombre del declarante para casarlas. Devuelve cuántas filas quedan marcadas."""
    for o in operaciones:
        o["sustituida"] = "0"
    modificaciones = [o for o in operaciones if str(o.get("modificacion")) == "1"]
    if not modificaciones:
        return 0
    por_clave: dict[tuple, list[dict]] = {}
    for o in operaciones:
        por_clave.setdefault((o["nif"] or o["emisor"], o["isin"], o["fecha_operacion"], o["volumen"], o["precio"]), []).append(o)
    n = 0
    for m in modificaciones:
        for o in por_clave.get((m["nif"] or m["emisor"], m["isin"], m["fecha_operacion"], m["volumen"], m["precio"]), []):
            if o["registro"] < m["registro"] and o["sustituida"] == "0" and 0 <= (date.fromisoformat(m["fecha_registro"]) - date.fromisoformat(o["fecha_registro"])).days <= 90:
                o["sustituida"] = "1"
                n += 1
    return n


def cargar_operaciones(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    for f in filas:
        for k in ("volumen", "precio", "importe_eur"):
            f[k] = float(f[k]) if f.get(k) not in (None, "") else None
        f["linea"] = int(f["linea"])
        f.setdefault("sustituida", "0")
    return filas


def guardar_operaciones(ruta: Path, filas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    filas = sorted(filas, key=lambda f: (f["fecha_registro"], f["registro"], f["linea"]))
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        for f in filas:
            w.writerow({k: ("" if f.get(k) is None else f.get(k)) for k in CAMPOS})


def cargar_pendientes(ruta: Path) -> dict[str, dict]:
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8", newline="") as fh:
        return {f["registro"]: f for f in csv.DictReader(fh)}


def guardar_pendientes(ruta: Path, pend: dict[str, dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["registro", "fecha_registro", "emisor", "nif", "motivo", "documento", "intentos", "motivo_fallo"])
        w.writeheader()
        for r in sorted(pend):
            w.writerow(pend[r])


# --------------------------------------------------------------------------- recogida
def tramos_pendientes(cobertura: dict, hoy: date) -> list[tuple[date, date]]:
    """Qué fechas del registro faltan por leer: los últimos DIAS_RECIENTES siempre, y hacia atrás hasta INICIO_REGISTRO."""
    out = [(hoy - timedelta(days=DIAS_RECIENTES), hoy)]
    leido_desde = date.fromisoformat(cobertura["desde"]) if cobertura.get("desde") else hoy - timedelta(days=DIAS_RECIENTES)
    fin = leido_desde - timedelta(days=1)
    while fin >= INICIO_REGISTRO:
        ini = max(INICIO_REGISTRO, fin - timedelta(days=TRAMO_DIAS - 1))
        out.append((ini, fin))
        fin = ini - timedelta(days=1)
    return out


def listar(sesion, desde: date, hasta: date, local: Path | None, dormir=time.sleep) -> list[dict]:
    """Todas las notificaciones del registro entre dos fechas (todas las páginas)."""
    out, pagina, total = [], 0, 1
    while pagina < total:
        if local:
            ruta = local / f"listado_{desde.isoformat()}_{hasta.isoformat()}_{pagina}.html"
            if not ruta.exists():
                if pagina == 0:
                    raise DatosRaros(f"sin listado guardado para {desde}..{hasta}")
                break
            html = ruta.read_text(encoding="utf-8")
        else:
            html = _get(sesion, URL_LISTADO, {"fechad": desde.strftime("%d/%m/%Y"), "fechah": hasta.strftime("%d/%m/%Y"), "page": pagina}, dormir=dormir)
            dormir(PAUSA)
        filas, actual, total = leer_listado(html)
        out.extend(filas)
        pagina += 1
        if pagina > 400:
            raise DatosRaros("Más de 400 páginas en un tramo: el registro no responde como se esperaba")
    return out


def recoger(salida: Path, hoy: date, local: Path | None = None, max_documentos: int = MAX_DOCUMENTOS, dormir=time.sleep) -> dict:
    """Lee el registro, descarga los PDF nuevos y actualiza operaciones.csv, pendientes.csv y cobertura.json."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    operaciones = cargar_operaciones(dd / "operaciones.csv")
    pendientes = cargar_pendientes(dd / "pendientes.csv")
    cobertura = json.loads((dd / "cobertura.json").read_text(encoding="utf-8")) if (dd / "cobertura.json").exists() else {}
    vistos = {f["registro"] for f in operaciones} | set(cobertura.get("sin_operaciones", []))
    sesion = requests.Session()
    descargados, nuevos_registros, fallos = 0, 0, 0
    nuevos_sin_ops = []
    intentados = set()
    tramos = tramos_pendientes(cobertura, hoy)
    tramos_hechos = []
    for ini, fin in tramos:
        if descargados >= max_documentos:
            break
        try:
            lista = listar(sesion, ini, fin, local, dormir)
        except DatosRaros as e:
            if ini == tramos[0][0]:
                raise
            AVISOS.append(f"Tramo {ini}..{fin}: {e}; se deja para otra pasada")
            break
        completo = True
        for n in lista:
            if n["registro"] in vistos:
                continue
            if descargados >= max_documentos:
                completo = False
                break
            try:
                if local:
                    ruta = local / f"doc_{n['registro']}.txt"
                    if not ruta.exists():
                        raise DatosRaros("sin PDF guardado")
                    texto = ruta.read_text(encoding="utf-8")
                else:
                    texto = texto_pdf(_get(sesion, n["documento"], dormir=dormir, binario=True))
                    dormir(PAUSA)
                descargados += 1
                detalle = leer_notificacion(texto, n["motivo"])
                ops = operaciones_de(n, detalle)
                if not ops:
                    nuevos_sin_ops.append(n["registro"])
                    AVISOS.append(f"Registro {n['registro']} ({n['emisor']}): el PDF no tiene filas de operaciones legibles")
                operaciones.extend(ops)
                vistos.add(n["registro"])
                nuevos_registros += 1
                pendientes.pop(n["registro"], None)
            except DatosRaros as e:
                fallos += 1
                intentados.add(n["registro"])
                p = pendientes.get(n["registro"], {"intentos": "0"})
                pendientes[n["registro"]] = {"registro": n["registro"], "fecha_registro": n["fecha_registro"], "emisor": n["emisor"], "nif": n["nif"],
                                             "motivo": n["motivo"], "documento": n["documento"], "intentos": str(int(p.get("intentos", "0")) + 1),
                                             "motivo_fallo": str(e)[:150]}
        if completo:
            tramos_hechos.append((ini, fin))
        else:
            break
    # reintentos de pendientes (hasta 5 intentos)
    for reg, p in list(pendientes.items()):
        if descargados >= max_documentos or int(p.get("intentos", "0")) >= 5 or reg in vistos or reg in intentados:
            continue
        try:
            if local:
                ruta = local / f"doc_{reg}.txt"
                if not ruta.exists():
                    raise DatosRaros("sin PDF guardado")
                texto = ruta.read_text(encoding="utf-8")
            else:
                texto = texto_pdf(_get(sesion, p["documento"], dormir=dormir, binario=True))
                dormir(PAUSA)
            descargados += 1
            ops = operaciones_de({"registro": reg, "fecha_registro": p["fecha_registro"], "emisor": p["emisor"], "nif": p["nif"], "motivo": p["motivo"],
                                  "documento": p["documento"]}, leer_notificacion(texto, p["motivo"]))
            operaciones.extend(ops)
            vistos.add(reg)
            nuevos_registros += 1
            pendientes.pop(reg)
        except DatosRaros as e:
            p["intentos"] = str(int(p.get("intentos", "0")) + 1)
            p["motivo_fallo"] = str(e)[:150]
    # cobertura: el tramo reciente siempre; hacia atrás, solo los tramos completos consecutivos
    desde_antes = date.fromisoformat(cobertura["desde"]) if cobertura.get("desde") else None
    desde_nuevo = desde_antes
    for ini, fin in tramos_hechos[1:] if tramos_hechos and tramos_hechos[0] == tramos[0] else []:
        if desde_nuevo is None or fin == desde_nuevo - timedelta(days=1):
            desde_nuevo = ini
    if tramos_hechos and tramos_hechos[0] == tramos[0] and desde_nuevo is None:
        desde_nuevo = tramos[0][0]
    cobertura = {"desde": desde_nuevo.isoformat() if desde_nuevo else None, "hasta": hoy.isoformat(), "completo_hasta_inicio": bool(desde_nuevo and desde_nuevo <= INICIO_REGISTRO),
                 "sin_operaciones": sorted(set(cobertura.get("sin_operaciones", [])) | set(nuevos_sin_ops)), "ultima_pasada": hoy.isoformat()}
    sustituidas = marcar_sustituidas(operaciones)
    guardar_operaciones(dd / "operaciones.csv", operaciones)
    guardar_pendientes(dd / "pendientes.csv", pendientes)
    (dd / "cobertura.json").write_text(json.dumps(cobertura, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"operaciones": operaciones, "cobertura": cobertura, "descargados": descargados, "nuevos": nuevos_registros, "fallos": fallos, "pendientes": len(pendientes),
            "sustituidas": sustituidas}


# --------------------------------------------------------------------------- cálculo
def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def inicio_cubierto(cobertura: dict) -> date | None:
    """Primer lunes con el registro ya leído: las semanas anteriores solo tienen notificaciones tardías y no sirven para
    comparar. None si el registro está leído desde el inicio del formulario europeo o no se sabe desde cuándo."""
    if cobertura.get("completo_hasta_inicio") or not cobertura.get("desde"):
        return None
    d = date.fromisoformat(cobertura["desde"])
    return d + timedelta(days=(7 - d.weekday()) % 7)


def serie_semanal(operaciones: list[dict], hoy: date, desde: date | None = None) -> list[dict]:
    """Compras y ventas discrecionales por semana (lunes), desde la primera operación (o desde `desde`, el primer lunes
    con el registro leído) hasta la semana actual."""
    disc = [o for o in operaciones if o["tipo"] == "discrecional" and o["sentido"] in ("compra", "venta")]
    if not disc:
        return []
    primera = _lunes(min(date.fromisoformat(o["fecha_operacion"]) for o in disc))
    if desde is not None:
        primera = max(primera, desde)
    semanas: dict[date, dict] = {}
    s = primera
    while s <= _lunes(hoy):
        semanas[s] = {"semana": s.isoformat(), "compras_n": 0, "ventas_n": 0, "compras_eur": 0.0, "ventas_eur": 0.0, "empresas_compra": set(), "empresas_venta": set()}
        s += timedelta(days=7)
    for o in disc:
        k = _lunes(date.fromisoformat(o["fecha_operacion"]))
        if k not in semanas:
            continue
        fila = semanas[k]
        if o["sentido"] == "compra":
            fila["compras_n"] += 1
            fila["compras_eur"] += o["importe_eur"] or 0.0
            fila["empresas_compra"].add(o["nif"] or o["emisor"])
        else:
            fila["ventas_n"] += 1
            fila["ventas_eur"] += o["importe_eur"] or 0.0
            fila["empresas_venta"].add(o["nif"] or o["emisor"])
    out = []
    for k in sorted(semanas):
        f = semanas[k]
        n = f["compras_n"] + f["ventas_n"]
        out.append({"semana": f["semana"], "compras_n": f["compras_n"], "ventas_n": f["ventas_n"], "compras_eur": round(f["compras_eur"], 2),
                    "ventas_eur": round(f["ventas_eur"], 2), "neto_eur": round(f["compras_eur"] - f["ventas_eur"], 2),
                    "proporcion_compras": round(100 * f["compras_n"] / n, 1) if n else None,
                    "empresas_compra": len(f["empresas_compra"]), "empresas_venta": len(f["empresas_venta"])})
    return out


def ventana_13(serie: list[dict], hasta_indice: int) -> dict | None:
    """Agregado de las SEMANAS semanas que acaban en la semana de índice dado."""
    trozo = serie[max(0, hasta_indice - SEMANAS + 1): hasta_indice + 1]
    if len(trozo) < SEMANAS:
        return None
    c = sum(f["compras_n"] for f in trozo)
    v = sum(f["ventas_n"] for f in trozo)
    ce = sum(f["compras_eur"] for f in trozo)
    ve = sum(f["ventas_eur"] for f in trozo)
    return {"compras_n": c, "ventas_n": v, "compras_eur": round(ce, 2), "ventas_eur": round(ve, 2), "neto_eur": round(ce - ve, 2),
            "proporcion_compras": round(100 * c / (c + v), 1) if c + v else None}


def percentil(valor: float, historia: list[float]) -> int | None:
    if not historia:
        return None
    return round(100 * sum(1 for h in historia if h <= valor) / len(historia))


def calcular(operaciones: list[dict], hoy: date, cobertura: dict) -> dict:
    sustituidas = [o for o in operaciones if str(o.get("sustituida")) == "1"]
    operaciones = [o for o in operaciones if str(o.get("sustituida")) != "1"]
    serie = serie_semanal(operaciones, hoy, inicio_cubierto(cobertura))
    actual = ventana_13(serie, len(serie) - 1) if serie else None
    historia = []
    if serie and len(serie) >= SEMANAS_MINIMAS + SEMANAS:
        for i in range(SEMANAS - 1, len(serie) - 1):
            v = ventana_13(serie, i)
            if v and v["proporcion_compras"] is not None:
                historia.append(v["proporcion_compras"])
    pct = percentil(actual["proporcion_compras"], historia) if actual and actual["proporcion_compras"] is not None and len(historia) >= SEMANAS_MINIMAS else None
    desde = hoy - timedelta(weeks=SEMANAS)
    recientes = [o for o in operaciones if o["fecha_operacion"] >= desde.isoformat()]
    por_empresa: dict[str, dict] = {}
    for o in recientes:
        k = o["nif"] or o["emisor"]
        e = por_empresa.setdefault(k, {"emisor": o["emisor"], "nif": o["nif"], "isin": o["isin"], "compras_n": 0, "ventas_n": 0, "compras_eur": 0.0, "ventas_eur": 0.0,
                                       "otras_n": 0, "ultima_operacion": o["fecha_operacion"], "cargos": set()})
        e["ultima_operacion"] = max(e["ultima_operacion"], o["fecha_operacion"])
        if o["tipo"] == "discrecional" and o["sentido"] == "compra":
            e["compras_n"] += 1
            e["compras_eur"] += o["importe_eur"] or 0.0
            e["cargos"].add(o["cargo_tipo"])
        elif o["tipo"] == "discrecional" and o["sentido"] == "venta":
            e["ventas_n"] += 1
            e["ventas_eur"] += o["importe_eur"] or 0.0
            e["cargos"].add(o["cargo_tipo"])
        else:
            e["otras_n"] += 1
    empresas = []
    for e in por_empresa.values():
        e["neto_eur"] = round(e["compras_eur"] - e["ventas_eur"], 2)
        e["compras_eur"] = round(e["compras_eur"], 2)
        e["ventas_eur"] = round(e["ventas_eur"], 2)
        e["cargos"] = sorted(e["cargos"])
        empresas.append(e)
    empresas.sort(key=lambda e: -abs(e["neto_eur"]))
    mes_ini = date(hoy.year, hoy.month, 1)
    mes_ant_fin = mes_ini - timedelta(days=1)
    mes_ant_ini = date(mes_ant_fin.year, mes_ant_fin.month, 1)
    def agregado(desde_: date, hasta_: date) -> dict:
        ops = [o for o in operaciones if desde_.isoformat() <= o["fecha_operacion"] <= hasta_.isoformat() and o["tipo"] == "discrecional"]
        c = [o for o in ops if o["sentido"] == "compra"]
        v = [o for o in ops if o["sentido"] == "venta"]
        return {"desde": desde_.isoformat(), "hasta": hasta_.isoformat(), "compras_n": len(c), "ventas_n": len(v),
                "compras_eur": round(sum(o["importe_eur"] or 0 for o in c), 2), "ventas_eur": round(sum(o["importe_eur"] or 0 for o in v), 2),
                "empresas_compra": len({o["nif"] or o["emisor"] for o in c}), "empresas_venta": len({o["nif"] or o["emisor"] for o in v}),
                "proporcion_compras": round(100 * len(c) / (len(c) + len(v)), 1) if c or v else None}
    def por_sector(desde_: date, hasta_: date) -> dict | None:
        """Compras y ventas discrecionales por sector propio entre dos fechas; None sin tabla sectorial."""
        if not SECTORES:
            return None
        ops = [o for o in operaciones if desde_.isoformat() <= o["fecha_operacion"] <= hasta_.isoformat() and o["tipo"] == "discrecional"]
        grupos: dict[str, dict] = {}
        sin = set()
        for o in ops:
            clave = _sectores.sector_de(o.get("isin"), SECTORES)
            if clave == _sectores.SIN_SECTOR:
                sin.add(o.get("isin") or o["emisor"])
            g = grupos.setdefault(clave, {"sector": clave, "nombre": _sectores.nombre_sector(clave), "compras_n": 0, "ventas_n": 0, "compras_eur": 0.0, "ventas_eur": 0.0, "empresas": set()})
            g["empresas"].add(o["nif"] or o["emisor"])
            if o["sentido"] == "compra":
                g["compras_n"] += 1
                g["compras_eur"] += o["importe_eur"] or 0.0
            elif o["sentido"] == "venta":
                g["ventas_n"] += 1
                g["ventas_eur"] += o["importe_eur"] or 0.0
        filas = []
        for g in grupos.values():
            g["empresas"] = len(g["empresas"])
            g["compras_eur"], g["ventas_eur"] = round(g["compras_eur"], 2), round(g["ventas_eur"], 2)
            g["neto_eur"] = round(g["compras_eur"] - g["ventas_eur"], 2)
            g["proporcion_compras"] = round(100 * g["compras_n"] / (g["compras_n"] + g["ventas_n"]), 1) if g["compras_n"] + g["ventas_n"] else None
            filas.append(g)
        filas.sort(key=lambda g: (-g["neto_eur"], g["nombre"]))
        if sin:
            AVISOS.append(f"{len(sin)} emisores sin sector en cortos/sectores.csv (se agregan como «sin sector»): {', '.join(sorted(sin)[:8])}")
        return {"desde": desde_.isoformat(), "hasta": hasta_.isoformat(), "sectores": filas, "sin_sector": sorted(sin)}
    recientes_lista = sorted([o for o in operaciones if o["fecha_registro"] >= (hoy - timedelta(days=30)).isoformat()],
                             key=lambda o: (o["fecha_registro"], o["registro"], o["linea"]), reverse=True)
    totales = {"operaciones": len(operaciones), "sustituidas": len(sustituidas), "discrecionales": sum(1 for o in operaciones if o["tipo"] == "discrecional"),
               "por_tipo": {t: sum(1 for o in operaciones if o["tipo"] == t) for t in ("discrecional", "plan", "derivado", "fuera_mercado", "otro")},
               "primera_operacion": min((o["fecha_operacion"] for o in operaciones), default=None),
               "ultimo_registro": max((o["fecha_registro"] for o in operaciones), default=None)}
    res = {"fecha": hoy.isoformat(), "semanas": SEMANAS, "ventana_desde": desde.isoformat(), "actual": actual, "percentil_proporcion": pct,
           "semanas_de_historia": len(historia), "empresas_13_semanas": empresas, "mes_en_curso": agregado(mes_ini, hoy), "mes_anterior": agregado(mes_ant_ini, mes_ant_fin),
           "recientes": recientes_lista[:60], "serie": serie, "totales": totales, "cobertura": cobertura,
           "sectores_13_semanas": por_sector(desde, hoy), "sectores_mes_anterior": por_sector(mes_ant_ini, mes_ant_fin)}
    base = {"version": VERSION, "ultimo_registro": totales["ultimo_registro"], "n": totales["operaciones"], "semana": _lunes(hoy).isoformat(),
            "empresas": [[e["nif"], e["compras_n"], e["ventas_n"], e["neto_eur"]] for e in empresas], "actual": actual}
    res["huella"] = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return res


# --------------------------------------------------------------------------- textos
def _eur(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{abs(v):,.0f}".replace(",", ".")
    return ("−" if v < 0 else "") + s + " €"


def _f(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _importe_txt(o: dict) -> str:
    if o["divisa"] == "EUR":
        return _eur(o["importe_eur"])
    return _html(f"{_cifra(o['volumen'], 0)} × {_cifra(o['precio'], 2)} {o['divisa']}")


def _cifra(v, minimo: int) -> str:
    """Número a la española: miles con punto, decimales con coma, sin ceros sobrantes (como mínimo `minimo` decimales)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return _html(v)
    s = f"{abs(x):,.4f}".rstrip("0")
    entero, _, dec = s.partition(".")
    dec = dec.ljust(minimo, "0")
    s = entero.replace(",", ".") + ("," + dec if dec else "")
    return ("−" if x < 0 else "") + s


def _nombre(e: str) -> str:
    e = re.sub(r",?\s*(S\.A\.|SA|S\.A|SOCIEDAD AN[ÓO]NIMA)\s*$", "", e.strip(), flags=re.I)
    return e.title().replace(" De ", " de ").replace(" Y ", " y ").replace(" Del ", " del ").replace("Ibex", "IBEX").replace("Iag", "IAG").replace("Bbva", "BBVA").replace("Acs", "ACS")


CARGO_TXT = {"consejero": "consejero", "directivo": "directivo", "vinculada": "persona vinculada"}
TIPO_TXT = {"discrecional": "", "plan": "plan de acciones o retribución", "derivado": "instrumento distinto de acciones", "fuera_mercado": "fuera de mercado", "otro": "otra operación"}


def fragmento(res: dict, fecha_pub: str) -> str:
    a = res["actual"]
    emp = res["empresas_13_semanas"]
    compradoras = sorted([e for e in emp if e["neto_eur"] > 0], key=lambda e: -e["neto_eur"])[:10]
    vendedoras = sorted([e for e in emp if e["neto_eur"] < 0], key=lambda e: e["neto_eur"])[:10]
    partes = [f"<!-- directivos:inicio {res['huella']} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con las notificaciones registradas en la CNMV hasta el {_f(res["totales"]["ultimo_registro"])}. '
              + (f'Registro de la CNMV leído desde el {_f(res["cobertura"]["desde"])}: ' if inicio_cubierto(res["cobertura"]) else f'Operaciones desde el {_f(res["totales"]["primera_operacion"])}; ')
              + f'{res["totales"]["operaciones"]} líneas leídas, {res["totales"]["discrecionales"]} discrecionales'
              + (f'; {res["totales"]["sustituidas"]} líneas iniciales sustituidas por notificaciones de modificación' if res["totales"]["sustituidas"] else "") + ".</p>"]
    if a and a["proporcion_compras"] is not None:
        frase = (f"En las últimas {SEMANAS} semanas, administradores y directivos de las cotizadas españolas han comunicado a la CNMV <strong>{a['compras_n']} compras</strong> "
                 f"y <strong>{a['ventas_n']} ventas</strong> discrecionales de acciones de su propia empresa: las compras son el <strong>{a['proporcion_compras']:.0f} %</strong> de las operaciones")
        if res["percentil_proporcion"] is not None:
            frase += f", percentil {res['percentil_proporcion']} de la serie semanal desde {res['serie'][0]['semana'][:4]} (ha sido igual o menor el {res['percentil_proporcion']} % de las semanas)"
        else:
            frase += (f" (el percentil histórico se publicará cuando la serie tenga {SEMANAS_MINIMAS + SEMANAS} semanas completas; ahora tiene "
                      f"{len(res['serie'])}, desde el {_f(res['serie'][0]['semana'])})")
        frase += f". En euros: {_eur(a['compras_eur'])} comprados frente a {_eur(a['ventas_eur'])} vendidos, neto {_eur(a['neto_eur'])}.</p>"
        partes.append("<p>" + frase)
    else:
        partes.append("<p>Todavía no hay trece semanas completas de operaciones discrecionales en la serie.</p>")
    partes.append(f"<h2>Las empresas con más compra neta de sus directivos ({SEMANAS} semanas)</h2>")
    if compradoras:
        partes.append('<figure class="wp-block-table"><table><thead><tr><th>Empresa</th><th>Compras</th><th>Ventas</th><th>Neto</th><th>Quién</th><th>Última operación</th></tr></thead><tbody>'
                      + "".join(f"<tr><td>{_html(_nombre(e['emisor']))}</td><td>{e['compras_n']}</td><td>{e['ventas_n']}</td><td>{_eur(e['neto_eur'])}</td>"
                                f"<td>{', '.join(CARGO_TXT.get(c, c) for c in e['cargos'])}</td><td>{_f(e['ultima_operacion'])}</td></tr>" for e in compradoras)
                      + "</tbody></table></figure>")
    else:
        partes.append("<p>Ninguna empresa con compra neta en la ventana.</p>")
    partes.append(f"<h2>Las empresas con más venta neta de sus directivos ({SEMANAS} semanas)</h2>")
    if vendedoras:
        partes.append('<figure class="wp-block-table"><table><thead><tr><th>Empresa</th><th>Compras</th><th>Ventas</th><th>Neto</th><th>Quién</th><th>Última operación</th></tr></thead><tbody>'
                      + "".join(f"<tr><td>{_html(_nombre(e['emisor']))}</td><td>{e['compras_n']}</td><td>{e['ventas_n']}</td><td>{_eur(e['neto_eur'])}</td>"
                                f"<td>{', '.join(CARGO_TXT.get(c, c) for c in e['cargos'])}</td><td>{_f(e['ultima_operacion'])}</td></tr>" for e in vendedoras)
                      + "</tbody></table></figure>")
    else:
        partes.append("<p>Ninguna empresa con venta neta en la ventana.</p>")
    sec = res.get("sectores_13_semanas")
    if sec and sec["sectores"]:
        partes.append(f"<h2>Por sector ({SEMANAS} semanas)</h2>"
                      '<figure class="wp-block-table"><table><thead><tr><th>Sector</th><th>Empresas</th><th>Compras</th><th>Ventas</th><th>Neto</th><th>Compras sobre el total</th></tr></thead><tbody>'
                      + "".join(f"<tr><td>{_html(g['nombre'])}</td><td>{g['empresas']}</td><td>{g['compras_n']}</td><td>{g['ventas_n']}</td><td>{_eur(g['neto_eur'])}</td>"
                                f"<td>{(str(round(g['proporcion_compras'])) + ' %') if g['proporcion_compras'] is not None else '—'}</td></tr>" for g in sec["sectores"])
                      + "</tbody></table></figure>"
                      '<p class="has-small-font-size">Sectores según la clasificación propia de El Especulador (ocho sectores, asignados por la actividad declarada por cada empresa); '
                      "las empresas que no están clasificadas se agrupan como «sin sector».</p>")
    partes.append("<h2>Las últimas notificaciones</h2><p>Registradas en la CNMV en los últimos 30 días, sin nombres: cada línea enlaza con la notificación pública. "
                  "Las que no son discrecionales (planes de acciones, derivados, fuera de mercado) se marcan.</p>")
    rec = res["recientes"][:40]
    if rec:
        partes.append('<figure class="wp-block-table"><table><thead><tr><th>Registro</th><th>Empresa</th><th>Quién</th><th>Operación</th><th>Fecha</th><th>Importe</th><th>Tipo</th></tr></thead><tbody>'
                      + "".join(f'<tr><td><a href="{o["documento"]}" rel="nofollow">{_f(o["fecha_registro"])}</a></td><td>{_html(_nombre(o["emisor"]))}</td>'
                                f"<td>{CARGO_TXT.get(o['cargo_tipo'], o['cargo_tipo'])}</td><td>{_html(o['sentido'] if o['sentido'] != 'otro' else o['operacion'])}</td>"
                                f"<td>{_f(o['fecha_operacion'])}</td><td>{_importe_txt(o)}</td>"
                                f"<td>{TIPO_TXT.get(o['tipo'], o['tipo'])}</td></tr>" for o in rec)
                      + "</tbody></table></figure>")
    else:
        partes.append("<p>Sin notificaciones en los últimos 30 días.</p>")
    m = res["mes_anterior"]
    partes.append(f"<h2>El mes anterior, en conjunto</h2><p>{MESES[int(m['desde'][5:7]) - 1].capitalize()} de {m['desde'][:4]}: {m['compras_n']} compras discrecionales en "
                  f"{m['empresas_compra']} empresas por {_eur(m['compras_eur'])} y {m['ventas_n']} ventas en {m['empresas_venta']} empresas por {_eur(m['ventas_eur'])}"
                  + (f"; las compras fueron el {m['proporcion_compras']:.0f} % de las operaciones." if m["proporcion_compras"] is not None else ".") + "</p>")
    cob = res["cobertura"]
    partes.append('<h2 id="metodo">Cómo se hace</h2>'
                  "<p>Las personas con responsabilidades de dirección en una cotizada, y sus personas vinculadas, deben comunicar a la CNMV sus operaciones con acciones "
                  "de la empresa (artículo 19 del Reglamento europeo de abuso de mercado). El Especulador lee ese registro público cada día y guarda cada operación sin el "
                  "nombre de quien la hace: empresa, tipo de cargo (consejero, directivo o persona vinculada), compra o venta, fecha, volumen y precio, con el enlace a la "
                  "notificación oficial. Cuenta como <strong>discrecional</strong> la compra o venta de acciones en un centro de negociación que la propia notificación no "
                  "atribuye a un plan de retribución, de incentivos o de compra para empleados; las entregas de acciones, el ejercicio de opciones, los derivados, "
                  "las operaciones fuera de mercado, los préstamos y las pignoraciones se guardan con su tipo y no entran en el neto. Cuando una notificación de "
                  "modificación repite las operaciones de una anterior (mismo emisor, fecha, volumen y precio), la anterior deja de contar. La «proporción de compras» es el "
                  f"porcentaje de operaciones discrecionales que son compras en las últimas {SEMANAS} semanas; el percentil compara esa proporción con todas las ventanas "
                  f"de {SEMANAS} semanas anteriores (solo se publica con al menos {SEMANAS_MINIMAS} ventanas anteriores, es decir, {SEMANAS_MINIMAS + SEMANAS} semanas de serie). "
                  "Los importes son volumen por precio, solo en euros. "
                  "Lectura histórica, sin predicción: que los directivos compren o vendan describe lo que han hecho, no lo que hará la acción.</p>"
                  f'<p class="has-small-font-size">Fuente: CNMV, <a href="{URL_REGISTRO}">registro de notificaciones de los directivos y personas vinculadas</a>, reproducido '
                  "fielmente (la CNMV lo ofrece gratis en cnmv.es). Registro leído desde el "
                  f"{_f(cob.get('desde'))}{' (completo desde el inicio del formulario europeo, mayo de 2018)' if cob.get('completo_hasta_inicio') else ' (se sigue completando hacia atrás)'}. "
                  "La clasificación y los cálculos son de El Especulador y se publican con licencia CC BY 4.0. Contenido informativo y educativo; no es asesoramiento "
                  "financiero ni recomendación de inversión.</p>")
    partes.append("<!-- directivos:fin -->")
    return "\n".join(partes)


def _frase_sectores(sec: dict | None) -> str:
    """Sector con más compra neta y con más venta neta del mes (anzuelo gratuito del agregado sectorial)."""
    if not sec or not sec["sectores"]:
        return ""
    con_datos = [g for g in sec["sectores"] if g["sector"] != "sin-sector"]
    if not con_datos:
        return ""
    mas = max(con_datos, key=lambda g: g["neto_eur"])
    menos = min(con_datos, key=lambda g: g["neto_eur"])
    partes = []
    if mas["neto_eur"] > 0:
        partes.append(f"más compra neta en {mas['nombre'].lower()} ({_eur(mas['neto_eur'])})")
    if menos["neto_eur"] < 0 and menos is not mas:
        partes.append(f"más venta neta en {menos['nombre'].lower()} ({_eur(menos['neto_eur'])})")
    return (" Por sectores: " + " y ".join(partes) + ".") if partes else ""


def resumen_mensual(res: dict) -> str:
    m = res["mes_anterior"]
    mes = f"{MESES[int(m['desde'][5:7]) - 1]} de {m['desde'][:4]}"
    return (f"<p><strong>Directivos del mercado español, {mes}</strong>: {m['compras_n']} compras discrecionales de acciones propias en {m['empresas_compra']} empresas "
            f"({_eur(m['compras_eur'])}) y {m['ventas_n']} ventas en {m['empresas_venta']} empresas ({_eur(m['ventas_eur'])})"
            + (f"; las compras fueron el {m['proporcion_compras']:.0f} % de las operaciones." if m["proporcion_compras"] is not None else ".")
            + _frase_sectores(res.get("sectores_mes_anterior"))
            + f' Fuente: registro público de la CNMV, sin nombres; detalle por empresa en <a href="{PAGINA_WP}">la página de directivos</a>. '
            "Contenido informativo; no es asesoramiento financiero.</p>\n")


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Compras y ventas de directivos comunicadas a la CNMV, sin nombres (El Especulador)",
        "description": "Operaciones de administradores, directivos y personas vinculadas con acciones de su empresa, comunicadas a la CNMV, clasificadas como discrecionales o no, "
                       "agregadas por empresa a 13 semanas y por semana desde 2018.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir del registro de notificaciones de directivos de la CNMV",
        "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": URL_REGISTRO, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/operaciones.csv"},
                         {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie_semanal.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    cambia = antes.get("huella") != res["huella"]
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "resumen-mensual.html", "datos/serie_semanal.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    with (dd / "serie_semanal.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["semana", "compras_n", "ventas_n", "compras_eur", "ventas_eur", "neto_eur", "proporcion_compras", "empresas_compra", "empresas_venta"])
        w.writeheader()
        for f in res["serie"]:
            w.writerow({k: ("" if f[k] is None else f[k]) for k in w.fieldnames})
    salida_json = {k: v for k, v in res.items() if k != "serie"}
    salida_json.update({"version": VERSION, "fecha_publicacion": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "fuente": "CNMV, registro de notificaciones de los directivos y personas vinculadas (Reglamento de Ejecución (UE) 2016/523)",
                        "condiciones": "Reproducción fiel del registro público de la CNMV, que lo ofrece gratuitamente en cnmv.es; sin nombres de personas físicas. "
                                       "Clasificación y cálculos de El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero."})
    previo.write_text(json.dumps(salida_json, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- directivos:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    (salida / "resumen-mensual.html").write_text(resumen_mensual(res), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compras y ventas de directivos comunicadas a la CNMV | El Especulador</title>
<meta name="description" content="Qué hacen con sus propias acciones los administradores y directivos de las cotizadas españolas: compras y ventas discrecionales comunicadas a la CNMV, por empresa y por semana, sin nombres.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:980px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} table{{border-collapse:collapse;width:100%;font-size:.92rem}} th,td{{border-bottom:1px solid #e3e8ef;padding:4px 6px;text-align:left}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Compras y ventas de directivos (CNMV)</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/operaciones.csv">todas las operaciones leídas, sin nombres</a> · <a href="datos/serie_semanal.csv">serie semanal</a> · <a href="datos/ultima.json">JSON</a>. Fuente: registro público de la CNMV; clasificación y cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="carpeta con respuestas guardadas: listado_<desde>_<hasta>_<pagina>.html y doc_<registro>.txt (texto de pdftotext)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--max-documentos", type=int, default=MAX_DOCUMENTOS, help="PDF que se descargan como máximo en esta pasada")
    ap.add_argument("--sin-descarga", action="store_true", help="no lee el registro; recalcula y reescribe con lo guardado")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else date.today()
    salida = Path(a.salida)
    if a.sin_descarga:
        dd = salida / "datos"
        operaciones = cargar_operaciones(dd / "operaciones.csv")
        cobertura = json.loads((dd / "cobertura.json").read_text(encoding="utf-8")) if (dd / "cobertura.json").exists() else {}
        marcar_sustituidas(operaciones)
        rec = {"operaciones": operaciones, "cobertura": cobertura, "descargados": 0, "nuevos": 0, "fallos": 0, "pendientes": 0, "sustituidas": 0}
    else:
        rec = recoger(salida, hoy, Path(a.local) if a.local else None, a.max_documentos)
    if not rec["operaciones"]:
        raise DatosRaros("No hay ninguna operación leída: no se publica nada")
    res = calcular(rec["operaciones"], hoy, rec["cobertura"])
    cambia = escribir(res, hoy, salida, forzar=a.forzar)
    for av in AVISOS[:50]:
        print(f"::warning::{av}")
    if len(AVISOS) > 50:
        print(f"::warning::… y {len(AVISOS) - 50} avisos más")
    t = res["totales"]
    print(f"Pasada del {hoy}: {rec['descargados']} PDF leídos, {rec['nuevos']} notificaciones nuevas, {rec['fallos']} fallos, {rec['pendientes']} pendientes. "
          f"Serie: {t['operaciones']} líneas ({t['discrecionales']} discrecionales, {t['sustituidas']} sustituidas por modificaciones) desde {t['primera_operacion']}; "
          f"registro cubierto desde {rec['cobertura'].get('desde')}. "
          f"{'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
