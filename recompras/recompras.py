"""Recompras del IBEX 35 (indicador 17): qué empresas comunican compras de acciones propias, cuánto, a qué
precio medio y cuánto llevan ejecutado de su programa.

Fuente: los informes que las empresas envían a la CNMV como «Otra Información Relevante» en cumplimiento del
art. 5 del Reglamento (UE) 596/2014 y del art. 2 del Reglamento Delegado (UE) 2016/1052. El colector `cnmv`
ya los identifica (caja `recompras` de `cnmv/datos/ibex35.csv`); este colector abre cada comunicado nuevo,
descarga su PDF, lee las filas diarias con `filas.py` (fase 0, validado con ocho maquetas distintas) y
extrae del texto el acumulado del programa cuando consta.

Salidas en `--salida` (en el servidor, $ESPEC_DATOS_DIR/recompras/):
  fragmento-wp.html        bloque para la página, entre <!-- recompras:inicio HUELLA --> y <!-- recompras:fin -->
  index.html               página propia
  datos/ultima.json        lo que se publica (versionado)
  datos/informes.csv       estado: un registro por comunicado leído (memoria entre pasadas)
  datos/operaciones.csv    todas las filas diarias leídas (empresa, fecha, centro, acciones, precio)
  datos/semanal.csv        serie semanal del IBEX (acciones e importe estimado) desde la primera pasada

Lee el listado de comunicados de `--cnmv` (por defecto `<datos>/cnmv/datos/ibex35.csv`, donde `--datos` es la
carpeta madre de `--salida`; admite una URL). `--local CARPETA` evita la red: toma `ibex35.csv` y un
`<nreg>.txt` (texto de pdftotext) por comunicado de esa carpeta. Si no hay listado o no tiene comunicados de
recompra, el script se para sin escribir (DatosRaros). Importe estimado = acciones × precio medio ponderado
del informe (estimación de El Especulador; el importe exacto está en cada documento).

Sin personas físicas: no se guarda quién firma el informe. Sin predicción ni recomendación.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filas  # noqa: E402

VERSION = "1.0.1"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/recompras/"
WEB = "https://elespeculador.com"
CNMV = "https://www.cnmv.es"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos; +https://elespeculador.com)", "Accept-Language": "es-ES,es;q=0.9"}
PAUSA = 1.0
MAX_INFORMES = 40
VENTANA_DIAS = 45   # las filas de un informe son de las semanas anteriores al comunicado (siete sesiones, art. 2.3 del RD 2016/1052)
INTENTOS_MAX = 3
LECTOR = "1.0.1"   # lector de fechas: lo leído «sin filas» con otro lector (o sin anotar) se relee una vez
DIAS_SEMANA = 7
DIAS_EN_CURSO = 45
SEMANAS_TABLA = 8
SEMANAS_PERCENTIL = 52
AVISOS: list[str] = []

CAMPOS_INFORMES = ["nreg", "isin", "empresa", "fecha_comunicado", "titulo", "enlace", "documento", "estado", "intentos", "filas",
                   "acciones", "precio_medio", "moneda", "importe_estimado_eur", "desde", "hasta", "dias", "centros", "total_declarado",
                   "coincide", "acciones_programa", "importe_programa_eur", "pct_programa", "pct_capital", "finalizado", "leido", "lector"]
CAMPOS_OPERACIONES = ["nreg", "isin", "empresa", "fecha", "centro", "operacion", "acciones", "precio", "moneda"]


class DatosRaros(Exception):
    pass


def aviso(texto: str) -> None:
    AVISOS.append(texto)
    print(f"::warning::{texto}")


# --------------------------------------------------------------------------- lectura del listado y de los documentos
def leer_listado(origen: str) -> list[dict]:
    """Filas de `cnmv/datos/ibex35.csv` con caja `recompras` (ruta local o URL), de la más reciente a la más antigua."""
    if origen.startswith("http"):
        import requests
        r = requests.get(origen, headers=CABECERAS, timeout=60)
        r.raise_for_status()
        texto = r.text
    else:
        ruta = Path(origen)
        if not ruta.exists():
            raise DatosRaros(f"no existe el listado de la CNMV: {origen}")
        texto = ruta.read_text(encoding="utf-8")
    filas_ = [r for r in csv.DictReader(io.StringIO(texto)) if r.get("caja") == "recompras" and r.get("nreg")]
    if not filas_:
        raise DatosRaros("el listado de la CNMV no tiene comunicados de recompra")
    filas_.sort(key=lambda r: (r.get("fecha", ""), r["nreg"]), reverse=True)
    return filas_


ENLACE = re.compile(r'<a[^>]+href="([^"]+)"', re.I)


def enlaces_documentos(pagina: str) -> list[str]:
    """Direcciones absolutas de los documentos del comunicado (`webservices/verdocumento/ver?t=...`), sin repetir y en orden."""
    salida: list[str] = []
    for a in ENLACE.findall(pagina):
        a = html.unescape(a)
        if "verdocumento" not in a.lower():
            continue
        u = a if a.startswith("http") else CNMV + (a if a.startswith("/") else "/" + a)
        if u not in salida:
            salida.append(u)
    return salida


def texto_pdf(contenido: bytes) -> str:
    """Texto de un PDF con `pdftotext -layout` (poppler-utils). Cadena vacía si falla."""
    if not contenido.startswith(b"%PDF"):
        return ""
    try:
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=contenido, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.decode("utf-8", errors="replace") if p.returncode == 0 else ""


# --------------------------------------------------------------------------- lectura del texto
PCT_PROGRAMA = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%\s*(?:del|sobre el)\s+importe\s+(?:monetario\s+)?m[áa]ximo", re.I)
IMPORTE_EUR = re.compile(r"(?:asciende a|alcanzado un importe de|importe(?: total)? de|por (?:un )?importe(?: total)? de)\s+([\d.]{4,}(?:,\d{1,2})?)\s*(?:euros|€|EUR)\b", re.I)
ACCIONES_PROGRAMA = re.compile(r"(?:asciende a|un total de|total de|ya se han adquirido)\s+([\d.]{5,})\s+(?:acciones|que representan|t[íi]tulos)", re.I)
CONTEXTO_PROGRAMA = re.compile(r"programa|hasta la fecha|hasta el d[íi]a|desde el inicio|acumulad|tramo", re.I)


def _con_contexto(plano: str, m: re.Match) -> bool:
    """La frase que rodea la coincidencia habla del programa entero (y no del total de la semana)."""
    ini = max(plano.rfind(". ", 0, m.start()), plano.rfind(": ", 0, m.start()), 0)
    fin = plano.find(". ", m.end())
    frase = plano[ini:fin if fin != -1 else m.end() + 120]
    return bool(CONTEXTO_PROGRAMA.search(frase))
PCT_CAPITAL = re.compile(r"representan?\s+(?:aproximadamente\s+)?el\s+(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s+del\s+capital\s+social", re.I)
FINALIZADO = re.compile(r"(?:ha finalizado|finalizaci[óo]n del programa|programa\s+de\s+recompra\s+ha\s+(?:concluido|terminado))", re.I)


def _num_es(t: str) -> float:
    return float(t.replace(".", "").replace(",", "."))


def resumen_programa(texto: str) -> dict:
    """Acumulado del programa según el texto del informe: porcentaje ejecutado del importe máximo, importe en euros,
    acciones acumuladas, porcentaje del capital y si el programa ha terminado. None en lo que no consta."""
    plano = re.sub(r"\s+", " ", texto)
    out = {"pct_programa": None, "importe_programa_eur": None, "acciones_programa": None, "pct_capital": None, "finalizado": False}
    m = PCT_PROGRAMA.search(plano)
    if m:
        out["pct_programa"] = round(float(m.group(1).replace(",", ".")), 2)
    importes = [_num_es(m.group(1)) for m in IMPORTE_EUR.finditer(plano) if _con_contexto(plano, m)]
    importes = [x for x in importes if x >= 100_000]
    if importes:
        out["importe_programa_eur"] = max(importes)
    for m in ACCIONES_PROGRAMA.finditer(plano):
        if _con_contexto(plano, m):
            out["acciones_programa"] = int(_num_es(m.group(1)))
            break
    m = PCT_CAPITAL.search(plano)
    if m:
        out["pct_capital"] = round(float(m.group(1).replace(",", ".")), 2)
    if FINALIZADO.search(plano):
        out["finalizado"] = True
        if out["pct_programa"] is None and re.search(r"alcanzado el importe m[áa]ximo", plano, re.I):
            out["pct_programa"] = 100.0
    return out


def analizar(texto: str, fecha_comunicado: date | None = None) -> dict:
    """Filas, resumen y acumulado del programa de un informe. `coincide` compara la suma de acciones con el total
    declarado (None si el documento no lo declara). Con `fecha_comunicado`, una fila fuera de la ventana del informe
    (de VENTANA_DIAS días antes del comunicado al propio día) delata una fecha mal leída: si el otro orden de las
    fechas dd/dd/aaaa (mes/día) deja más filas dentro, se lee así; las que sigan fuera se descartan con aviso."""
    f = filas.leer_filas(texto)
    fuera: list[dict] = []
    if fecha_comunicado is not None and f:
        def dentro(x):
            return fecha_comunicado - timedelta(days=VENTANA_DIAS) <= date.fromisoformat(x["fecha"]) <= fecha_comunicado
        if not all(dentro(x) for x in f):
            otro = filas.leer_filas(texto, orden="md")
            if sum(1 for x in otro if dentro(x)) > sum(1 for x in f if dentro(x)):
                f = otro
            fuera = [x for x in f if not dentro(x)]
            f = [x for x in f if dentro(x)]
    r = filas.resumen(f)
    declarados = filas.totales_declarados(texto)
    coincide = None
    if declarados and r["acciones"]:
        coincide = r["acciones"] in declarados
    return {"filas": f, "resumen": r, "declarados": declarados, "coincide": coincide, "programa": resumen_programa(texto), "fuera": fuera}


# --------------------------------------------------------------------------- estado entre pasadas
def cargar_estado(carpeta: Path) -> tuple[list[dict], list[dict]]:
    informes, operaciones = [], []
    if (carpeta / "informes.csv").exists():
        with (carpeta / "informes.csv").open(encoding="utf-8", newline="") as fh:
            informes = list(csv.DictReader(fh))
    if (carpeta / "operaciones.csv").exists():
        with (carpeta / "operaciones.csv").open(encoding="utf-8", newline="") as fh:
            operaciones = list(csv.DictReader(fh))
    return informes, operaciones


def fuera_de_plazo(e: dict) -> bool:
    """Informe leído con operaciones fuera de su ventana (antes de VENTANA_DIAS días o después del comunicado): fechas
    mal leídas por una versión anterior del lector. Se relee (con el límite de INTENTOS_MAX)."""
    try:
        c, d0, d1 = (date.fromisoformat(e[k]) for k in ("fecha_comunicado", "desde", "hasta"))
    except (KeyError, TypeError, ValueError):
        return False
    return d0 < c - timedelta(days=VENTANA_DIAS) or d1 > c


def pendientes(listado: list[dict], informes: list[dict]) -> list[dict]:
    """Comunicados del listado sin leer, con error, leídos con fechas fuera de plazo (fuera_de_plazo) o leídos «sin filas»
    con otro LECTOR, con menos de INTENTOS_MAX intentos, del más reciente al más antiguo."""
    estado = {i["nreg"]: i for i in informes}
    out = []
    for r in listado:
        e = estado.get(r["nreg"])
        quedan = e is not None and int(e.get("intentos") or 0) < INTENTOS_MAX
        sin_filas_viejo = e is not None and e.get("estado") == "sin_filas" and (e.get("lector") or "") != LECTOR
        if e is None or (quedan and (e.get("estado") == "error" or (e.get("estado") == "leido" and fuera_de_plazo(e)) or sin_filas_viejo)):
            out.append(r)
    return out


def _informe_base(r: dict) -> dict:
    return {"nreg": r["nreg"], "isin": r.get("isin", ""), "empresa": r.get("empresa", ""), "fecha_comunicado": (r.get("fecha") or "")[:10],
            "titulo": r.get("texto", ""), "enlace": r.get("enlace", ""), "documento": "", "estado": "error", "intentos": 0, "filas": 0,
            "acciones": 0, "precio_medio": "", "moneda": "", "importe_estimado_eur": "", "desde": "", "hasta": "", "dias": 0, "centros": "",
            "total_declarado": "", "coincide": "", "acciones_programa": "", "importe_programa_eur": "", "pct_programa": "", "pct_capital": "",
            "finalizado": "", "leido": "", "lector": LECTOR}


def informe_desde_textos(r: dict, textos: list[tuple[str, str]], hoy: date) -> tuple[dict, list[dict]]:
    """Construye el registro del comunicado a partir de los textos de sus documentos [(url, texto)]. Usa el primer
    documento con filas; si ninguno las tiene, el acumulado del programa del primero con texto (estado `sin_filas`)."""
    inf = _informe_base(r)
    inf["leido"] = hoy.isoformat()
    ops: list[dict] = []
    elegido = None
    try:
        fecha_com = date.fromisoformat((r.get("fecha") or "")[:10])
    except ValueError:
        fecha_com = None
    for url, texto in textos:
        if not texto.strip():
            continue
        a = analizar(texto, fecha_com)
        if a["filas"] and (elegido is None or not elegido[1]["filas"]):
            elegido = (url, a)
        elif elegido is None:
            elegido = (url, a)
    if elegido is None:
        inf["estado"] = "sin_texto"
        return inf, ops
    url, a = elegido
    inf["documento"] = url
    p = a["programa"]
    for k in ("acciones_programa", "importe_programa_eur", "pct_programa", "pct_capital"):
        inf[k] = "" if p[k] is None else p[k]
    inf["finalizado"] = 1 if p["finalizado"] else 0
    if not a["filas"]:
        inf["estado"] = "sin_filas"
        return inf, ops
    rs = a["resumen"]
    inf["estado"] = "leido"
    inf["filas"] = rs["filas"]
    inf["acciones"] = rs["acciones"]
    monedas = rs["precio_medio"]
    inf["moneda"] = "+".join(sorted(monedas))
    inf["precio_medio"] = monedas.get("EUR", next(iter(monedas.values()), ""))
    eur = [f for f in a["filas"] if f["moneda"] == "EUR" and f["operacion"] == "compra" and not f["detalle"]]
    inf["importe_estimado_eur"] = round(sum(f["acciones"] * f["precio"] for f in eur), 2) if eur else ""
    inf["desde"], inf["hasta"], inf["dias"] = rs["desde"], rs["hasta"], rs["dias"]
    inf["centros"] = "+".join(rs["centros"])
    inf["total_declarado"] = a["declarados"][0] if a["declarados"] else ""
    inf["coincide"] = "" if a["coincide"] is None else (1 if a["coincide"] else 0)
    if a["fuera"]:
        aviso(f"recompras: {inf['empresa']} nreg {inf['nreg']}: {len(a['fuera'])} filas con fecha fuera de la ventana del comunicado "
              f"({', '.join(sorted({x['fecha'] for x in a['fuera']}))}); descartadas")
    if a["coincide"] is False:
        aviso(f"recompras: {inf['empresa']} nreg {inf['nreg']}: la suma de filas ({rs['acciones']}) no coincide con el total declarado {a['declarados']}; a verificar")
    for f in a["filas"]:
        if f["detalle"]:
            continue
        ops.append({"nreg": inf["nreg"], "isin": inf["isin"], "empresa": inf["empresa"], "fecha": f["fecha"], "centro": f["centro"],
                    "operacion": f["operacion"], "acciones": f["acciones"], "precio": f["precio"], "moneda": f["moneda"]})
    return inf, ops


def descargar_textos(sesion, enlace: str) -> list[tuple[str, str]]:
    """Textos de los PDF enlazados desde la página del comunicado en la CNMV (hasta tres documentos)."""
    p = sesion.get(enlace, timeout=60)
    p.raise_for_status()
    textos = []
    for u in enlaces_documentos(p.text)[:3]:
        time.sleep(PAUSA)
        g = sesion.get(u, timeout=120)
        if g.status_code != 200:
            continue
        textos.append((u, texto_pdf(g.content)))
    return textos


def recoger(listado: list[dict], informes: list[dict], operaciones: list[dict], hoy: date, local: Path | None = None,
            maximo: int = MAX_INFORMES, guardar_textos: Path | None = None) -> tuple[list[dict], list[dict], int]:
    """Lee los comunicados pendientes (red, o `<nreg>.txt` de `local`) y actualiza informes y operaciones. Devuelve
    las listas nuevas y cuántos comunicados se han procesado. `guardar_textos` guarda el texto de cada documento
    descargado como `<nreg>[_n].txt` (para depurar maquetas nuevas y construir pruebas)."""
    por_nreg = {i["nreg"]: dict(i) for i in informes}
    ops = [dict(o) for o in operaciones]
    sesion = None
    if local is None:
        import requests
        sesion = requests.Session()
        sesion.headers.update(CABECERAS)
    hechos = 0
    for r in pendientes(listado, informes)[:maximo]:
        previo = por_nreg.get(r["nreg"])
        intentos = int(previo.get("intentos") or 0) + 1 if previo else 1
        try:
            if local is not None:
                ruta = local / f"{r['nreg']}.txt"
                textos = [(f"local:{ruta.name}", ruta.read_text(encoding="utf-8"))] if ruta.exists() else []
            else:
                textos = descargar_textos(sesion, r["enlace"])
                time.sleep(PAUSA)
            if guardar_textos is not None:
                guardar_textos.mkdir(parents=True, exist_ok=True)
                for n, (_, t) in enumerate(textos):
                    (guardar_textos / (f"{r['nreg']}.txt" if n == 0 else f"{r['nreg']}_{n}.txt")).write_text(t, encoding="utf-8")
            inf, nuevas = informe_desde_textos(r, textos, hoy)
        except Exception as e:  # red o lectura: se reintenta en la siguiente pasada
            inf = _informe_base(r)
            inf["estado"] = "error"
            aviso(f"recompras: {r.get('empresa', '')} nreg {r['nreg']}: {type(e).__name__}: {str(e)[:120]} (intento {intentos})")
            nuevas = []
        inf["intentos"] = intentos
        por_nreg[r["nreg"]] = inf
        ops = [o for o in ops if o["nreg"] != r["nreg"]] + nuevas
        hechos += 1
    nuevos = sorted(por_nreg.values(), key=lambda i: (i["fecha_comunicado"], i["nreg"]), reverse=True)
    ops.sort(key=lambda o: (o["fecha"], o["empresa"], o["centro"]), reverse=True)
    return nuevos, ops, hechos


# --------------------------------------------------------------------------- cálculo
def _f(v, default=None):
    try:
        return float(v) if v not in ("", None) else default
    except (TypeError, ValueError):
        return default


def ultimo_por_empresa(informes: list[dict], desde: str) -> list[dict]:
    """El comunicado más reciente de cada empresa con fecha de comunicado >= desde (cualquier estado salvo error)."""
    vistos = {}
    for i in sorted(informes, key=lambda i: (i["fecha_comunicado"], i["nreg"]), reverse=True):
        if i["fecha_comunicado"] < desde or i.get("estado") in ("error", "sin_texto"):
            continue
        vistos.setdefault(i["isin"] or i["empresa"], i)
    return sorted(vistos.values(), key=lambda i: (-(_f(i.get("importe_estimado_eur"), 0) or 0), i["empresa"]))


def serie_semanal(operaciones: list[dict]) -> list[dict]:
    """Por semana ISO (lunes): empresas, acciones e importe estimado en euros de las filas en euros."""
    semanas: dict[str, dict] = {}
    for o in operaciones:
        if o.get("operacion", "compra") != "compra":
            continue
        d = date.fromisoformat(o["fecha"])
        lunes = (d - timedelta(days=d.weekday())).isoformat()
        s = semanas.setdefault(lunes, {"semana": lunes, "empresas": set(), "acciones": 0, "importe_estimado_eur": 0.0})
        s["empresas"].add(o["isin"] or o["empresa"])
        s["acciones"] += int(float(o["acciones"]))
        if o.get("moneda", "EUR") == "EUR":
            s["importe_estimado_eur"] += int(float(o["acciones"])) * float(o["precio"])
    out = []
    for lunes in sorted(semanas):
        s = semanas[lunes]
        out.append({"semana": lunes, "empresas": len(s["empresas"]), "acciones": s["acciones"], "importe_estimado_eur": round(s["importe_estimado_eur"], 2)})
    return out


def percentil(valor: float, historico: list[float]) -> float | None:
    """Percentil (débil) de `valor` entre `historico`; None con menos de SEMANAS_PERCENTIL observaciones."""
    if len(historico) < SEMANAS_PERCENTIL:
        return None
    return round(100.0 * sum(1 for h in historico if h <= valor) / len(historico), 1)


def calcular(informes: list[dict], operaciones: list[dict], hoy: date) -> dict:
    desde_semana = (hoy - timedelta(days=DIAS_SEMANA)).isoformat()
    desde_curso = (hoy - timedelta(days=DIAS_EN_CURSO)).isoformat()
    semana = ultimo_por_empresa(informes, desde_semana)
    en_curso = ultimo_por_empresa(informes, desde_curso)
    serie = serie_semanal(operaciones)
    completas = [s for s in serie if s["semana"] < (hoy - timedelta(days=hoy.weekday())).isoformat()]
    ultima = completas[-1] if completas else None
    pct = percentil(ultima["importe_estimado_eur"], [s["importe_estimado_eur"] for s in completas]) if ultima else None

    def fila(i: dict) -> dict:
        return {"empresa": i["empresa"], "isin": i["isin"], "nreg": i["nreg"], "fecha_comunicado": i["fecha_comunicado"], "titulo": i["titulo"],
                "enlace": i["enlace"], "documento": i["documento"], "estado": i["estado"], "desde": i["desde"] or None, "hasta": i["hasta"] or None,
                "dias": int(i["dias"] or 0), "acciones": int(float(i["acciones"] or 0)), "precio_medio": _f(i["precio_medio"]), "moneda": i["moneda"] or None,
                "importe_estimado_eur": _f(i["importe_estimado_eur"]), "centros": (i["centros"] or "").split("+") if i["centros"] else [],
                "total_declarado": int(float(i["total_declarado"])) if i["total_declarado"] not in ("", None) else None,
                "coincide": None if i["coincide"] in ("", None) else bool(int(i["coincide"])),
                "pct_programa": _f(i["pct_programa"]), "importe_programa_eur": _f(i["importe_programa_eur"]),
                "acciones_programa": int(float(i["acciones_programa"])) if i["acciones_programa"] not in ("", None) else None,
                "pct_capital": _f(i["pct_capital"]), "finalizado": bool(int(i["finalizado"] or 0))}

    semana_f = [fila(i) for i in semana]
    curso_f = [fila(i) for i in en_curso if not int(i.get("finalizado") or 0)]
    terminados = [fila(i) for i in en_curso if int(i.get("finalizado") or 0)]
    leidos = [i for i in informes if i.get("estado") == "leido"]
    return {
        "version": VERSION, "fecha": hoy.isoformat(), "fuente": "CNMV, Otra Información Relevante (informes de operaciones con acciones propias, art. 2 del Reglamento Delegado 2016/1052)",
        "semana": {"desde": desde_semana, "hasta": hoy.isoformat(), "empresas": len(semana_f),
                   "acciones": sum(x["acciones"] for x in semana_f), "importe_estimado_eur": round(sum(x["importe_estimado_eur"] or 0 for x in semana_f), 2),
                   "informes": semana_f},
        "en_curso": {"dias": DIAS_EN_CURSO, "empresas": len(curso_f), "programas": curso_f, "terminados": terminados},
        "serie": {"semanas": serie[-SEMANAS_TABLA:], "n_semanas": len(completas), "ultima_completa": ultima, "percentil_ultima": pct,
                  "desde": serie[0]["semana"] if serie else None},
        "cobertura": {"informes_leidos": len(leidos), "informes_sin_filas": sum(1 for i in informes if i.get("estado") == "sin_filas"),
                      "informes_error": sum(1 for i in informes if i.get("estado") == "error"),
                      "coinciden": sum(1 for i in leidos if i.get("coincide") in (1, "1")), "no_coinciden": sum(1 for i in leidos if i.get("coincide") in (0, "0")),
                      "primer_comunicado": min((i["fecha_comunicado"] for i in informes), default=None)},
        "nota": "Importe estimado = acciones × precio medio ponderado del informe (estimación de El Especulador; el importe exacto figura en cada documento). "
                "Las filas se leen de la tabla diaria de cada informe y se contrastan con el total que declara el documento cuando lo hay.",
    }


def huella(d: dict) -> str:
    """SHA-256 (12 caracteres) del contenido publicado, sin la fecha de la pasada ni los bordes de la ventana de siete
    días: solo cambia si cambian los comunicados, las operaciones o la serie."""
    base = {k: v for k, v in d.items() if k not in ("fecha", "huella")}
    base["semana"] = {k: v for k, v in d["semana"].items() if k not in ("desde", "hasta")}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos y HTML
def _eur(v) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}".replace(".", ",") + " M€"
    return f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _n(v) -> str:
    return "—" if v is None else f"{int(v):,}".replace(",", ".")


def _precio(v, moneda) -> str:
    if v is None:
        return "—"
    simbolo = {"EUR": "€", "GBP": "£", "USD": "USD"}.get((moneda or "EUR").split("+")[0], "")
    return f"{v:.4f}".replace(".", ",") + f" {simbolo}".rstrip()


def _pct(v) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",") + " %"


def _fecha_es(v) -> str:
    v = (v or "")[:10]
    return f"{v[8:10]}/{v[5:7]}/{v[0:4]}" if len(v) == 10 else "—"


def _periodo(x: dict) -> str:
    if not x["desde"]:
        return "sin detalle legible"
    if x["desde"] == x["hasta"]:
        return _fecha_es(x["desde"])
    return f"{_fecha_es(x['desde'])} – {_fecha_es(x['hasta'])}"


def frase_semana(d: dict) -> str:
    s = d["semana"]
    if not s["informes"]:
        return "Ninguna empresa del IBEX 35 ha comunicado compras de acciones propias en los últimos siete días."
    nombres = [x["empresa"] for x in s["informes"][:3]]
    if s["empresas"] > 3:
        lista = ", ".join(nombres) + f" y otras {s['empresas'] - 3}"
    else:
        lista = ", ".join(nombres[:-1]) + (" y " + nombres[-1] if len(nombres) > 1 else nombres[0])
    resto = ""
    return (f"En los últimos siete días, {s['empresas']} {'empresa' if s['empresas'] == 1 else 'empresas'} del IBEX 35 han comunicado compras de "
            f"acciones propias ({lista}{resto}): {_n(s['acciones'])} acciones, unos {_eur(s['importe_estimado_eur'])} estimados a los precios medios de cada informe.")


def fragmento(d: dict) -> str:
    e = html.escape
    h = d.get("huella") or huella(d)

    def importe(x):
        if x["importe_estimado_eur"] is None:
            return "—"
        return _eur(x["importe_estimado_eur"]) + (" (solo euros)" if x["moneda"] and "+" in x["moneda"] else "")

    filas_semana = "".join(
        f"<tr><td><a href='{e(x['enlace'])}' rel='nofollow noopener'>{e(x['empresa'])}</a></td><td>{e(_periodo(x))}</td>"
        f"<td class='n'>{_n(x['acciones']) if x['acciones'] else '—'}</td><td class='n'>{_precio(x['precio_medio'], x['moneda'])}</td>"
        f"<td class='n'>{importe(x)}</td><td class='n'>{_pct(x['pct_programa'])}</td>"
        f"<td>{'a verificar' if x['coincide'] is False else ('sin tabla legible' if x['estado'] == 'sin_filas' else _fecha_es(x['fecha_comunicado']))}</td></tr>"
        for x in d["semana"]["informes"])
    filas_curso = "".join(
        f"<tr><td><a href='{e(x['enlace'])}' rel='nofollow noopener'>{e(x['empresa'])}</a></td><td>{_fecha_es(x['fecha_comunicado'])}</td>"
        f"<td class='n'>{_pct(x['pct_programa'])}</td><td class='n'>{_eur(x['importe_programa_eur'])}</td><td class='n'>{_n(x['acciones_programa'])}</td><td class='n'>{_pct(x['pct_capital'])}</td></tr>"
        for x in d["en_curso"]["programas"])
    terminados = ", ".join(f"{e(x['empresa'])} ({_fecha_es(x['fecha_comunicado'])})" for x in d["en_curso"]["terminados"])
    filas_serie = "".join(
        f"<tr><td>{_fecha_es(s['semana'])}</td><td class='n'>{s['empresas']}</td><td class='n'>{_n(s['acciones'])}</td><td class='n'>{_eur(s['importe_estimado_eur'])}</td></tr>"
        for s in reversed(d["serie"]["semanas"]))
    serie = d["serie"]
    if serie["n_semanas"] >= SEMANAS_PERCENTIL and serie["percentil_ultima"] is not None:
        pct_txt = f"La última semana completa está en el percentil {serie['percentil_ultima']:.0f} de la serie."
    else:
        pct_txt = (f"La serie empieza el {_fecha_es(serie['desde'])}; el percentil histórico se publicará cuando haya {SEMANAS_PERCENTIL} semanas completas "
                   f"(hay {serie['n_semanas']})." if serie["desde"] else "Todavía no hay semanas completas en la serie.")
    cob = d["cobertura"]
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": "Recompras de acciones propias del IBEX 35",
        "description": "Compras de acciones propias comunicadas a la CNMV por las empresas del IBEX 35: acciones, precio medio, importe estimado y ejecución del programa, por semana.",
        "url": f"{WEB}/recompras-ibex-35/", "license": "https://www.cnmv.es/portal/aviso-legal.aspx", "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "El Especulador", "url": WEB}, "dateModified": d["fecha"],
        "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"},
                         {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/operaciones.csv"},
                         {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/semanal.csv"}],
        "temporalCoverage": f"{cob['primer_comunicado']}/{d['fecha']}" if cob["primer_comunicado"] else d["fecha"],
    }, ensure_ascii=False)
    frag = f"""<!-- recompras:inicio {h} -->
<div class="espec-datos espec-recompras">
<p class="espec-resumen">{e(frase_semana(d))}</p>
<h3>Comunicados de los últimos siete días</h3>
<table class="espec-tabla"><thead><tr><th>Empresa</th><th>Periodo del informe</th><th class="n">Acciones</th><th class="n">Precio medio</th><th class="n">Importe estimado</th><th class="n">Programa ejecutado</th><th>Comunicado</th></tr></thead>
<tbody>{filas_semana or '<tr><td colspan="7">Sin comunicados en los últimos siete días.</td></tr>'}</tbody></table>
<h3>Programas en curso (comunicado en los últimos {DIAS_EN_CURSO} días)</h3>
<table class="espec-tabla"><thead><tr><th>Empresa</th><th>Último informe</th><th class="n">Ejecutado del importe máximo</th><th class="n">Importe acumulado</th><th class="n">Acciones acumuladas</th><th class="n">% del capital</th></tr></thead>
<tbody>{filas_curso or '<tr><td colspan="6">Ningún programa con comunicado en el periodo.</td></tr>'}</tbody></table>
{('<p class="espec-nota">Programas terminados en el periodo: ' + terminados + '.</p>') if terminados else ''}
<h3>Ritmo semanal de recompra del IBEX 35 (estimado)</h3>
<table class="espec-tabla"><thead><tr><th>Semana (lunes)</th><th class="n">Empresas</th><th class="n">Acciones</th><th class="n">Importe estimado</th></tr></thead>
<tbody>{filas_serie or '<tr><td colspan="4">Sin operaciones leídas todavía.</td></tr>'}</tbody></table>
<p class="espec-nota">{e(pct_txt)} La semana en curso aparece incompleta hasta que las empresas envían su informe (normalmente el lunes o el martes siguientes).</p>
<h3>Cómo se lee</h3>
<p>Cada empresa con un programa de recompra en marcha envía a la CNMV, como «Otra Información Relevante», un informe con las compras de la semana anterior: fecha, centro de negociación, número de acciones y precio medio ponderado (art. 2 del Reglamento Delegado (UE) 2016/1052). El Especulador lee la tabla diaria de cada informe, suma las acciones y las contrasta con el total que declara el propio documento cuando lo hay; si no coinciden, la fila se marca «a verificar». El importe estimado es acciones × precio medio del informe: una estimación, no la cifra oficial. El porcentaje ejecutado es el que la empresa declara sobre el importe máximo del programa; cuando no lo declara, la casilla queda vacía. Algunas empresas publican la tabla como imagen y no se puede leer: aparecen como «sin tabla legible» con el acumulado que declaren en el texto.</p>
<p class="espec-nota">Históricamente, los programas de recompra reducen el número de acciones en circulación; nada de esta página anticipa lo que hará una cotización ni es una recomendación de inversión. Datos reproducidos fielmente de la CNMV y gratuitos en cnmv.es; informes leídos: {cob['informes_leidos']} (sin tabla legible: {cob['informes_sin_filas']}; sin coincidir con el total declarado: {cob['no_coinciden']}). Actualizado el {_fecha_es(d['fecha'])}.</p>
</div>
<script type="application/ld+json">{jsonld}</script>
<!-- recompras:fin -->
"""
    assert "$" not in frag  # el reemplazo de Make trata el dólar como carácter especial
    return frag


def pagina(d: dict, frag: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recompras de acciones del IBEX 35 | El Especulador</title>
<meta name="description" content="Qué empresas del IBEX 35 comunican compras de acciones propias cada semana, cuántas acciones, a qué precio medio y cuánto llevan ejecutado de su programa.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:980px;margin:0 auto;padding:16px;line-height:1.5}}
h1{{font-size:1.5rem}} h3{{font-size:1.1rem;margin-top:1.4em}} table{{border-collapse:collapse;font-size:.9rem;width:100%;margin:.5em 0}}
th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;vertical-align:top}} th{{background:#f6f8fb}} td.n,th.n{{text-align:right;white-space:nowrap}}
.espec-resumen{{font-size:1.05rem}} .espec-nota{{color:#5b6675;font-size:.88rem}} a{{color:#1f4e8c}}
</style></head><body>
<h1>Recompras de acciones propias del IBEX 35</h1>
{frag}
<p class="espec-nota">Datos: <a href="datos/ultima.json">ultima.json</a> · <a href="datos/operaciones.csv">operaciones.csv</a> · <a href="datos/semanal.csv">semanal.csv</a> · <a href="datos/informes.csv">informes.csv</a>. Versión {VERSION}.</p>
</body></html>
"""


# --------------------------------------------------------------------------- escritura
def _csv(ruta: Path, filas_: list[dict], campos: list[str]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for f in filas_:
            w.writerow({k: f.get(k, "") for k in campos})


def escribir(salida: Path, d: dict, informes: list[dict], operaciones: list[dict], forzar: bool = False) -> bool:
    """Guarda el estado siempre; el fragmento, la página y el JSON solo si cambia la huella (o con --forzar)."""
    datos = salida / "datos"
    datos.mkdir(parents=True, exist_ok=True)
    _csv(datos / "informes.csv", informes, CAMPOS_INFORMES)
    _csv(datos / "operaciones.csv", operaciones, CAMPOS_OPERACIONES)
    _csv(datos / "semanal.csv", serie_semanal(operaciones), ["semana", "empresas", "acciones", "importe_estimado_eur"])
    h = huella(d)
    ruta_json = datos / "ultima.json"
    if ruta_json.exists() and not forzar:
        try:
            if json.loads(ruta_json.read_text(encoding="utf-8")).get("huella") == h:
                return False
        except ValueError:
            pass
    d = dict(d)
    d["huella"] = h
    frag = fragmento(d)
    (salida / "fragmento-wp.html").write_text(frag, encoding="utf-8")
    (salida / "index.html").write_text(pagina(d, frag), encoding="utf-8")
    ruta_json.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Recompras del IBEX 35 (indicador 17)")
    p.add_argument("--salida", default="docs/recompras")
    p.add_argument("--datos", default=None, help="raíz con las salidas de los demás colectores (por defecto, la carpeta madre de --salida)")
    p.add_argument("--cnmv", default=None, help="ruta o URL de cnmv/datos/ibex35.csv (por defecto, <datos>/cnmv/datos/ibex35.csv)")
    p.add_argument("--local", default=None, help="carpeta con ibex35.csv y <nreg>.txt: sin red")
    p.add_argument("--fecha", default=None)
    p.add_argument("--max", type=int, default=MAX_INFORMES, help="comunicados nuevos por pasada")
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--guardar-textos", default=None, help="carpeta donde guardar el texto de cada documento leído (depuración)")
    a = p.parse_args()
    salida = Path(a.salida)
    raiz = Path(a.datos) if a.datos else salida.resolve().parent
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).astimezone().date()
    local = Path(a.local) if a.local else None
    origen = a.cnmv or (str(local / "ibex35.csv") if local else str(raiz / "cnmv" / "datos" / "ibex35.csv"))
    try:
        listado = leer_listado(origen)
        informes, operaciones = cargar_estado(salida / "datos")
        informes, operaciones, hechos = recoger(listado, informes, operaciones, hoy, local=local, maximo=a.max,
                                                guardar_textos=Path(a.guardar_textos) if a.guardar_textos else None)
        if not any(i.get("estado") in ("leido", "sin_filas") for i in informes):
            raise DatosRaros("ningún comunicado de recompra se ha podido leer")
        d = calcular(informes, operaciones, hoy)
        cambia = escribir(salida, d, informes, operaciones, a.forzar)
    except DatosRaros as e:
        print(f"::error::recompras: {e}")
        return 1
    print(f"recompras: {len(listado)} comunicados en el listado, {hechos} procesados en esta pasada, {d['cobertura']['informes_leidos']} leídos en total; "
          f"semana: {d['semana']['empresas']} empresas, {d['semana']['acciones']:,} acciones; {'salida nueva' if cambia else 'sin cambios'}; avisos: {len(AVISOS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
