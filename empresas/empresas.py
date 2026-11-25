"""Ficha integrada por empresa del IBEX 35 (indicador 16): un JSON por empresa y un índice de eventos.

Contrato con el chat de fichas de Tecnología (versión 1.0, 21/11/2026; catálogo de Datos): Datos no toca las páginas
/ibex35/<empresa>/; publica en el servidor

  <salida>/<ISIN>.json       ficha de datos de cada empresa del IBEX 35: registro oficial (comunicados a la CNMV de doce
                             meses), dividendos comunicados a la CNMV (sin rentabilidad), posiciones cortas, compras y
                             ventas de directivos a 13 semanas, accionistas (solo personas jurídicas), recompra en curso,
                             cuatro fuerzas y perfil (tablas mantenidas a mano), eventos de ±30 días
  <salida>/eventos.json      todos los eventos de los últimos 30 días y los anunciados para los 30 siguientes
  <salida>/indice.json       lista de empresas con la huella de cada ficha y la fecha de la última pasada
  <salida>/cambios.csv       registro de cambios de cada cifra (fecha, ISIN, campo, antes, después, fuente)
  <salida>/index.html        página propia con el resumen

No descarga nada: lee las salidas que los demás colectores dejan en la raíz de datos (`--datos`, por defecto la
carpeta madre de `--salida`; en el servidor, $ESPEC_DATOS_DIR), más dos tablas del repositorio:

  cortos/datos/vigentes.csv, historial_cambios.csv, ultima.json      posiciones cortas (CNMV)
  directivos/datos/operaciones.csv, ultima.json                        compras y ventas de directivos (CNMV)
  accionistas/datos/ultima.json                                        participaciones significativas (CNMV)
  cnmv/datos/ibex35.csv, dividendos.csv, ultima.json                   comunicados del IBEX 35 y sus dividendos (CNMV)
  empresas/cuatro_fuerzas.csv, empresas/perfil.csv                     tablas de Datos con la fuente de cada cifra

Nada de BME: ni dividendos, ni rentabilidades, ni precios (21/11/2026).

Si un colector falla, su bloque conserva el último dato bueno de la ficha anterior, con estado «anterior» y su
fecha; si nunca hubo dato, el bloque va vacío (null o lista vacía) y la ficha de la web lo oculta. Si no hay
ninguna fuente, el script se para sin escribir (DatosRaros). Personas físicas: los accionistas solo se copian si
la salida de `accionistas` ya lleva el filtro de personas jurídicas (campo `fisicas_excluidas`); en los cortos,
un tenedor que no se reconozca como persona jurídica sale sin nombre y con aviso; los directivos van sin nombre
desde su colector.

Uso: python empresas/empresas.py --salida docs/empresas [--datos RAIZ] [--fecha AAAA-MM-DD] [--forzar]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "1.2.1"
CONTRATO = "1.0"          # cambia solo si cambian los campos que lee la ficha de la web
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/empresas/"
WEB = "https://elespeculador.com"
FICHAS = f"{WEB}/ibex35/"          # direcciones reales de las fichas (hijas de la página 8258), comprobadas el 21/11/2026
PAGINA_CORTOS = f"{WEB}/posiciones-cortas-hoy/"
AQUI = Path(__file__).resolve().parent
CUATRO_FUERZAS = AQUI / "cuatro_fuerzas.csv"
PERFIL = AQUI / "perfil.csv"
DIAS_EVENTOS = 30
DIAS_REGISTRO = 365
ALCANCE_REGISTRO = ("Comunicados a la CNMV de resultados, dividendos, recompras, ampliaciones y OPV, y OPA "
                    "(información privilegiada y otra información relevante), de los últimos doce meses")
LECTURA = {"completa": "leído del comunicado", "parcial": "parcial: el resto, en el comunicado",
           "flexible: ver comunicado": "dividendo flexible: el importe depende de la opción del accionista; ver el comunicado",
           "flexible: completa": "dividendo flexible: efectivo por acción para quien elige cobrar en efectivo y su fecha de pago, leídos "
                                 "del comunicado; quien elige acciones nuevas cobra en acciones (más el dividendo de ajuste, si lo hay)",
           "flexible: parcial": "dividendo flexible: lo leído es el efectivo por acción para quien elige cobrar en efectivo o su fecha "
                                "de pago; el resto, en el comunicado",
           "sin pago: ver comunicado": "anuncio de política de dividendos, sin un pago concreto: ver el comunicado",
           "sin documento": "sin leer: ver el comunicado", "sin datos": "sin leer: ver el comunicado"}
SEMANAS_INSIDERS = 13
MAX_ACCIONISTAS = 8
FUENTE = {"registro_oficial": "CNMV, comunicados de información privilegiada y otra información relevante",
          "dividendos": "CNMV, comunicados de las empresas", "cortos": "CNMV, registro de posiciones cortas netas",
          "directivos": "CNMV, notificaciones de operaciones de directivos", "accionistas": "CNMV, participaciones significativas",
          "recompra": "CNMV, comunicados de las empresas"}
# Qué bloques de la ficha salen de cada colector (para conservar el último dato bueno si ese colector falla)
BLOQUES = {"cnmv": ("registro_oficial", "dividendos", "recompra"), "cortos": ("cortos",), "directivos": ("directivos",),
           "accionistas": ("accionistas",)}
EVENTOS_DE = {"cnmv": ("comunicado_", "dividendo_"), "cortos": ("corto_",), "directivos": ("insider_",), "accionistas": ("-",)}
# Tenedores de cortos que son entidades aunque su nombre no lleve forma societaria
TENEDORES_ENTIDAD = ("CAISSE DE DEPOT ET PLACEMENT DU QUEBEC",)
SIN_NOMBRE = "Tenedor no identificado como persona jurídica (nombre no publicado)"
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
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None   # sin NaN ni infinitos: JSON válido


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


def _persona_juridica():
    """La regla del colector de accionistas (accionistas/duenos.py), sin copiarla: una sola definición."""
    ruta = AQUI.parent / "accionistas" / "duenos.py"
    spec = importlib.util.spec_from_file_location("duenos_para_empresas", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.persona_juridica


_REGLA_JURIDICA = None


def es_entidad(nombre: str) -> bool:
    """Persona jurídica según la regla del colector de accionistas, o entidad conocida sin forma societaria."""
    global _REGLA_JURIDICA
    if _REGLA_JURIDICA is None:
        _REGLA_JURIDICA = _persona_juridica()
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", nombre or "") if not unicodedata.combining(c)).upper()
    return _REGLA_JURIDICA(nombre) or any(e in sin_tildes for e in TENEDORES_ENTIDAD)


def universo() -> list[dict]:
    """Empresas del IBEX 35 con su nombre corto y la ficha de la web (cnmv/empresas.csv); si falta, dividendos/ibex35.csv."""
    raiz = AQUI.parent
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
    sin_nombre: set[str] = set()

    def nombre(t: str) -> str:
        if es_entidad(t):
            return t
        sin_nombre.add(t)
        return SIN_NOMBRE

    por_isin: dict[str, dict] = {}
    for r in _csv(carpeta / "vigentes.csv"):
        pct = _num(r.get("posicion_pct"))
        if pct is None or not r.get("estado", "").startswith("igual o superior"):
            continue
        e = por_isin.setdefault(r["isin"], {"suma_pct": 0.0, "tenedores": 0, "posiciones": [], "ultima_fecha": "", "cambios_30d": []})
        e["posiciones"].append({"tenedor": nombre(r["tenedor"]), "pct": pct, "fecha": r["fecha_posicion"]})
        e["suma_pct"] = round(e["suma_pct"] + pct, 2)
        e["tenedores"] += 1
        e["ultima_fecha"] = max(e["ultima_fecha"], r["fecha_posicion"])
    desde = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    if (carpeta / "historial_cambios.csv").exists():
        for r in _csv(carpeta / "historial_cambios.csv"):
            if r["fecha_publicacion"] < desde:
                continue
            e = por_isin.setdefault(r["isin"], {"suma_pct": 0.0, "tenedores": 0, "posiciones": [], "ultima_fecha": "", "cambios_30d": []})
            e["cambios_30d"].append({"fecha": r["fecha_publicacion"], "tenedor": nombre(r["tenedor"]), "tipo": r["tipo"],
                                     "antes_pct": _num(r.get("antes_pct")), "ahora_pct": _num(r.get("ahora_pct"))})
    for e in por_isin.values():
        e["posiciones"].sort(key=lambda p: (-p["pct"], p["tenedor"]))
        e["cambios_30d"].sort(key=lambda c: (c["fecha"], c["tenedor"]), reverse=True)
    if sin_nombre:
        aviso(f"cortos: {len(sin_nombre)} tenedores sin forma de persona jurídica salen sin nombre; revisar (Cumplimiento si fueran "
              f"personas físicas): {sorted(sin_nombre)}")
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


def leer_cnmv(raiz: Path, hoy: date) -> tuple[dict, dict]:
    """{isin: {registro:[...], dividendos:[...], recompra:{...}|None}}, estado. Comunicados clasificados de doce meses."""
    carpeta = raiz / "cnmv" / "datos"
    if not (carpeta / "ibex35.csv").exists():
        return {}, {"estado": "ausente", "fecha": None}
    ultima = _json(carpeta / "ultima.json") if (carpeta / "ultima.json").exists() else {}
    fecha = ultima.get("actualizado")
    desde = (hoy - timedelta(days=DIAS_REGISTRO)).isoformat()
    # El registro es completo desde la fecha más reciente de las dos «desde» del histórico (IP y OIR); con el
    # relleno hacia atrás terminado, desde hace doce meses.
    hist = ultima.get("historico") or {}
    desde_hist = max((v.get("desde") or "" for v in hist.values()), default="") if hist else ""
    if hist and all(v.get("completo") for v in hist.values()):
        desde_hist = desde
    leidos = {}
    if (carpeta / "dividendos.csv").exists():
        leidos = {(r["canal"], r["nreg"]): r for r in _csv(carpeta / "dividendos.csv")}
    por_isin: dict[str, dict] = {}
    titulos: dict[tuple[str, str], str] = {}
    for r in _csv(carpeta / "ibex35.csv"):
        if not r.get("isin"):
            continue
        titulos[(r.get("canal", ""), r.get("nreg", ""))] = r.get("texto", "") or r.get("categoria", "")
        e = por_isin.setdefault(r["isin"], {"registro": [], "dividendos": [], "recompra": None, "completos": []})
        c = {"fecha": _dia(r["fecha"]), "tipo": (r.get("etiqueta", "") + (" " + r["periodo"] if r.get("periodo") else "")).strip(),
             "caja": r.get("caja", ""), "titulo": r.get("texto", "") or r.get("categoria", ""), "fuente": "CNMV",
             "enlace": r.get("enlace", ""), "nreg": r.get("nreg", ""), "canal": r.get("canal", ""), "grupo": r.get("grupo", "")}
        if c["caja"] == "recompras" and (e["recompra"] is None or c["fecha"] > e["recompra"]["fecha"]):
            e["recompra"] = c
        if c["fecha"] < desde or c["fecha"] > hoy.isoformat():
            continue
        e["registro"].append(c)
        if c["caja"] == "dividendos":
            # Importe, moneda y fechas solo si cnmv/dividendos_cnmv.py los ha leído con seguridad del propio comunicado;
            # si no, el anuncio con su enlace. Nunca rentabilidad.
            d = leidos.get((c["canal"], c["nreg"]), {})
            e["dividendos"].append({"fecha_comunicado": c["fecha"], "tipo": r.get("etiqueta", ""), "titulo": c["titulo"],
                                    "importe": _num(d.get("importe_bruto")), "moneda": d.get("moneda") or None,
                                    "fecha_ex": d.get("fecha_ex") or None, "fecha_registro": d.get("fecha_registro") or None,
                                    "fecha_pago": d.get("fecha_pago") or None,
                                    "lectura": LECTURA.get(d.get("extraccion", ""), "sin leer: ver el comunicado"),
                                    "fuente": "CNMV", "enlace": c["enlace"], "nreg": c["nreg"]})
            e["completos"].append(COMPLETO.get(d.get("extraccion", ""), False))
    # Dividendos anunciados dentro de los resultados (empresas de la lista cerrada de cnmv/dividendo_en_resultados.csv,
    # Inditex, Logista y Naturgy): un dividendo por pago, con el enlace a la nota de resultados que lo anuncia; un dividendo
    # propuesto sin fecha (Logista, complementario) sale sin fechas, con su importe.
    if (carpeta / "dividendos_resultados.csv").exists():
        for d in _csv(carpeta / "dividendos_resultados.csv"):
            if not d.get("isin") or not (desde <= d.get("fecha_comunicado", "") <= hoy.isoformat()):
                continue
            e = por_isin.setdefault(d["isin"], {"registro": [], "dividendos": [], "recompra": None, "completos": []})
            completa = d.get("extraccion") == "completa"
            que = f"dividendo {d['concepto']} anunciado en los resultados" if d.get("concepto") else "anunciado en los resultados"
            e["dividendos"].append({"fecha_comunicado": d["fecha_comunicado"], "tipo": "Dividendo",
                                    "titulo": titulos.get((d.get("canal", ""), d.get("nreg", ""))) or "Resultados",
                                    "importe": _num(d.get("importe_bruto")), "moneda": d.get("moneda") or None,
                                    "fecha_ex": d.get("fecha_ex") or None, "fecha_registro": d.get("fecha_registro") or None,
                                    "fecha_pago": d.get("fecha_pago") or None,
                                    "lectura": f"{que}: " + lectura_resultados(d.get("extraccion", "")),
                                    "fuente": "CNMV", "enlace": d.get("enlace", ""), "nreg": d.get("nreg", "")})
            e["completos"].append(completa)
    for e in por_isin.values():
        e["registro"].sort(key=lambda c: (c["fecha"], c["canal"], int(c["nreg"] or 0)), reverse=True)
        e["dividendos"].sort(key=lambda d: (d["fecha_comunicado"], int(d["nreg"] or 0), d["fecha_pago"] or ""), reverse=True)
        e["estado_dividendos"] = estado_dividendos(e.pop("completos"))
    return por_isin, {"estado": "ok", "fecha": fecha, "desde": desde_hist or None}


# Estado del bloque de dividendos de cada empresa (24/11/2026; antes era el del colector cnmv para todas):
#   «vacio»   sin comunicados de dividendo en doce meses;
#   «ok»      todos sus pagos leídos del comunicado (importe y fechas; en un flexible, el efectivo y su fecha de pago);
#   «parcial» algún pago remite al comunicado, o solo hay anuncios de política de dividendos.
# Los anuncios de política (sin un pago concreto) no cuentan como pago ni como pendiente.
def lectura_resultados(extraccion: str) -> str:
    """Cómo se leyó un dividendo anunciado en una nota de resultados (cnmv/dividendos_cnmv.py, formatos de la lista cerrada)."""
    if extraccion == "completa":
        return "leído del comunicado"
    if extraccion == "solo pago":
        return "importe y fecha de pago leídos de la nota, que no da la fecha ex"
    if extraccion.startswith("anunciado:"):
        return "propuesto, pendiente de la junta; " + extraccion.split(":", 1)[1].strip() + ", sin fecha exacta"
    return "parcial: el resto, en el comunicado"


COMPLETO = {"completa": True, "flexible: completa": True, "sin pago: ver comunicado": None}


def estado_dividendos(completos: list) -> str:
    if not completos:
        return "vacio"
    pagos = [c for c in completos if c is not None]
    return "ok" if pagos and all(pagos) else "parcial"


def leer_tabla(ruta: Path, columnas: tuple[str, ...]) -> tuple[dict[str, list[dict]], dict]:
    """Tabla de Datos mantenida a mano (cuatro fuerzas, perfil): {isin: [filas]}, estado («pendiente» si no tiene filas)."""
    if not ruta.exists():
        return {}, {"estado": "pendiente", "fecha": None}
    filas = _csv(ruta)
    falta = [c for c in columnas if filas and c not in filas[0]]
    if falta:
        raise DatosRaros(f"{ruta.name}: faltan columnas {falta}")
    por_isin: dict[str, list[dict]] = {}
    for r in filas:
        if r.get("isin"):
            por_isin.setdefault(r["isin"].strip(), []).append({k: (r.get(k) or "").strip() for k in columnas if k != "isin"})
    fechas = [r.get("fecha", "") for r in filas if r.get("fecha")]
    return por_isin, {"estado": "ok" if por_isin else "pendiente", "fecha": max(fechas) if fechas else None}


COLUMNAS_FUERZAS = ("isin", "fuerza", "indicador", "cifra", "unidad", "texto", "ejercicio", "fuente", "pagina", "enlace",
                    "fecha", "verificado_por", "verificado_el")
COLUMNAS_PERFIL = ("isin", "sede", "cierre_ejercicio", "web_ri", "fuente", "fecha")


# --------------------------------------------------------------------------- ficha y eventos
TIPOS_EVENTO = {
    "corto_nueva": "Nueva posición corta publicada", "corto_sube": "Sube una posición corta", "corto_baja": "Baja una posición corta",
    "corto_sale": "Una posición corta deja de publicarse", "insider_compra": "Compra de un directivo o consejero",
    "insider_venta": "Venta de un directivo o consejero",
    "dividendo_ex": "Fecha ex-dividendo", "dividendo_pago": "Pago de dividendo",
    "comunicado_recompras": "Comunicado de recompra", "comunicado_resultados": "Resultados", "comunicado_dividendos": "Comunicado de dividendo",
    "comunicado_opvs-ampliaciones": "Comunicado de OPV o ampliación", "comunicado_opas": "Comunicado sobre una OPA",
    "comunicado_otro": "Comunicado a la CNMV",
}
CARGO = {"consejero": "un consejero", "directivo": "un directivo", "vinculada": "una persona vinculada"}


def eventos_de(isin: str, empresa: str, ficha: str, c: dict | None, d: dict | None, cn: dict | None, hoy: date) -> list[dict]:
    """Eventos con fecha entre hoy-30 y hoy+30 días, a partir de las fuentes de este día."""
    desde = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat()
    hasta = (hoy + timedelta(days=DIAS_EVENTOS)).isoformat()
    url_ficha = f"{FICHAS}{ficha}/" if ficha else ""
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
        add(x["fecha"], tipo, f"{TIPOS_EVENTO[tipo]} en {empresa}", detalle, PAGINA_CORTOS, FUENTE["cortos"])
    for o in (d or {}).get("recientes", []):
        tipo = "insider_compra" if o["sentido"] == "compra" else "insider_venta"
        quien = CARGO.get(o["cargo_tipo"], "un directivo")
        importe = f" por {_eur(o['importe_eur'])}" if o["importe_eur"] else ""
        add(o["fecha_registro"], tipo, f"{TIPOS_EVENTO[tipo]} en {empresa}",
            f"{o['sentido'].capitalize()} discrecional de {quien}{importe} (operación del {_fecha_es(o['fecha_operacion'])}).",
            o.get("documento") or "", FUENTE["directivos"])
    for x in (cn or {}).get("registro", []):
        tipo = f"comunicado_{x['caja']}" if f"comunicado_{x['caja']}" in TIPOS_EVENTO else "comunicado_otro"
        add(x["fecha"], tipo, f"{TIPOS_EVENTO[tipo]}: {empresa}", x["titulo"], x["enlace"], "CNMV")
    # Un mismo dividendo puede anunciarse dos veces (anuncio y recordatorio, o el importe aprobado y luego el ajustado
    # por la autocartera): misma fecha e importe igual, a menos de un 5 % o sin importe en uno de los dos. Da un solo
    # evento, con los datos del comunicado más reciente que tenga importe.
    divs: dict = {}
    for x in sorted((cn or {}).get("dividendos", []), key=lambda d: (d["fecha_comunicado"], int(d["nreg"]))):
        for campo, tipo in (("fecha_ex", "dividendo_ex"), ("fecha_pago", "dividendo_pago")):
            if not x.get(campo):
                continue
            clave = next((k for k in divs if k[:2] == (tipo, x[campo]) and _mismo_importe(divs[k].get("importe"), x.get("importe"))),
                         (tipo, x[campo], len(divs)))
            if clave not in divs or x.get("importe") or not divs[clave].get("importe"):
                divs[clave] = x
    for (tipo, fecha, _), x in divs.items():
        importe = f"{_importe_es(x['importe'])} {'€' if x['moneda'] == 'EUR' else x['moneda']} brutos por acción" \
            if x.get("importe") and x.get("moneda") else "importe en el comunicado"
        otra = x.get("fecha_pago") if tipo == "dividendo_ex" else x.get("fecha_ex")
        if x.get("tipo") == "Dividendo flexible":   # el importe es el efectivo para quien lo elige
            inicio = f"Dividendo flexible: {importe} en efectivo para quien lo elige" if x.get("importe") and x.get("moneda") \
                else "Dividendo flexible: pago del efectivo a quien lo elige; importe en el comunicado"
        else:
            inicio = f"Dividendo de {importe}"
        detalle = inicio + (f"; {'pago' if tipo == 'dividendo_ex' else 'ex-dividendo'} el {_fecha_es(otra)}" if otra else "") + "."
        add(fecha, tipo, f"{TIPOS_EVENTO[tipo]}: {empresa}", detalle, x["enlace"], "CNMV")
    ev.sort(key=lambda e: (e["fecha"], e["tipo"], e["titulo"]), reverse=True)
    return ev


FIN_RECOMPRA = (" finalizacion ", " finaliza ", " fin del programa ", " fin de programa ", " conclusion ", " concluido ",
                " concluye ", " terminado ", " termina ", " completado ")


def fin_de_programa(titulo: str) -> bool:
    """«Finalización del Programa de Recompra y próxima reducción de capital» (Santander, 28/10/2026): ya no está en curso."""
    t = "".join(c for c in unicodedata.normalize("NFKD", titulo or "") if not unicodedata.combining(c)).lower()
    t = " " + re.sub(r"[^a-z0-9]+", " ", t) + " "
    return any(w in t for w in FIN_RECOMPRA)


def _mismo_importe(a, b) -> bool:
    return a is None or b is None or abs(a - b) <= 0.05 * max(a, b)


def _importe_es(v: float) -> str:
    """Importe por acción tal como lo da el comunicado, sin redondear (5,74867096) ni ceros de más (0,2)."""
    return f"{v:.8f}".rstrip("0").rstrip(".").replace(".", ",")


def huella_de(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def ficha(emp: dict, fuentes: dict, estados: dict, hoy: date, previa: dict | None = None) -> dict:
    isin, empresa, slug = emp["isin"], emp["empresa"], emp.get("ficha", "")
    c = fuentes["cortos"].get(isin)
    d = fuentes["directivos"].get(isin)
    a = fuentes["accionistas"].get(isin)
    cn = fuentes["cnmv"].get(isin)
    fz = fuentes["cuatro_fuerzas"].get(isin, [])
    pf = (fuentes["perfil"].get(isin) or [None])[0]
    cuerpo = {
        "contrato": CONTRATO, "empresa": empresa, "isin": isin, "ficha": f"{FICHAS}{slug}/" if slug else None,
        "registro_oficial": [{k: x[k] for k in ("fecha", "tipo", "titulo", "fuente", "enlace", "nreg", "grupo")} for x in (cn or {}).get("registro", [])],
        "dividendos": (cn or {}).get("dividendos", []),
        "cortos": None if estados["cortos"]["estado"] == "ausente" else {
            "total_publicado": (c or {}).get("suma_pct", 0.0), "fecha_dato": estados["cortos"]["fecha"],
            "tenedores": (c or {}).get("tenedores", 0), "posiciones": (c or {}).get("posiciones", []),
            "ultima_posicion": (c or {}).get("ultima_fecha") or None, "cambios_30d": (c or {}).get("cambios_30d", []),
            "fuente": FUENTE["cortos"]},
        "directivos": None if estados["directivos"]["estado"] == "ausente" else {
            "semanas": SEMANAS_INSIDERS, **{k: (d or {}).get(k, 0 if k.endswith(("_n", "_eur")) else None)
                                           for k in ("compras_n", "ventas_n", "compras_eur", "ventas_eur", "neto_eur", "ultima_operacion")},
            "operaciones_30d": len((d or {}).get("recientes", [])), "fecha_dato": estados["directivos"]["fecha"], "fuente": FUENTE["directivos"]},
        "accionistas": None if a is None else {
            "fecha_derechos_voto": a["fecha"], "derechos_voto": a["derechos_voto"], "n": a["n"], "principales": a["principales"],
            "fecha_dato": estados["accionistas"]["fecha"],
            "nota": f"Solo personas jurídicas; {a['fisicas_excluidas']} participaciones de personas físicas no se publican." if a["fisicas_excluidas"] else "Solo personas jurídicas.",
            "fuente": FUENTE["accionistas"]},
        "recompra": None if estados["cnmv"]["estado"] == "ausente" else {
            "ultimo_comunicado": (cn or {}).get("recompra"),
            # en curso: comunicado de recompra de los últimos 45 días que no anuncia el final del programa
            "en_curso": bool((cn or {}).get("recompra") and (cn or {})["recompra"]["fecha"] >= (hoy - timedelta(days=45)).isoformat()
                             and not fin_de_programa((cn or {})["recompra"]["titulo"])),
            "fecha_dato": _dia(estados["cnmv"]["fecha"]) or None, "fuente": FUENTE["recompra"]},
        "cuatro_fuerzas": fz,
        "perfil": pf,
        "eventos": eventos_de(isin, empresa, slug, c, d, cn, hoy),
    }
    por_bloque = {
        "registro_oficial": {**estados["cnmv"], "alcance": ALCANCE_REGISTRO}, "recompra": dict(estados["cnmv"]),
        # el de dividendos es el de la empresa (estado_dividendos) cuando el colector ha ido bien
        "dividendos": {**estados["cnmv"], "estado": (cn or {}).get("estado_dividendos", "vacio")} if estados["cnmv"]["estado"] == "ok"
        else dict(estados["cnmv"]),
        "cortos": dict(estados["cortos"]), "directivos": dict(estados["directivos"]),
        "accionistas": dict(estados["accionistas"]) if a is not None or estados["accionistas"]["estado"] == "ausente"
        else {"estado": "vacio", "fecha": estados["accionistas"]["fecha"]},
        "cuatro_fuerzas": dict(estados["cuatro_fuerzas"]) if fz else {"estado": "pendiente", "fecha": None},
        "perfil": dict(estados["perfil"]) if pf else {"estado": "pendiente", "fecha": None},
    }
    # Último dato bueno: si un colector falta hoy y la ficha anterior tenía sus bloques, se conservan, marcados «anterior».
    for fuente, bloques in BLOQUES.items():
        if estados[fuente]["estado"] != "ausente" or not previa:
            continue
        antes = (previa.get("fuentes") or {})
        # basta el primer bloque de la fuente (el registro oficial, en la CNMV): el de dividendos puede ir «vacio» en una
        # empresa sin dividendos con el colector funcionando
        if (antes.get(bloques[0]) or {}).get("estado") not in ("ok", "parcial", "anterior") or not all(b in antes for b in bloques):
            continue
        for b in bloques:
            cuerpo[b] = previa.get(b)
            por_bloque[b] = {**antes[b], "estado": "anterior"}
        desde, hasta = (hoy - timedelta(days=DIAS_EVENTOS)).isoformat(), (hoy + timedelta(days=DIAS_EVENTOS)).isoformat()
        cuerpo["eventos"] += [e for e in previa.get("eventos", []) if e["tipo"].startswith(EVENTOS_DE[fuente]) and desde <= e["fecha"] <= hasta]
        cuerpo["eventos"].sort(key=lambda e: (e["fecha"], e["tipo"], e["titulo"]), reverse=True)
    for b, est in por_bloque.items():
        if est["estado"] == "ausente":
            est["estado"] = "vacio"
    cuerpo["huella"] = huella_de(cuerpo)
    cuerpo["version"] = VERSION
    cuerpo["actualizado"] = hoy.isoformat()
    cuerpo["fuentes"] = por_bloque
    cuerpo["licencia"] = ("El Especulador, a partir de datos de la CNMV (comunicados, posiciones cortas, notificaciones de directivos y "
                          "participaciones significativas), reproducidos fielmente; gratuitos en cnmv.es. Cuatro fuerzas y perfil: "
                          "cada cifra con su documento y página.")
    cuerpo["aviso"] = "Datos con fin informativo y educativo; no son una recomendación de inversión."
    return cuerpo


# --------------------------------------------------------------------------- registro de cambios
def cifras(f: dict) -> dict[str, str]:
    """Las cifras de una ficha que se vigilan en cambios.csv, con una clave estable por cifra."""
    out: dict[str, str] = {}
    c = f.get("cortos")
    if c:
        out["cortos.total_publicado"], out["cortos.tenedores"] = str(c["total_publicado"]), str(c["tenedores"])
        for p in c.get("posiciones", []):
            out[f"cortos.posicion[{p['tenedor']}]"] = str(p["pct"])
    d = f.get("directivos")
    if d:
        for k in ("compras_n", "ventas_n", "compras_eur", "ventas_eur", "neto_eur"):
            out[f"directivos.{k}"] = str(d[k])
    a = f.get("accionistas")
    if a:
        out["accionistas.derechos_voto"] = str(a["derechos_voto"])
        for p in a.get("principales", []):
            out[f"accionistas.participacion[{p['accionista']}]"] = str(p["total_pct"])
    for x in f.get("dividendos", []):
        for k in ("importe", "fecha_ex", "fecha_pago"):
            if x.get(k) is not None:
                out[f"dividendos[{x['nreg']}].{k}"] = str(x[k])
    if f.get("recompra"):
        out["recompra.en_curso"] = str(f["recompra"]["en_curso"])
    for x in f.get("cuatro_fuerzas", []):
        out[f"cuatro_fuerzas[{x.get('fuerza')}/{x.get('indicador')}]"] = f"{x.get('cifra')} {x.get('unidad')}".strip()
    for k, v in (f.get("perfil") or {}).items():
        if k in ("sede", "cierre_ejercicio", "web_ri"):
            out[f"perfil.{k}"] = v
    return out


def _fuente_de(campo: str) -> str:
    b = campo.split(".")[0].split("[")[0]
    return FUENTE.get(b, "tabla de Datos con documento y página" if b in ("cuatro_fuerzas", "perfil") else "")


def cambios_de(antes: dict, despues: dict, hoy: date) -> list[dict]:
    a, d = cifras(antes), cifras(despues)
    filas = []
    for campo in sorted(set(a) | set(d)):
        if a.get(campo) != d.get(campo):
            filas.append({"fecha": hoy.isoformat(), "isin": despues["isin"], "empresa": despues["empresa"], "campo": campo,
                          "antes": a.get(campo, ""), "despues": d.get(campo, ""), "fuente": _fuente_de(campo)})
    return filas


# --------------------------------------------------------------------------- salida
def pagina(fichas: list[dict], eventos: dict, hoy: date) -> str:
    e = html.escape
    filas = []
    for f in sorted(fichas, key=lambda x: x["empresa"].lower()):
        c, d, r = f["cortos"], f["directivos"], f["recompra"]
        filas.append(
            f"<tr><td>{e(f['empresa'])} <span class='isin'>{e(f['isin'])}</span></td>"
            f"<td class='n'>{_pct(c['total_publicado']) if c else '—'}</td>"
            f"<td class='n'>{(str(d['compras_n']) + ' / ' + str(d['ventas_n'])) if d else '—'}</td>"
            f"<td class='n'>{len(f['dividendos'])}</td>"
            f"<td>{'Sí (' + _fecha_es(r['ultimo_comunicado']['fecha']) + ')' if r and r['en_curso'] else ('No' if r else '—')}</td>"
            f"<td class='n'>{len(f['registro_oficial'])}</td><td class='n'>{len(f['eventos'])}</td><td><a href='{e(f['isin'])}.json'>JSON</a></td></tr>")
    estados = fichas[0]["fuentes"] if fichas else {}
    est = " · ".join(f"{k}: {v['estado']}" + (f" ({_fecha_es(v['fecha'])})" if v.get('fecha') else "") for k, v in estados.items())
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fichas de datos del IBEX 35 | El Especulador</title>
<meta name="description" content="Un JSON por empresa del IBEX 35 con su registro oficial en la CNMV, dividendos comunicados, posiciones cortas, operaciones de directivos, accionistas, recompras y eventos recientes.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0;width:100%}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}}
th{{background:#f6f8fb}} td.n,th.n{{text-align:right}} .isin{{color:#5b6675;font-size:.8rem}} a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Fichas de datos del IBEX 35</h1>
<p>Generado el {_fecha_es(hoy.isoformat())}. {len(fichas)} empresas; {eventos['n']} eventos entre el {_fecha_es(eventos['desde'])} y el {_fecha_es(eventos['hasta'])} (<a href="eventos.json">eventos.json</a>, <a href="indice.json">indice.json</a>, <a href="cambios.csv">cambios.csv</a>). Estado de cada bloque: {e(est)}.</p>
<table><thead><tr><th>Empresa</th><th class="n">Cortos publicados</th><th class="n">Compras / ventas de directivos (13 sem.)</th><th class="n">Anuncios de dividendo (12 meses)</th><th>Recompra en curso</th><th class="n">Comunicados (12 meses)</th><th class="n">Eventos</th><th>Ficha</th></tr></thead>
<tbody>
{chr(10).join(filas)}
</tbody></table>
<p class="pie">Datos de la CNMV (comunicados, posiciones cortas, notificaciones de directivos, participaciones significativas), reproducidos fielmente por El Especulador con fin informativo y educativo; gratuitos en cnmv.es. Sin recomendación de inversión. Contrato {CONTRATO}, versión {VERSION}.</p>
</body></html>
"""


def _escribir_json(ruta: Path, obj: dict) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")   # JSON estricto
    os.replace(tmp, ruta)


def escribir(fichas: list[dict], hoy: date, salida: Path, forzar: bool = False) -> dict:
    """Escribe cada ficha solo si su huella cambia (o con --forzar) y anota en cambios.csv cada cifra que cambia;
    indice.json en cada pasada (fecha de comprobación); eventos.json e index.html si algo cambia."""
    salida.mkdir(parents=True, exist_ok=True)
    cambiadas, iguales, registro = [], [], []
    for f in fichas:
        ruta = salida / f"{f['isin']}.json"
        previa = None
        if ruta.exists():
            try:
                previa = _json(ruta)
            except (ValueError, OSError):
                previa = None
        if previa and previa.get("huella") == f["huella"] and not forzar:
            iguales.append(f["isin"])
            continue
        if previa and previa.get("contrato") == CONTRATO:
            registro += cambios_de(previa, f, hoy)
        _escribir_json(ruta, f)
        cambiadas.append(f["isin"])
    if registro:
        ruta_c = salida / "cambios.csv"
        nuevo = not ruta_c.exists()
        with ruta_c.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["fecha", "isin", "empresa", "campo", "antes", "despues", "fuente"])
            if nuevo:
                w.writeheader()
            w.writerows(registro)
    todos = sorted((ev for f in fichas for ev in f["eventos"]), key=lambda e: (e["fecha"], e["empresa"], e["tipo"]), reverse=True)
    eventos = {"version": VERSION, "contrato": CONTRATO, "fecha": hoy.isoformat(), "desde": (hoy - timedelta(days=DIAS_EVENTOS)).isoformat(),
               "hasta": (hoy + timedelta(days=DIAS_EVENTOS)).isoformat(), "n": len(todos), "tipos": TIPOS_EVENTO, "eventos": todos}
    eventos["huella"] = huella_de(todos)
    ruta_ev = salida / "eventos.json"
    ev_cambia = forzar or not ruta_ev.exists() or _json(ruta_ev).get("huella") != eventos["huella"]
    if ev_cambia:
        _escribir_json(ruta_ev, eventos)
    indice = {"version": VERSION, "contrato": CONTRATO, "comprobado": hoy.isoformat(),
              "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "fuentes": fichas[0]["fuentes"] if fichas else {},
              "empresas": [{"isin": f["isin"], "empresa": f["empresa"], "ficha": f["ficha"], "huella": f["huella"],
                            "eventos": len(f["eventos"]), "json": f"{PAGES}{f['isin']}.json"} for f in sorted(fichas, key=lambda x: x["empresa"].lower())]}
    _escribir_json(salida / "indice.json", indice)
    if cambiadas or ev_cambia or not (salida / "index.html").exists() or forzar:
        (salida / "index.html").write_text(pagina(fichas, eventos, hoy), encoding="utf-8")
    return {"cambiadas": cambiadas, "iguales": iguales, "eventos": len(todos), "eventos_cambia": ev_cambia, "cambios": len(registro)}


def generar(raiz: Path, hoy: date, salida: Path | None = None) -> list[dict]:
    """Lee las fuentes y devuelve las fichas de todo el universo. Para si no hay ninguna fuente de colector."""
    fuentes, estados = {}, {}
    fuentes["cortos"], estados["cortos"] = leer_cortos(raiz, hoy)
    fuentes["directivos"], estados["directivos"] = leer_directivos(raiz, hoy)
    fuentes["accionistas"], estados["accionistas"] = leer_accionistas(raiz)
    fuentes["cnmv"], estados["cnmv"] = leer_cnmv(raiz, hoy)
    ausentes = [k for k in BLOQUES if estados[k]["estado"] == "ausente"]
    if len(ausentes) == len(BLOQUES):
        raise DatosRaros(f"ninguna fuente disponible en {raiz}")
    for k in ausentes:
        aviso(f"{k}: salida ausente en {raiz / k}; la ficha conserva el último dato bueno de ese bloque, si lo hay")
    fuentes["cuatro_fuerzas"], estados["cuatro_fuerzas"] = leer_tabla(CUATRO_FUERZAS, COLUMNAS_FUERZAS)
    perfil, estados["perfil"] = leer_tabla(PERFIL, COLUMNAS_PERFIL)
    fuentes["perfil"] = perfil
    emp = universo()
    if not emp:
        raise DatosRaros("universo vacío: ni cnmv/empresas.csv ni dividendos/ibex35.csv")
    out = []
    for e in emp:
        previa = None
        if salida is not None and (salida / f"{e['isin']}.json").exists():
            try:
                previa = _json(salida / f"{e['isin']}.json")
            except (ValueError, OSError):
                previa = None
        out.append(ficha(e, fuentes, estados, hoy, previa))
    return out


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
        fichas = generar(raiz, hoy, salida)
        res = escribir(fichas, hoy, salida, a.forzar)
    except DatosRaros as e:
        print(f"::error::empresas: {e}")
        return 1
    print(f"empresas: {len(fichas)} fichas, {len(res['cambiadas'])} cambiadas, {len(res['iguales'])} iguales, {res['eventos']} eventos"
          f"{' (eventos.json nuevo)' if res['eventos_cambia'] else ''}, {res['cambios']} cifras cambiadas; avisos: {len(AVISOS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
