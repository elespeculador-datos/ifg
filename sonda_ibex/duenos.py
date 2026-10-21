"""Los dueños del IBEX 35: los accionistas significativos de cada empresa, según la CNMV.

Fuente: el registro de participaciones significativas de la CNMV («Notificaciones de
derechos de voto e instrumentos financieros» de cada emisor), que recoge la última
notificación de cada accionista obligado a comunicar (Real Decreto 1362/2007). La lista
de las 35 del índice sale de la lista de cotizadas de BME (campo de índices).

Cómo se llega a cada ficha: la CNMV no admite enlaces fijos por NIF; hay que buscar la
entidad por su nombre (formulario ASP.NET), elegirla si salen varias y seguir el enlace de
la ficha, que lleva un identificador de un solo uso. Por eso se busca cada vez.

Comprobaciones antes de publicar:
- cada empresa española del IBEX debe devolver la tabla de accionistas; si la CNMV falla con
  alguna, se usan sus datos de la última consulta buena y el flujo avisa; con más de 5 fallos,
  no se publica nada;
- los porcentajes deben ser números entre 0 y 100 y el total (A+B) cuadrar con A + B;
- las empresas con domicilio fuera de España (Ferrovial, ArcelorMittal) no se toman de la
  CNMV: sus participaciones se comunican al supervisor de su país y la tabla de la CNMV
  estaría incompleta.

Los nombres de los accionistas se reproducen tal y como los publica la CNMV.

Uso:
  python accionistas/duenos.py --salida docs/accionistas
  python accionistas/duenos.py --salida DIR --local consulta.json     (sin red, para probar)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

BME = "https://apiweb.bolsasymercados.es/Market/v1/EQ/ListedCompanies"
CAB_BME = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/",
           "Origin": "https://www.bolsasymercados.es"}
CNMV_BUSQUEDA = "https://www.cnmv.es/portal/Consultas/Busqueda?id=7"
CNMV_FICHA = "https://www.cnmv.es/portal/consultas/DerechosVoto/Notificaciones-Participaciones.aspx?qS="
CAB_CNMV = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124 Safari/537.36 (El Especulador, datos abiertos)", "Accept-Language": "es-ES,es;q=0.9"}
PAGINA_WP = "https://elespeculador.com/accionistas-ibex-35/"
METODOLOGIA = PAGINA_WP + "#como-se-hace"
PAGES = "https://elespeculador-datos.github.io/ifg/accionistas/"
MAX_FALLOS = 5
PAUSA = 2.0  # segundos entre consultas a la CNMV

# ISIN -> (nombre corto, texto que se busca en la CNMV, comienzo del nombre en la CNMV)
EMPRESAS = {
    "ES0125220311": ("Acciona", "ACCIONA", "ACCIONA, S.A."),
    "ES0105563003": ("Acciona Energía", "ACCIONA ENERGIAS", "CORPORACION ACCIONA ENERGIAS RENOVABLES"),
    "ES0132105018": ("Acerinox", "ACERINOX", "ACERINOX, S.A."),
    "ES0167050915": ("ACS", "ACTIVIDADES DE CONSTRUCCION", "ACS, ACTIVIDADES DE CONSTRUCCION Y SERVICIOS"),
    "ES0105046017": ("Aena", "AENA", "AENA, S.M.E., S.A."),
    "ES0109067019": ("Amadeus", "AMADEUS", "AMADEUS IT GROUP"),
    "ES0113860A34": ("Banco Sabadell", "BANCO DE SABADELL", "BANCO DE SABADELL, S.A."),
    "ES0113900J37": ("Banco Santander", "BANCO SANTANDER, S.A.", "BANCO SANTANDER, S.A."),
    "ES0113679I37": ("Bankinter", "BANKINTER", "BANKINTER, S.A."),
    "ES0113211835": ("BBVA", "BANCO BILBAO VIZCAYA", "BANCO BILBAO VIZCAYA ARGENTARIA"),
    "ES0140609019": ("CaixaBank", "CAIXABANK, S.A.", "CAIXABANK, S.A."),
    "ES0105066007": ("Cellnex", "CELLNEX", "CELLNEX TELECOM"),
    "ES0139140174": ("Colonial", "COLONIAL SFL", "COLONIAL SFL"),
    "ES0130960018": ("Enagás", "ENAGAS, S.A.", "ENAGAS, S.A."),
    "ES0130670112": ("Endesa", "ENDESA", "ENDESA, S.A."),
    "ES0137650018": ("Fluidra", "FLUIDRA", "FLUIDRA, S.A."),
    "ES0171996087": ("Grifols", "GRIFOLS, S.A.", "GRIFOLS, S.A."),
    "ES0177542018": ("IAG", "INTERNATIONAL CONSOLIDATED", "INTERNATIONAL CONSOLIDATED AIRLINES"),
    "ES0144580Y14": ("Iberdrola", "IBERDROLA, S.A.", "IBERDROLA, S.A."),
    "ES0148396007": ("Inditex", "TEXTIL", "INDUSTRIA DE DISE"),
    "ES0118594417": ("Indra", "INDRA", "INDRA SISTEMAS"),
    "ES0105027009": ("Logista", "LOGISTA", "LOGISTA INTEGRAL"),
    "ES0124244E34": ("Mapfre", "MAPFRE, S.A.", "MAPFRE, S.A."),
    "ES0105025003": ("Merlin Properties", "MERLIN PROPERTIES, SOCIMI, S.A.", "MERLIN PROPERTIES"),
    "ES0116870314": ("Naturgy", "NATURGY ENERGY GROUP, S.A.", "NATURGY ENERGY GROUP"),
    "ES0105777017": ("Puig", "PUIG", "PUIG BRANDS"),
    "ES0173093024": ("Redeia", "REDEIA CORPORACION, S.A.", "REDEIA CORPORACION"),
    "ES0173516115": ("Repsol", "REPSOL, S.A.", "REPSOL, S.A."),
    "ES0157261019": ("Rovi", "LABORATORIOS FARMACEUTICOS ROVI, S.A.", "LABORATORIOS FARMACEUTICOS ROVI"),
    "ES0182870214": ("Sacyr", "SACYR, S.A.", "SACYR, S.A."),
    "ES0165386014": ("Solaria", "SOLARIA", "SOLARIA ENERGIA"),
    "ES0178430E18": ("Telefónica", "TELEFONICA, S.A.", "TELEFONICA, S.A."),
    "ES0180907000": ("Unicaja", "UNICAJA BANCO, S.A.", "UNICAJA BANCO"),
}
# Domicilio social fuera de España: sus participaciones significativas se comunican al supervisor de su país.
FUERA = {
    "NL0015001FS8": ("Ferrovial", "Países Bajos", "la AFM, el supervisor neerlandés"),
    "LU1598757687": ("ArcelorMittal", "Luxemburgo", "la CSSF, el supervisor luxemburgués"),
}
COLUMNAS = {"Denominación": "accionista", "% Total (A)": "acciones", "% Directo": "directo", "% Indirecto": "indirecto",
            "% (B)": "instrumentos", "(A+B)": "total", "F.Registro Entrada CNMV": "fecha", "Información adicional": "info"}


class DatosRaros(Exception):
    pass


AVISOS: list[str] = []


def _limpiar(x: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def _sin_tildes(x: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", x.upper()) if unicodedata.category(c) != "Mn")


def _num_cnmv(x: str) -> float | None:
    x = (x or "").strip()
    if not x:
        return None
    if not re.fullmatch(r"\d{1,3},\d{1,4}", x):
        raise DatosRaros(f"porcentaje con formato inesperado: {x!r}")
    return float(x.replace(",", "."))


def _pct(x: float | None, dec: int = 3) -> str:
    return "—" if x is None else f"{x:.{dec}f}".replace(".", ",") + " %"


def _iso(d: str) -> str:
    """DD/MM/AAAA -> AAAA-MM-DD."""
    return f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if re.fullmatch(r"\d\d/\d\d/\d{4}", d or "") else ""


def _f(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


# --------------------------------------------------------------------------- descargas
def lista_ibex() -> list[dict]:
    for i in range(3):
        try:
            r = requests.get(BME, params={"tradingSystem": "SIBE", "page": 0, "pageSize": 0}, headers=CAB_BME, timeout=60)
            r.raise_for_status()
            j = r.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(5 * (i + 1))
    else:
        raise DatosRaros("BME no devuelve la lista de cotizadas")
    ibex = [{"isin": c["isin"], "nombre_bme": c["name"]} for c in j.get("data", []) if "IBEX 35" in (c.get("indices") or "")]
    if not 33 <= len(ibex) <= 37:
        raise DatosRaros(f"la lista de BME da {len(ibex)} valores del IBEX 35")
    return ibex


def _pedir(s: requests.Session, metodo: str, url: str, **kw) -> requests.Response | None:
    for i in range(3):
        try:
            r = s.request(metodo, url, timeout=90, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(8 * (i + 1))
    return None


def _ocultos(t: str) -> dict:
    return {m.group(1): html.unescape(m.group(2))
            for m in re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', t)}


def _guid(t: str) -> str | None:
    m = re.search(r'Notificaciones-Participaciones\.aspx\?qS=(\{[0-9a-fA-F-]+\})', t)
    return m.group(1) if m else None


def _subtitulo(t: str) -> str:
    m = re.search(r'id="ctl00_lblSubtitulo">(.*?)<', t, re.S)
    return _limpiar(m.group(1)) if m else ""


def buscar(s: requests.Session, termino: str, prefijo: str) -> tuple[str, str]:
    """Devuelve (guid de la ficha, nombre en la CNMV)."""
    g = _pedir(s, "GET", CNMV_BUSQUEDA)
    if g is None:
        raise DatosRaros("la CNMV no responde al formulario")
    datos = _ocultos(g.text)
    datos.update({"ctl00$ContentPrincipal$wNombreEntidad$txtDenominacion": termino, "ctl00$ContentPrincipal$btnOk": "Buscar"})
    time.sleep(PAUSA)
    p = _pedir(s, "POST", CNMV_BUSQUEDA, data=datos, headers={"Referer": CNMV_BUSQUEDA})
    if p is None:
        raise DatosRaros("la CNMV no responde a la búsqueda")
    pre = _sin_tildes(prefijo)
    if _guid(p.text):
        nombre = _subtitulo(p.text)
        if not _sin_tildes(nombre).startswith(pre):
            raise DatosRaros(f"la búsqueda «{termino}» lleva a {nombre!r}")
        return _guid(p.text), nombre
    sel = re.search(r'<select name="ctl00\$ContentPrincipal\$wbusqueda\$lstSeleccion".*?</select>', p.text, re.S)
    opciones = [(m.group(1), _limpiar(m.group(2)))
                for m in re.finditer(r'<option[^>]*value="([^"]+)"[^>]*>(.*?)</option>', sel.group(0) if sel else "", re.S)]
    elegidas = [o for o in opciones if _sin_tildes(o[1]).startswith(pre)]
    if len(elegidas) != 1:
        raise DatosRaros(f"la búsqueda «{termino}» da {len(opciones)} entidades y {len(elegidas)} encajan")
    datos = _ocultos(p.text)
    datos.update({"ctl00$ContentPrincipal$wNombreEntidad$txtDenominacion": termino,
                  "ctl00$ContentPrincipal$wbusqueda$lstSeleccion": elegidas[0][0],
                  "ctl00$ContentPrincipal$wbusqueda$btnSeleccionar": "Seleccionar"})
    time.sleep(PAUSA)
    q = _pedir(s, "POST", p.url, data=datos, headers={"Referer": p.url})
    if q is None or not _guid(q.text):
        raise DatosRaros(f"no se pudo abrir la ficha de {elegidas[0][1]}")
    return _guid(q.text), _subtitulo(q.text) or elegidas[0][1]


def ficha(s: requests.Session, guid: str) -> dict:
    r = _pedir(s, "GET", CNMV_FICHA + guid)
    if r is None:
        raise DatosRaros("la CNMV no devuelve la ficha")
    t = r.text
    tabla = re.search(r'<table[^>]+id="ctl00_ContentPrincipal_gridAccionistasSignificativos".*?</table>', t, re.S)
    if not tabla:
        raise DatosRaros("la ficha no trae la tabla de accionistas significativos")
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla.group(0), re.S):
        celdas = {re.sub(r"\s+", " ", m.group(1)).strip(): _limpiar(m.group(2))
                  for m in re.finditer(r'<td[^>]*data-th="([^"]+)"[^>]*>(.*?)</td>', tr, re.S)}
        if not celdas.get("Denominación"):
            continue
        f = {v: celdas.get(k, "") for k, v in COLUMNAS.items()}
        for k in ("acciones", "directo", "indirecto", "instrumentos", "total"):
            f[k] = _num_cnmv(f[k])
        f["fecha"] = _iso(f["fecha"])
        filas.append(f)
    plano = _limpiar(t)
    tot = re.search(r"Número total de derechos de voto.*?(\d{1,3}(?:\.\d{3})+)", plano)
    fmod = re.search(r"Fecha de última modificación del número de derechos de voto:\s*(\d\d/\d\d/\d{4})", plano)
    return {"accionistas": filas, "derechos_voto": int(tot.group(1).replace(".", "")) if tot else None,
            "fecha_derechos_voto": _iso(fmod.group(1)) if fmod else ""}


def revisar_filas(filas: list[dict], empresa: str) -> None:
    for f in filas:
        for k in ("acciones", "directo", "indirecto", "instrumentos", "total"):
            if f[k] is not None and not 0 <= f[k] <= 100:
                raise DatosRaros(f"{empresa}: porcentaje fuera de rango en {f['accionista']}")
        a, b, t = f["acciones"] or 0, f["instrumentos"] or 0, f["total"]
        if t is None or abs(a + b - t) > 0.0015:
            raise DatosRaros(f"{empresa}: A + B no cuadra con el total en {f['accionista']}")
        if not f["fecha"]:
            AVISOS.append(f"{empresa}: {f['accionista']} sin fecha de registro")


def consultar(anterior: dict) -> dict:
    ibex = lista_ibex()
    s = requests.Session()
    s.headers.update(CAB_CNMV)
    empresas, fallos = [], []
    previas = {e["isin"]: e for e in anterior.get("empresas", [])}
    for v in ibex:
        isin = v["isin"]
        if isin in FUERA:
            corto, pais, supervisor = FUERA[isin]
            empresas.append({"isin": isin, "empresa": corto, "fuera": True, "pais": pais, "supervisor": supervisor})
            continue
        corto, termino, prefijo = EMPRESAS.get(isin, (None, v["nombre_bme"], v["nombre_bme"]))
        if corto is None:
            corto = v["nombre_bme"].title()
            AVISOS.append(f"Valor nuevo en el IBEX 35 sin entrada en EMPRESAS: {isin} {v['nombre_bme']}")
        try:
            guid, nombre_cnmv = buscar(s, termino, prefijo)
            time.sleep(PAUSA)
            d = ficha(s, guid)
            revisar_filas(d["accionistas"], corto)
            if not d["accionistas"]:
                raise DatosRaros("la tabla de accionistas viene vacía")
            empresas.append({"isin": isin, "empresa": corto, "nombre_cnmv": nombre_cnmv, "fuera": False,
                             "consulta": datetime.now(timezone.utc).date().isoformat(), **d})
        except DatosRaros as e:
            fallos.append(f"{corto}: {e}")
            if isin in previas and not previas[isin].get("fuera"):
                empresas.append({**previas[isin], "de_consulta_anterior": True})
            AVISOS.append(f"{corto}: {e} (se usan los datos de la consulta anterior)" if isin in previas else f"{corto}: {e} (sin datos)")
        time.sleep(PAUSA)
    if len(fallos) > MAX_FALLOS:
        raise DatosRaros(f"la CNMV ha fallado con {len(fallos)} empresas: {fallos}")
    return {"empresas": sorted(empresas, key=lambda e: _sin_tildes(e["empresa"]))}


# --------------------------------------------------------------------------- cálculo y textos
def principal(e: dict) -> list[dict]:
    """El accionista o los accionistas con más derechos de voto por acciones (A)."""
    filas = [f for f in e["accionistas"] if (f["acciones"] or 0) > 0]
    if not filas:
        return []
    m = max(f["acciones"] for f in filas)
    return [f for f in filas if abs(f["acciones"] - m) < 1e-9]


def frase_empresa(e: dict) -> str:
    p = principal(e)
    n = len(e["accionistas"])
    if not p:
        return (f"<p>La CNMV recoge {n} {'participación' if n == 1 else 'participaciones'}, solo a través de instrumentos "
                f"financieros.</p>")
    nom = lambda f: html.escape(f["accionista"])  # noqa: E731
    if len(p) == 2 and {bool(p[0]["directo"]), bool(p[1]["directo"])} == {True, False}:
        d, i = (p[0], p[1]) if p[0]["directo"] else (p[1], p[0])
        t = (f"La mayor participación por acciones, del {_pct(p[0]['acciones'])} de los derechos de voto, figura dos veces: "
             f"de forma directa a nombre de {nom(d)} y de forma indirecta a nombre de {nom(i)}.")
    elif len(p) == 1:
        t = f"La mayor participación por acciones es la de {nom(p[0])}, con el {_pct(p[0]['acciones'])} de los derechos de voto."
    else:
        t = (f"La mayor participación por acciones, del {_pct(p[0]['acciones'])}, figura a nombre de "
             + ", ".join(nom(f) for f in p[:-1]) + f" y {nom(p[-1])}.")
    resto = n - len(p)
    if resto:
        t += f" En total, la CNMV recoge {n} participaciones significativas."
    return f"<p>{t}</p>"


def tabla_empresa(e: dict) -> str:
    filas = sorted(e["accionistas"], key=lambda f: (-(f["acciones"] or 0), -(f["total"] or 0), f["accionista"]))
    cuerpo = "\n".join(
        f"<tr><td>{html.escape(f['accionista'])}</td><td>{_pct(f['acciones'])}</td><td>{_pct(f['instrumentos'])}</td>"
        f"<td>{_pct(f['total'])}</td><td>{_f(f['fecha'])}</td></tr>" for f in filas)
    return ('<figure class="wp-block-table"><table><thead><tr><th>Accionista</th><th>Por acciones</th>'
            '<th>Por instrumentos financieros</th><th>Total</th><th>Registrada en la CNMV</th></tr></thead>'
            f"<tbody>\n{cuerpo}\n</tbody></table></figure>")


def _ancla(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _sin_tildes(nombre).lower()).strip("-")


def resumen(datos: dict) -> str:
    con = [e for e in datos["empresas"] if not e.get("fuera")]
    mayoria = sorted(((e, principal(e)[0]) for e in con if principal(e) and principal(e)[0]["acciones"] > 50),
                     key=lambda x: -x[1]["acciones"])
    presencia: dict[str, list[str]] = {}
    for e in con:
        for f in e["accionistas"]:
            presencia.setdefault(f["accionista"], []).append(e["empresa"])
    top = sorted(presencia.items(), key=lambda x: (-len(x[1]), x[0]))
    t = []
    if top:
        quien, donde = top[0]
        t.append(f"<p>{html.escape(quien)} es el accionista que aparece en más empresas del IBEX 35: tiene una participación "
                 f"significativa declarada en {len(donde)} de las {len(con)} que se registran en la CNMV.")
    if mayoria:
        t[-1] += (f" En {len(mayoria)} hay un accionista con más de la mitad de los derechos de voto por acciones: "
                  + "; ".join(f"{html.escape(e['empresa'])} ({html.escape(p['accionista'])}, {_pct(p['acciones'], 1)})"
                              for e, p in mayoria) + ".")
    if t:
        t[-1] += "</p>"
    return "\n".join(t)


def tabla_presencia(datos: dict) -> str:
    con = [e for e in datos["empresas"] if not e.get("fuera")]
    presencia: dict[str, list[tuple[str, float]]] = {}
    for e in con:
        for f in e["accionistas"]:
            presencia.setdefault(f["accionista"], []).append((e["empresa"], f["total"] or 0))
    top = [x for x in sorted(presencia.items(), key=lambda x: (-len(x[1]), x[0])) if len(x[1]) >= 3]
    cuerpo = "\n".join(
        f"<tr><td>{html.escape(q)}</td><td>{len(d)}</td><td>"
        + ", ".join(f"{html.escape(n)} ({_pct(p, 2)})" for n, p in sorted(d, key=lambda z: -z[1])) + "</td></tr>"
        for q, d in top)
    return ('<figure class="wp-block-table"><table><thead><tr><th>Accionista</th><th>Empresas</th>'
            '<th>Dónde (total de derechos de voto declarado)</th></tr></thead>'
            f"<tbody>\n{cuerpo}\n</tbody></table></figure>")


def huella(datos: dict) -> str:
    """Resumen de los datos (sin fechas de consulta), para saber si algo ha cambiado."""
    base = [[e["isin"], e.get("fuera"), [[f["accionista"], f["acciones"], f["instrumentos"], f["total"], f["fecha"]]
                                         for f in e.get("accionistas", [])]] for e in datos["empresas"]]
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def fragmento(datos: dict, fecha: str) -> str:
    con = [e for e in datos["empresas"] if not e.get("fuera")]
    fuera = [e for e in datos["empresas"] if e.get("fuera")]
    ultima = max((f["fecha"] for e in con for f in e["accionistas"] if f["fecha"]), default="")
    partes = [f"<!-- accionistas:inicio {huella(datos)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha)} con el registro de participaciones significativas '
              f"de la CNMV. La notificación más reciente es del {_f(ultima)}.</p>",
              resumen(datos),
              "<h2>Los accionistas que están en más empresas del IBEX 35</h2>",
              "<p>Accionistas con participación significativa en tres empresas o más del índice. Entre paréntesis, el total de "
              "derechos de voto que declaran en cada una, por acciones y por instrumentos financieros.</p>",
              tabla_presencia(datos),
              "<h2>Empresa por empresa</h2>"]
    for e in con:
        aviso = (f' <small>(la CNMV no respondió en la última consulta: datos del {_f(e.get("consulta", ""))})</small>'
                 if e.get("de_consulta_anterior") else "")
        partes += [f'<h3 id="{_ancla(e["empresa"])}">{html.escape(e["empresa"])}{aviso}</h3>', frase_empresa(e), tabla_empresa(e)]
    if fuera:
        partes.append("<h2>Las que tienen el domicilio fuera de España</h2>")
        partes.append("<p>" + " ".join(
            f"{html.escape(e['empresa'])} tiene su domicilio social en {html.escape(e['pais'])}, así que sus accionistas "
            f"significativos lo comunican a {html.escape(e['supervisor'])}, no a la CNMV." for e in fuera) +
            " Por eso no aparecen en las tablas.</p>")
    partes.append(f'<p class="has-small-font-size">Fuente: CNMV, registro de participaciones significativas de cada emisor, '
                  f'tal y como lo publica (última notificación de cada accionista). Los nombres de los accionistas se reproducen '
                  f'como figuran en la CNMV. <a href="{METODOLOGIA}">Cómo se hace y cómo leer las tablas</a>.</p>')
    partes.append("<!-- accionistas:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Accionistas significativos de las empresas del IBEX 35 (El Especulador, con datos de la CNMV)",
        "description": "Los accionistas que han comunicado a la CNMV una participación significativa en cada empresa del IBEX 35, "
                       "con el porcentaje de derechos de voto por acciones y por instrumentos financieros y la fecha de cada "
                       "notificación, y los accionistas presentes en más empresas del índice.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir del registro de participaciones significativas de la CNMV",
        "isBasedOn": "https://www.cnmv.es/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/accionistas.csv"}],
    }, ensure_ascii=False) + "</script>"


def escribir(datos: dict, fecha: str, salida: Path) -> bool:
    """Escribe los archivos. Devuelve True si los datos han cambiado respecto a los publicados."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(datos)
    cambia = antes.get("huella") != nueva
    fecha_pub = fecha if cambia else antes.get("fecha", fecha)
    campos = ["empresa", "isin", "accionista", "acciones", "directo", "indirecto", "instrumentos", "total", "fecha", "info",
              "consulta"]
    with (dd / "accionistas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for e in datos["empresas"]:
            for f in e.get("accionistas", []):
                w.writerow({**f, "empresa": e["empresa"], "isin": e["isin"], "consulta": e.get("consulta", "")})
    previo.write_text(json.dumps({
        "fecha": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "fuente": "CNMV, registro de participaciones significativas (Real Decreto 1362/2007)",
        "condiciones": "Reproducción fiel de la información publicada por la CNMV, que la ofrece gratuitamente en www.cnmv.es. "
                       "Cita: El Especulador, a partir de datos de la CNMV",
        **datos}, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(datos, fecha_pub)
    marca = "\n<!-- accionistas:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accionistas del IBEX 35 | El Especulador</title>
<meta name="description" content="Los accionistas significativos de cada empresa del IBEX 35 según el registro de la CNMV, con el porcentaje de derechos de voto y la fecha de cada notificación.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} h3{{font-size:1rem;margin-top:1.4em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Los accionistas del IBEX 35</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/accionistas.csv">todas las participaciones</a> · <a href="datos/ultima.json">JSON</a>. Reproducen la información que publica gratuitamente la CNMV en su web. Cita: «El Especulador, a partir de datos de la CNMV». Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(datetime.now(timezone.utc).date().isoformat())}. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
""", encoding="utf-8")
    return cambia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="JSON con una consulta ya hecha (para probar sin red)")
    ap.add_argument("--fecha")
    a = ap.parse_args()
    salida = Path(a.salida)
    previo = salida / "datos" / "ultima.json"
    anterior = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    datos = json.loads(Path(a.local).read_text(encoding="utf-8")) if a.local else consultar(anterior)
    for e in datos["empresas"]:
        if not e.get("fuera"):
            revisar_filas(e["accionistas"], e["empresa"])
    fecha = a.fecha or datetime.now(timezone.utc).date().isoformat()
    cambia = escribir(datos, fecha, salida)
    for av in AVISOS:
        print(f"::warning::{av}")
    con = [e for e in datos["empresas"] if not e.get("fuera")]
    print(f"{len(con)} empresas con datos de la CNMV, {sum(len(e['accionistas']) for e in con)} participaciones. "
          f"{'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
