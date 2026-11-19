"""Ficha integrada por empresa del IBEX 35 (indicador 16): un JSON por empresa y un índice de eventos.

Contrato con el chat de fichas y con Tecnología (catálogo, 18/11/2026): Datos no toca las páginas
/ibex-35/<empresa>/; publica en el servidor

  <salida>/<ISIN>.json       ficha de datos de cada empresa del IBEX 35 (cortos vigentes y cambios, compras y
                             ventas de directivos a 13 semanas, accionistas institucionales, próximo dividendo,
                             recompra en curso, comunicados recientes y lista de eventos con fecha y tipo)
  <salida>/eventos.json      todos los eventos de los últimos 30 días y los anunciados para los 30 siguientes
  <salida>/indice.json       lista de empresas con la huella y la fecha de cada ficha
  <salida>/index.html        página propia con el resumen

No descarga nada: lee las salidas que los demás colectores dejan en la raíz de datos (`--datos`, por defecto la
carpeta madre de `--salida`; en el servidor, $ESPEC_DATOS_DIR):

  cortos/datos/vigentes.csv, historial_cambios.csv, ultima.json      posiciones cortas (CNMV)
  directivos/datos/operaciones.csv, ultima.json                        compras y ventas de directivos (CNMV)
  accionistas/datos/ultima.json                                        participaciones significativas (CNMV)
  dividendos/datos/proximos.csv, ultimos_12m.csv, ultima.json          dividendos (BME)
  cnmv/datos/ibex35.csv, ultima.json                                   comunicados del IBEX 35 (CNMV)

Cada fuente que falte deja su sección en null con estado «ausente» y un aviso; si no hay ninguna, el script
se para sin escribir (DatosRaros). Personas físicas: los accionistas solo se copian si la salida de
`accionistas` ya lleva el filtro de personas jurídicas (campo `fisicas_excluidas`); los tenedores de cortos
son gestoras y los directivos van sin nombre desde su colector.

Uso: python empresas/empresas.py --salida docs/empresas [--datos RAIZ] [--fecha AAAA-MM-DD] [--forzar]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.1.0"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/empresas/"
WEB = "https://elespeculador.com"
DIAS_EVENTOS = 30
SEMANAS_INSIDERS = 13
MAX_ACCIONISTAS = 8
AVISOS: list[str] = []


class DatosRaros(Exception):
    pass


def aviso(texto: str) -> None:
    AVISOS.append(texto)
    print(f"::warning::{texto}")


# --------------------------------------------------------------------------- utilidades
def _csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _num(v) -> float | None:
    if v is None or v == "" or v == "None":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dia(v: str | None) -> str:
    """Primeros diez caracteres de una fecha ISO ('2026-11-06T08:59:25' -> '2026-11-06')."""
    return (v or "")[:10]


def _eur(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",") + " %"


def _fecha_es(v: str | None) -> str:
    v = _dia(v)
    return f"{v[8:10]}/{v[5:7]}/{v[0:4]}" if len(v) == 10 else "—"


def universo() -> list[dict]:
    """Empresas del IBEX 35 con su nombre corto y la ficha de la web (cnmv/empresas.csv); si falta, dividendos/ibex35.csv."""
    raiz = Path(__file__).resolve().parent.parent
    ruta = raiz / "cnmv" / "empresas.csv"
    if ruta.exists():
        return [{"isin": r["isin"].strip(), "empresa": r["nombre"].strip(), "ficha": r["ficha"].strip()} for r in _csv(ruta)]
    ruta = raiz / "dividendos" / "ibex35.csv"
    return [{"isin": r["isin"].strip(), "empresa": r["nombre"].strip(), "ficha": ""} for r in _csv(ruta)]


# --------------------------------------------------------------------------- lectores (una fuente cada uno)
def leer_cortos(raiz: Path, hoy: date) -> tuple[dict, dict]:
    """{isin: {suma_pct, tenedores, posiciones:[...], ultima_fecha, cambios_30d:[...]}}, estado."""
    carpeta = raiz / "cortos" / "datos"
    if not (carpeta / "vigentes.csv").exists():
        return {}, {"estado": "ausente", "fecha": None}
    fecha = None
    if (carpeta / "ultima.json").exists():
        fecha = _json(carpeta / "ultima.json").get("fecha_publicacion")
    por_isin: dict[str, dict] = {}
    for r in _csv(carpeta / "vigentes.csv"):
        pct = _num(r.get("posicion_pct"))
        if pct is None or not r.get("estado", "").startswith("igual o superior"):
            continue
        e = por_isin.setdefault(r["isin"], {"suma_pct": 0.0, "tenedores": 0, "posiciones": [], "ultima_fecha": "", "cambios_30d": []})
        e["posiciones"].append({"tenedor": r["tenedor"], "pct": pct, "fecha": r["fecha_posicion"]})
        e["suma_pct"] = round(e["suma_pct"] + pct, 2)
        e["tenedores"] += 1
        e["ultima_fecha"] = max(e["ultima_fecha"], r["fecha_posicion"])
    desde = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    if (carpeta / "historial_cambios.csv").exists():
        for r in _csv(carpeta / "historial_cambios.csv"):
            if r["fecha_publicacion"] < desde:
                continue
            e = por_isin.setdefault(r["isin"], {"suma_pct": 0.0, "tenedores": 0, "posiciones": [], "ultima_fecha": "", "cambios_30d": []})
            e["cambios_30d"].append({"fecha": r["fecha_publicacion"], "tenedor": r["tenedor"], "tipo": r["tipo"],
                                     "antes_pct": _num(r.get("antes_pct")), "ahora_pct": _num(r.get("ahora_pct"))})
    for e in por_isin.values():
        e["posiciones"].sort(key=lambda p: (-p["pct"], p["tenedor"]))
        e["cambios_30d"].sort(key=lambda c: (c["fecha"], c["tenedor"]), reverse=True)
    return por_isin, {"estado": "ok", "fecha": fecha}


def leer_directivos(raiz: Path, hoy: date) -> tuple[dict, dict]:
    """{isin: {compras_n, ventas_n, compras_eur, ventas_eur, neto_eur, ultima_operacion, recientes:[...]}}, estado."""
    carpeta = raiz / "directivos" / "datos"
    if not (carpeta / "operaciones.csv").exists():
        return {}, {"estado": "ausente", "fecha": None}
    fecha = _json(carpeta / "ultima.json").get("fecha") if (carpeta / "ultima.json").exists() else None
    desde_13 = (hoy - timedelta(weeks=SEMANAS_INSIDERS)).isoformat()
    desde_30 = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    por_isin: dict[str, dict] = {}
    for r in _csv(carpeta / "operaciones.csv"):
        if str(r.get("sustituida", "")) == "1" or r.get("tipo") != "discrecional" or r.get("sentido") not in ("compra", "venta"):
            continue
        e = por_isin.setdefault(r["isin"], {"compras_n": 0, "ventas_n": 0, "compras_eur": 0.0, "ventas_eur": 0.0, "neto_eur": 0.0,
                                            "ultima_operacion": "", "recientes": []})
        importe = _num(r.get("importe_eur")) or 0.0
        if r["fecha_operacion"] >= desde_13:
            if r["sentido"] == "compra":
                e["compras_n"] += 1
                e["compras_eur"] += importe
            else:
                e["ventas_n"] += 1
                e["ventas_eur"] += importe
            e["ultima_operacion"] = max(e["ultima_operacion"], r["fecha_operacion"])
        if r.get("fecha_registro", "") >= desde_30:
            e["recientes"].append({"fecha_registro": r["fecha_registro"], "fecha_operacion": r["fecha_operacion"], "sentido": r["sentido"],
                                   "cargo_tipo": r.get("cargo_tipo", ""), "importe_eur": round(importe, 2) if importe else None,
                                   "documento": r.get("documento", "")})
    for e in por_isin.values():
        e["compras_eur"] = round(e["compras_eur"], 2)
        e["ventas_eur"] = round(e["ventas_eur"], 2)
        e["neto_eur"] = round(e["compras_eur"] - e["ventas_eur"], 2)
        e["recientes"].sort(key=lambda o: (o["fecha_registro"], o["fecha_operacion"]), reverse=True)
    return por_isin, {"estado": "ok", "fecha": fecha}


def leer_accionistas(raiz: Path) -> tuple[dict, dict]:
    """{isin: {fecha, derechos_voto, principales:[{accionista, total_pct, fecha}], fisicas_excluidas}}, estado.
    Solo se copian las empresas cuya salida ya lleva el filtro de personas jurídicas (campo `fisicas_excluidas`)."""
    ruta = raiz / "accionistas" / "datos" / "ultima.json"
    if not ruta.exists():
        return {}, {"estado": "ausente", "fecha": None}
    j = _json(ruta)
    por_isin: dict[str, dict] = {}
    sin_filtro = 0
    for e in j.get("empresas", []):
        if e.get("fuera"):
            continue
        if "fisicas_excluidas" not in e:
            sin_filtro += 1
            continue
        filas = [f for f in e.get("accionistas", []) if (f.get("total") or 0) > 0]
        filas.sort(key=lambda f: (-(f.get("total") or 0), f.get("accionista", "")))
        por_isin[e["isin"]] = {"fecha": e.get("fecha_derechos_voto") or e.get("consulta", ""), "derechos_voto": e.get("derechos_voto"),
                               "principales": [{"accionista": f["accionista"], "total_pct": f["total"], "fecha": f.get("fecha", "")} for f in filas[:MAX_ACCIONISTAS]],
                               "n": len(filas), "fisicas_excluidas": e.get("fisicas_excluidas", 0)}
    estado = {"estado": "ok", "fecha": j.get("fecha")}
    if sin_filtro:
        estado["estado"] = "parcial"
        aviso(f"accionistas: {sin_filtro} empresas sin el filtro de personas jurídicas; no se copian a la ficha")
    return por_isin, estado


def leer_dividendos(raiz: Path, hoy: date) -> tuple[dict, dict]:
    """{isin: {proximo:{fecha_ex, fecha_pago, bruto, moneda, concepto}, ultimos_12m:{pagos, bruto_total, ultima_fecha_ex}, anunciados:[...]}}."""
    carpeta = raiz / "dividendos" / "datos"
    if not (carpeta / "proximos.csv").exists():
        return {}, {"estado": "ausente", "fecha": None}
    fecha = None
    if (carpeta / "ultima.json").exists():
        j = _json(carpeta / "ultima.json")
        fecha = j.get("fecha") or j.get("hoy") or _dia(j.get("generado"))
    por_isin: dict[str, dict] = {}
    h = hoy.isoformat()
    for r in _csv(carpeta / "proximos.csv"):
        fx = _dia(r.get("fecha_ex"))
        if not fx or fx < h:
            continue
        e = por_isin.setdefault(r["isin"], {"proximo": None, "ultimos_12m": None, "anunciados": []})
        d = {"fecha_ex": fx, "fecha_pago": _dia(r.get("fecha_pago")) or None, "bruto": _num(r.get("bruto")), "moneda": r.get("moneda", "EUR"),
             "concepto": r.get("concepto", ""), "extraordinario": str(r.get("extraordinario", "")).lower() in ("true", "1"),
             "flexible": str(r.get("flexible", "")).lower() in ("true", "1")}
        e["anunciados"].append(d)
    if (carpeta / "ultimos_12m.csv").exists():
        for r in _csv(carpeta / "ultimos_12m.csv"):
            e = por_isin.setdefault(r["isin"], {"proximo": None, "ultimos_12m": None, "anunciados": []})
            e["ultimos_12m"] = {"pagos": int(_num(r.get("pagos")) or 0), "bruto_total": _num(r.get("bruto_total")), "ultima_fecha_ex": _dia(r.get("ultima_fecha_ex"))}
    for e in por_isin.values():
        e["anunciados"].sort(key=lambda d: d["fecha_ex"])
        e["proximo"] = e["anunciados"][0] if e["anunciados"] else None
    return por_isin, {"estado": "ok", "fecha": fecha}


def leer_cnmv(raiz: Path, hoy: date) -> tuple[dict, dict]:
    """{isin: {recompra:{...}|None, resultados:{...}|None, comunicados_30d:[...]}}, estado."""
    carpeta = raiz / "cnmv" / "datos"
    if not (carpeta / "ibex35.csv").exists():
        return {}, {"estado": "ausente", "fecha": None}
    fecha = _json(carpeta / "ultima.json").get("actualizado") if (carpeta / "ultima.json").exists() else None
    desde = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    por_isin: dict[str, dict] = {}
    for r in _csv(carpeta / "ibex35.csv"):
        if not r.get("isin"):
            continue
        e = por_isin.setdefault(r["isin"], {"recompra": None, "resultados": None, "comunicados_30d": []})
        c = {"fecha": _dia(r["fecha"]), "caja": r.get("caja", ""), "etiqueta": r.get("etiqueta", ""), "periodo": r.get("periodo", ""),
             "texto": r.get("texto", ""), "enlace": r.get("enlace", ""), "nreg": r.get("nreg", "")}
        if c["caja"] == "recompras" and (e["recompra"] is None or c["fecha"] > e["recompra"]["fecha"]):
            e["recompra"] = c
        if c["caja"] == "resultados" and (e["resultados"] is None or c["fecha"] > e["resultados"]["fecha"]):
            e["resultados"] = c
        if c["fecha"] >= desde:
            e["comunicados_30d"].append(c)
    for e in por_isin.values():
        e["comunicados_30d"].sort(key=lambda c: (c["fecha"], c["nreg"]), reverse=True)
    return por_isin, {"estado": "ok", "fecha": fecha}


# --------------------------------------------------------------------------- ficha y eventos
TIPOS_EVENTO = {
    "corto_nueva": "Nueva posición corta publicada", "corto_sube": "Sube una posición corta", "corto_baja": "Baja una posición corta",
    "corto_sale": "Una posición corta deja de publicarse", "insider_compra": "Compra de un directivo o consejero",
    "insider_venta": "Venta de un directivo o consejero", "dividendo_ex": "Fecha ex del dividendo", "dividendo_pago": "Pago del dividendo",
    "comunicado_recompras": "Comunicado de recompra", "comunicado_resultados": "Resultados", "comunicado_dividendos": "Comunicado de dividendo",
    "comunicado_opvs": "Comunicado de OPV o ampliación", "comunicado_otro": "Comunicado a la CNMV",
}
CARGO = {"consejero": "un consejero", "directivo": "un directivo", "vinculada": "una persona vinculada"}


def eventos_de(isin: str, empresa: str, ficha: str, c: dict | None, d: dict | None, dv: dict | None, cn: dict | None, hoy: date) -> list[dict]:
    """Eventos con fecha entre hoy-30 y hoy+30 días, a partir de las cinco fuentes."""
    desde = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    hasta = (hoy + timedelta(days=DIAS_EVENTOS)).isoformat()
    url_ficha = f"{WEB}/ibex-35/{ficha}/" if ficha else ""
    ev: list[dict] = []

    def add(fecha, tipo, titulo, detalle, url, fuente):
        if desde <= fecha <= hasta:
            ev.append({"fecha": fecha, "tipo": tipo, "isin": isin, "empresa": empresa, "ficha": url_ficha, "titulo": titulo,
                       "detalle": detalle, "url": url, "fuente": fuente})

    for x in (c or {}).get("cambios_30d", []):
        tipo = {"nueva": "corto_nueva", "sube": "corto_sube", "baja": "corto_baja"}.get(x["tipo"], "corto_sale")
        if tipo == "corto_sale":
            detalle = f"{x['tenedor']} deja de publicar su posición (antes {_pct(x['antes_pct'])})."
        elif tipo == "corto_nueva":
            detalle = f"{x['tenedor']} publica una posición corta del {_pct(x['ahora_pct'])}."
        else:
            detalle = f"{x['tenedor']} pasa del {_pct(x['antes_pct'])} al {_pct(x['ahora_pct'])}."
        add(x["fecha"], tipo, f"{TIPOS_EVENTO[tipo]} en {empresa}", detalle, f"{WEB}/posiciones-cortas/", "CNMV, posiciones cortas")
    for o in (d or {}).get("recientes", []):
        tipo = "insider_compra" if o["sentido"] == "compra" else "insider_venta"
        quien = CARGO.get(o["cargo_tipo"], "un directivo")
        importe = f" por {_eur(o['importe_eur'])}" if o["importe_eur"] else ""
        add(o["fecha_registro"], tipo, f"{TIPOS_EVENTO[tipo]} en {empresa}",
            f"{o['sentido'].capitalize()} discrecional de {quien}{importe} (operación del {_fecha_es(o['fecha_operacion'])}).",
            o.get("documento") or f"{WEB}/compras-y-ventas-de-directivos/", "CNMV, notificaciones de directivos")
    for x in (dv or {}).get("anunciados", []):
        bruto = f"{x['bruto']:.4f}".rstrip("0").rstrip(".").replace(".", ",") + f" {x['moneda']}" if x["bruto"] is not None else "importe por confirmar"
        add(x["fecha_ex"], "dividendo_ex", f"Fecha ex del dividendo de {empresa}", f"{bruto} brutos por acción ({x['concepto'] or 'dividendo'}).",
            f"{WEB}/calendario-de-dividendos/", "BME")
        if x["fecha_pago"]:
            add(x["fecha_pago"], "dividendo_pago", f"Pago del dividendo de {empresa}", f"{bruto} brutos por acción.", f"{WEB}/calendario-de-dividendos/", "BME")
    for x in (cn or {}).get("comunicados_30d", []):
        tipo = f"comunicado_{x['caja']}" if f"comunicado_{x['caja']}" in TIPOS_EVENTO else "comunicado_otro"
        add(x["fecha"], tipo, f"{TIPOS_EVENTO[tipo]}: {empresa}", x["texto"], x["enlace"], "CNMV")
    ev.sort(key=lambda e: (e["fecha"], e["tipo"], e["titulo"]), reverse=True)
    return ev


def huella_de(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def ficha(emp: dict, fuentes: dict, estados: dict, hoy: date) -> dict:
    isin, empresa, slug = emp["isin"], emp["empresa"], emp.get("ficha", "")
    c = fuentes["cortos"].get(isin)
    d = fuentes["directivos"].get(isin)
    a = fuentes["accionistas"].get(isin)
    dv = fuentes["dividendos"].get(isin)
    cn = fuentes["cnmv"].get(isin)
    cuerpo = {
        "isin": isin, "empresa": empresa, "ficha": f"{WEB}/ibex-35/{slug}/" if slug else None,
        "cortos": None if estados["cortos"]["estado"] == "ausente" else {
            "suma_pct": (c or {}).get("suma_pct", 0.0), "tenedores": (c or {}).get("tenedores", 0),
            "posiciones": (c or {}).get("posiciones", []), "ultima_fecha": (c or {}).get("ultima_fecha") or None,
            "cambios_30d": (c or {}).get("cambios_30d", [])},
        "directivos": None if estados["directivos"]["estado"] == "ausente" else {
            "semanas": SEMANAS_INSIDERS, **{k: (d or {}).get(k, 0 if k.endswith(("_n", "_eur")) else None)
                                           for k in ("compras_n", "ventas_n", "compras_eur", "ventas_eur", "neto_eur", "ultima_operacion")},
            "operaciones_30d": len((d or {}).get("recientes", []))},
        "accionistas": None if a is None else {
            "fecha": a["fecha"], "derechos_voto": a["derechos_voto"], "n": a["n"], "principales": a["principales"],
            "nota": f"Solo personas jurídicas; {a['fisicas_excluidas']} participaciones de personas físicas no se publican." if a["fisicas_excluidas"] else "Solo personas jurídicas."},
        "dividendo": None if estados["dividendos"]["estado"] == "ausente" else {
            "proximo": (dv or {}).get("proximo"), "ultimos_12m": (dv or {}).get("ultimos_12m")},
        "recompra": None if estados["cnmv"]["estado"] == "ausente" else {
            "ultimo_comunicado": (cn or {}).get("recompra"),
            "en_curso": bool((cn or {}).get("recompra") and (cn or {})["recompra"]["fecha"] >= (hoy - timedelta(days=45)).isoformat())},
        "resultados": None if estados["cnmv"]["estado"] == "ausente" else (cn or {}).get("resultados"),
        "comunicados_30d": (cn or {}).get("comunicados_30d", []) if estados["cnmv"]["estado"] != "ausente" else [],
        "eventos": eventos_de(isin, empresa, slug, c, d, dv, cn, hoy),
    }
    cuerpo["huella"] = huella_de(cuerpo)
    cuerpo["version"] = VERSION
    cuerpo["fecha"] = hoy.isoformat()
    cuerpo["fuentes"] = estados
    cuerpo["licencia"] = ("El Especulador, a partir de datos de la CNMV (posiciones cortas, notificaciones de directivos, participaciones "
                          "significativas y comunicados, reproducidos fielmente) y de BME (dividendos, sujetos a sus condiciones). "
                          "Datos con fin informativo y educativo; no son una recomendación de inversión.")
    return cuerpo


# --------------------------------------------------------------------------- salida
def pagina(fichas: list[dict], eventos: dict, hoy: date) -> str:
    e = html.escape
    filas = []
    for f in sorted(fichas, key=lambda x: x["empresa"].lower()):
        c, d, dv, r = f["cortos"], f["directivos"], f["dividendo"], f["recompra"]
        prox = (dv or {}).get("proximo")
        filas.append(
            f"<tr><td>{e(f['empresa'])} <span class='isin'>{e(f['isin'])}</span></td>"
            f"<td class='n'>{_pct(c['suma_pct']) if c else '—'}</td>"
            f"<td class='n'>{(str(d['compras_n']) + ' / ' + str(d['ventas_n'])) if d else '—'}</td>"
            f"<td>{_fecha_es(prox['fecha_ex']) if prox else '—'}</td>"
            f"<td>{'Sí (' + _fecha_es(r['ultimo_comunicado']['fecha']) + ')' if r and r['en_curso'] else ('No' if r else '—')}</td>"
            f"<td class='n'>{len(f['eventos'])}</td><td><a href='{e(f['isin'])}.json'>JSON</a></td></tr>")
    estados = fichas[0]["fuentes"] if fichas else {}
    est = " · ".join(f"{k}: {v['estado']}" + (f" ({_fecha_es(v['fecha'])})" if v.get('fecha') else "") for k, v in estados.items())
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fichas de datos del IBEX 35 | El Especulador</title>
<meta name="description" content="Un JSON por empresa del IBEX 35 con cortos, operaciones de directivos, accionistas, dividendos, recompras y eventos recientes.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0;width:100%}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}}
th{{background:#f6f8fb}} td.n,th.n{{text-align:right}} .isin{{color:#5b6675;font-size:.8rem}} a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Fichas de datos del IBEX 35</h1>
<p>Generado el {_fecha_es(hoy.isoformat())}. {len(fichas)} empresas; {eventos['n']} eventos entre el {_fecha_es(eventos['desde'])} y el {_fecha_es(eventos['hasta'])} (<a href="eventos.json">eventos.json</a>, <a href="indice.json">indice.json</a>). Fuentes: {e(est)}.</p>
<table><thead><tr><th>Empresa</th><th class="n">Cortos publicados</th><th class="n">Compras / ventas de directivos (13 sem.)</th><th>Próxima fecha ex</th><th>Recompra en curso</th><th class="n">Eventos</th><th>Ficha</th></tr></thead>
<tbody>
{chr(10).join(filas)}
</tbody></table>
<p class="pie">Datos de la CNMV (posiciones cortas, notificaciones de directivos, participaciones significativas, comunicados) y de BME (dividendos), reproducidos fielmente por El Especulador con fin informativo y educativo. Sin recomendación de inversión. Versión {VERSION}.</p>
</body></html>
"""


def escribir(fichas: list[dict], hoy: date, salida: Path, forzar: bool = False) -> dict:
    """Escribe cada ficha solo si su huella cambia (o con --forzar); siempre eventos.json, indice.json e index.html si algo cambia."""
    salida.mkdir(parents=True, exist_ok=True)
    cambiadas, iguales = [], []
    for f in fichas:
        ruta = salida / f"{f['isin']}.json"
        if ruta.exists() and not forzar:
            try:
                if _json(ruta).get("huella") == f["huella"]:
                    iguales.append(f["isin"])
                    continue
            except (ValueError, OSError):
                pass
        ruta.write_text(json.dumps(f, ensure_ascii=False, indent=1), encoding="utf-8")
        cambiadas.append(f["isin"])
    todos = sorted((ev for f in fichas for ev in f["eventos"]), key=lambda e: (e["fecha"], e["empresa"], e["tipo"]), reverse=True)
    eventos = {"version": VERSION, "fecha": hoy.isoformat(), "desde": (hoy - timedelta(days=DIAS_EVENTOS)).isoformat(),
               "hasta": (hoy + timedelta(days=DIAS_EVENTOS)).isoformat(), "n": len(todos), "tipos": TIPOS_EVENTO, "eventos": todos}
    eventos["huella"] = huella_de(todos)
    ruta_ev = salida / "eventos.json"
    ev_cambia = forzar or not ruta_ev.exists() or _json(ruta_ev).get("huella") != eventos["huella"]
    if ev_cambia:
        ruta_ev.write_text(json.dumps(eventos, ensure_ascii=False, indent=1), encoding="utf-8")
    if cambiadas or ev_cambia or not (salida / "index.html").exists() or forzar:
        indice = {"version": VERSION, "fecha": hoy.isoformat(), "empresas": [{"isin": f["isin"], "empresa": f["empresa"], "ficha": f["ficha"],
                  "huella": f["huella"], "eventos": len(f["eventos"]), "json": f"{PAGES}{f['isin']}.json"} for f in sorted(fichas, key=lambda x: x["empresa"].lower())]}
        (salida / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
        (salida / "index.html").write_text(pagina(fichas, eventos, hoy), encoding="utf-8")
    return {"cambiadas": cambiadas, "iguales": iguales, "eventos": len(todos), "eventos_cambia": ev_cambia}


def generar(raiz: Path, hoy: date) -> list[dict]:
    """Lee las cinco fuentes y devuelve las fichas de todo el universo. Para si no hay ninguna fuente."""
    fuentes, estados = {}, {}
    fuentes["cortos"], estados["cortos"] = leer_cortos(raiz, hoy)
    fuentes["directivos"], estados["directivos"] = leer_directivos(raiz, hoy)
    fuentes["accionistas"], estados["accionistas"] = leer_accionistas(raiz)
    fuentes["dividendos"], estados["dividendos"] = leer_dividendos(raiz, hoy)
    fuentes["cnmv"], estados["cnmv"] = leer_cnmv(raiz, hoy)
    ausentes = [k for k, v in estados.items() if v["estado"] == "ausente"]
    if len(ausentes) == len(estados):
        raise DatosRaros(f"ninguna fuente disponible en {raiz}")
    for k in ausentes:
        aviso(f"{k}: salida ausente en {raiz / k}; la ficha sale sin esa sección")
    emp = universo()
    if not emp:
        raise DatosRaros("universo vacío: ni cnmv/empresas.csv ni dividendos/ibex35.csv")
    return [ficha(e, fuentes, estados, hoy) for e in emp]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--salida", default="docs/empresas")
    p.add_argument("--datos", default=None, help="raíz con las salidas de los demás colectores (por defecto, la carpeta madre de --salida)")
    p.add_argument("--fecha", default=None)
    p.add_argument("--forzar", action="store_true")
    a = p.parse_args()
    salida = Path(a.salida)
    raiz = Path(a.datos) if a.datos else salida.resolve().parent
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).astimezone().date()
    try:
        fichas = generar(raiz, hoy)
        res = escribir(fichas, hoy, salida, a.forzar)
    except DatosRaros as e:
        print(f"::error::empresas: {e}")
        return 1
    print(f"empresas: {len(fichas)} fichas, {len(res['cambiadas'])} cambiadas, {len(res['iguales'])} iguales, {res['eventos']} eventos"
          f"{' (eventos.json nuevo)' if res['eventos_cambia'] else ''}; avisos: {len(AVISOS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
