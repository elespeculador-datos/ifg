"""Calendario de dividendos del IBEX 35, a partir de lo que cada empresa comunica a la CNMV.

Indicador 11 del catálogo de Datos de El Especulador («Dividendos y OPAs (CNMV)», primera parte). Sustituto legal
del calendario de BME de la página «Calendario de dividendos» (8578, P3 del catálogo: datos de BME sin licencia).
No descarga nada: lee la salida del colector `cnmv` (PR #111) en <datos>/cnmv/datos/:

  dividendos.csv  importe bruto por acción, moneda y fechas ex, de registro y de pago leídos del PDF de cada
                  comunicado de dividendo del IBEX 35 (solo lo que se lee con seguridad; lo demás, vacío)
  ibex35.csv      título, empresa, ficha y clasificación de cada comunicado (solo cuentan los que el colector
                  sigue clasificando como dividendo)

y publica en <salida>/ (en el servidor, $ESPEC_DATOS_DIR/calendario/):

  fragmento-wp.html  próximos dividendos (fecha ex o de pago de hoy en adelante), pagados en los últimos 90 días
                     y dividendos flexibles comunicados, entre <!-- dividendos:inicio HUELLA --> y
                     <!-- dividendos:fin --> (las marcas de la página 8578)
  index.html         página propia de la salida
  datos/ultima.json  resumen versionado
  datos/calendario.csv  un dividendo por fila (un mismo dividendo anunciado varias veces, una sola vez)

Sin rentabilidad por dividendo ni precios: harían falta precios con licencia. Sin predicción ni recomendación.
La huella solo cambia si cambia lo publicado (un dividendo nuevo, uno que pasa de próximo a pagado, otro dato).

Uso:
  python calendario/calendario.py --salida $ESPEC_DATOS_DIR/calendario
  python calendario/calendario.py --salida /tmp/cal --datos /ruta/a/datos --fecha 2026-11-22
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "1.1.0"
MADRID = ZoneInfo("Europe/Madrid")
PAGINA_WP = "https://elespeculador.com/calendario-dividendos/"
FICHAS = "https://elespeculador.com/ibex35/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/calendario/"
DIAS_PAGADOS = 90       # pagados recientemente: fecha de pago en los últimos 90 días
DIAS_FLEXIBLES = 120    # dividendos flexibles: comunicados de los últimos 120 días, el último de cada empresa
TOLERANCIA = 0.05       # el importe aprobado y el ajustado por la autocartera se diferencian en menos de un 5 %
COLUMNAS_DIV = ["canal", "nreg", "fecha_comunicado", "isin", "empresa", "tipo", "importe_bruto", "moneda", "fecha_ex",
                "fecha_registro", "fecha_pago", "extraccion", "enlace"]
COLUMNAS_IBEX = ["canal", "nreg", "fecha", "texto", "enlace", "isin", "empresa", "ficha", "caja", "etiqueta"]
COLUMNAS_RES = ["canal", "nreg", "pago", "fecha_comunicado", "isin", "empresa", "concepto", "importe_bruto", "moneda", "fecha_ex",
                "fecha_registro", "fecha_pago", "extraccion", "enlace"]
LECTURA = {"completa": "leído del comunicado", "parcial": "parcial: el resto, en el comunicado"}
AVISOS: list[str] = []


class DatosRaros(Exception):
    """Falta la salida del colector cnmv o no tiene la forma esperada: mejor parar que publicar un calendario vacío."""


# --------------------------------------------------------------------------- lectura
def _csv(ruta: Path, columnas: list[str]) -> list[dict]:
    if not ruta.exists():
        raise DatosRaros(f"falta {ruta} (¿el colector cnmv no ha pasado todavía con la PR #111?)")
    with ruta.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    faltan = [c for c in columnas if filas and c not in filas[0]]
    if not filas or faltan:
        raise DatosRaros(f"{ruta.name}: vacío o sin columnas {faltan}")
    return filas


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x or "")
    return " " + re.sub(r"[^a-z0-9]+", " ", "".join(c for c in x if not unicodedata.combining(c)).lower()) + " "


def concepto(titulo: str) -> str:
    """«a cuenta», «complementario» o «extraordinario», si lo dice el título del comunicado; si no, vacío."""
    t = _norm(titulo)
    if " extraordinario " in t:
        return "extraordinario"
    if " a cuenta " in t or " interim " in t:
        return "a cuenta"
    if " complementario " in t or " dividendo final " in t:
        return "complementario"
    return ""


def _float(x: str) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def leer(datos: Path) -> tuple[list[dict], str]:
    """Dividendos del IBEX 35 que el colector cnmv sigue clasificando como tales, con su título y su ficha."""
    base = datos / "cnmv" / "datos"
    todos = {(r["canal"], r["nreg"]): r for r in _csv(base / "ibex35.csv", COLUMNAS_IBEX)}
    ibex = {k: r for k, r in todos.items() if r["caja"] == "dividendos" and r["etiqueta"] in ("Dividendo", "Dividendo flexible")}
    divs = []
    for r in _csv(base / "dividendos.csv", COLUMNAS_DIV):
        c = ibex.get((r["canal"], r["nreg"]))
        if c is None:      # el colector ya no lo clasifica como dividendo
            continue
        divs.append({"canal": r["canal"], "nreg": r["nreg"], "fecha_comunicado": r["fecha_comunicado"], "isin": r["isin"],
                     "empresa": c["empresa"], "ficha": c["ficha"], "titulo": c["texto"], "flexible": c["etiqueta"] == "Dividendo flexible",
                     "concepto": concepto(c["texto"]), "importe": _float(r["importe_bruto"]),
                     "moneda": (r["moneda"] or None) if _float(r["importe_bruto"]) else None,
                     "fecha_ex": r["fecha_ex"] or None, "fecha_registro": r["fecha_registro"] or None, "fecha_pago": r["fecha_pago"] or None,
                     "lectura": LECTURA.get(r["extraccion"], "sin leer: ver el comunicado"), "enlace": r["enlace"]})
    # Dividendos que la empresa anuncia solo en su nota de resultados (lista cerrada del colector cnmv, hoy Inditex):
    # una fila por pago, con la nota como comunicado. Si el colector ya no la clasifica como resultados, no entra.
    if (base / "dividendos_resultados.csv").exists():
        for r in _csv(base / "dividendos_resultados.csv", COLUMNAS_RES):
            c = todos.get((r["canal"], r["nreg"]))
            if c is None or c["caja"] != "resultados":
                continue
            divs.append({"canal": r["canal"], "nreg": r["nreg"], "fecha_comunicado": r["fecha_comunicado"], "isin": r["isin"],
                         "empresa": c["empresa"], "ficha": c["ficha"], "titulo": c["texto"], "flexible": False,
                         "concepto": r["concepto"], "importe": _float(r["importe_bruto"]),
                         "moneda": (r["moneda"] or None) if _float(r["importe_bruto"]) else None,
                         "fecha_ex": r["fecha_ex"] or None, "fecha_registro": r["fecha_registro"] or None, "fecha_pago": r["fecha_pago"] or None,
                         "lectura": "anunciado en los resultados: " + ("leído del comunicado" if r["extraccion"] == "completa"
                                                                     else "parcial: el resto, en el comunicado"),
                         "enlace": r["enlace"]})
    hasta = max((r["fecha"] for r in ibex.values()), default="")[:10]
    return divs, hasta


# --------------------------------------------------------------------------- cálculo
def _mismo_importe(a: float | None, b: float | None) -> bool:
    return a is None or b is None or abs(a - b) <= TOLERANCIA * max(a, b)


def fundir(divs: list[dict]) -> list[dict]:
    """Un dividendo por fila. El mismo dividendo puede comunicarse varias veces (anuncio y recordatorio, o el importe
    aprobado y después el ajustado por la autocartera): misma empresa, misma fecha ex o de pago e importe igual a menos
    de un 5 % (o sin importe en uno). Queda el comunicado más reciente que tenga importe."""
    fundidos: list[dict] = []
    for d in sorted((x for x in divs if not x["flexible"] and (x["fecha_ex"] or x["fecha_pago"])),
                    key=lambda x: (x["fecha_comunicado"], int(x["nreg"]))):
        igual = next((f for f in fundidos if f["isin"] == d["isin"] and _mismo_importe(f["importe"], d["importe"])
                      and ((d["fecha_ex"] and d["fecha_ex"] == f["fecha_ex"]) or (d["fecha_pago"] and d["fecha_pago"] == f["fecha_pago"]))), None)
        if igual is None:
            fundidos.append(dict(d))
        elif d["importe"] or not igual["importe"]:
            fundidos[fundidos.index(igual)] = dict(d)
    return fundidos


def _clave(d: dict) -> str:
    return d["fecha_ex"] or d["fecha_pago"]


def calcular(divs: list[dict], hoy: date, hasta: str) -> dict:
    h = hoy.isoformat()
    fundidos = fundir(divs)
    proximos = sorted((d for d in fundidos if (d["fecha_ex"] or "") >= h or (d["fecha_pago"] or "") >= h),
                      key=lambda d: (_clave(d), d["empresa"]))
    desde = (hoy - timedelta(days=DIAS_PAGADOS)).isoformat()
    pagados = sorted((d for d in fundidos if d not in proximos and d["fecha_pago"] and desde <= d["fecha_pago"] < h),
                     key=lambda d: (d["fecha_pago"], d["empresa"]), reverse=True)
    limite = (hoy - timedelta(days=DIAS_FLEXIBLES)).isoformat()
    ultimos: dict[str, dict] = {}
    # «Modificación del Programa de Recompra … por la primera ejecución del Scrip Dividend» (ACS) habla de la recompra, no del dividendo
    for d in sorted((x for x in divs if x["flexible"] and x["fecha_comunicado"] >= limite and " recompra " not in _norm(x["titulo"])),
                    key=lambda x: (x["fecha_comunicado"], int(x["nreg"]))):
        ultimos[d["isin"]] = d
    flexibles = sorted(ultimos.values(), key=lambda d: d["fecha_comunicado"], reverse=True)
    con_ex = [d for d in proximos if (d["fecha_ex"] or "") >= h]
    campos = ["empresa", "isin", "ficha", "concepto", "importe", "moneda", "fecha_ex", "fecha_registro", "fecha_pago", "lectura",
              "titulo", "fecha_comunicado", "nreg", "enlace"]
    return {"fecha": h, "comunicados_hasta": hasta,
            "proximos": [{k: d[k] for k in campos} for d in proximos],
            "pagados_90d": [{k: d[k] for k in campos} for d in pagados],
            "flexibles": [{k: d[k] for k in ("empresa", "isin", "ficha", "titulo", "fecha_comunicado", "nreg", "enlace", "importe", "moneda",
                                             "fecha_pago")} for d in flexibles],
            "con_fecha_ex": len(con_ex), "empresas_con_fecha_ex": len({d["isin"] for d in con_ex}),
            "todos": [{k: d[k] for k in campos} for d in sorted(fundidos, key=lambda d: (_clave(d), d["empresa"]))]}


def huella(res: dict) -> str:
    # lo que se publica depende también del día: qué fechas ex ya han pasado (la frase y la marca «pasada»)
    pasadas = [d["nreg"] for d in res["proximos"] if d["fecha_ex"] and d["fecha_ex"] < res["fecha"]]
    base = {"version": VERSION, "proximos": res["proximos"], "pagados_90d": res["pagados_90d"], "flexibles": res["flexibles"], "pasadas": pasadas}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else "—"


def _importe(d: dict) -> str:
    if not d.get("importe") or not d.get("moneda"):
        return f'<a href="{html.escape(d["enlace"])}">en el comunicado</a>'
    ent, _, dec = f"{d['importe']:.8f}".rstrip("0").partition(".")
    v = f"{ent},{dec.ljust(2, '0')}"  # como en los comunicados: dos decimales como mínimo y los que haga falta (0,080248)
    return f"{v} {'€' if d['moneda'] == 'EUR' else html.escape(d['moneda'])}"


def _efectivo(d: dict) -> str:
    """Efectivo por acción para quien lo elige y fecha de pago de un flexible, si el comunicado los fija."""
    partes = []
    if d.get("importe") and d.get("moneda"):
        partes.append(f"efectivo para quien lo elige: {_importe(d)} por acción")
    if d.get("fecha_pago"):
        partes.append(f"pago del efectivo: {_f(d['fecha_pago'])}")
    return (" · " + "; ".join(partes)) if partes else ""


def _empresa(d: dict) -> str:
    return f'<a href="{FICHAS}{html.escape(d["ficha"])}/">{html.escape(d["empresa"])}</a>' if d.get("ficha") else html.escape(d["empresa"])


def _comunicado(d: dict) -> str:
    return f'<a href="{html.escape(d["enlace"])}" title="{html.escape(d["titulo"])}">{_f(d["fecha_comunicado"])}</a>'


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def frase(res: dict) -> str:
    h = res["fecha"]
    con_ex = [d for d in res["proximos"] if (d["fecha_ex"] or "") >= h]
    if not con_ex:
        texto = "Ahora mismo ninguna empresa del IBEX 35 tiene comunicado un dividendo con fecha ex de hoy en adelante."
        pendientes = [d for d in res["proximos"] if (d["fecha_pago"] or "") >= h]
        if pendientes:
            k = len(pendientes)
            texto += f" Queda{'n' if k != 1 else ''} {k} dividendo{'s' if k != 1 else ''} pendiente{'s' if k != 1 else ''} de pago."
        return texto
    p = con_ex[0]
    n, m = res["con_fecha_ex"], res["empresas_con_fecha_ex"]
    cuantos = f"<strong>{n} dividendo{'s' if n != 1 else ''}</strong> de {m} empresa{'s' if m != 1 else ''} del IBEX 35 con fecha ex de hoy en adelante"
    if p.get("importe"):
        que = f"{_empresa(p)} descuenta {_importe(p)} brutos por acción" + (f", que paga el {_f(p['fecha_pago'])}" if p.get("fecha_pago") else "")
    else:
        que = f"{_empresa(p)} descuenta un dividendo cuyo importe está en el comunicado" + (f"; lo paga el {_f(p['fecha_pago'])}" if p.get("fecha_pago") else "")
    return f"Hay {cuantos}. La próxima fecha ex es el <strong>{_f(p['fecha_ex'])}</strong>: {que}."


def fragmento(res: dict, fecha_pub: str) -> str:
    h = res["fecha"]
    partes = [f"<!-- dividendos:inicio {res['huella']} -->",
              (f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)}. Se revisa cada hora con los comunicados de las empresas del '
               "IBEX 35 a la CNMV. Importes brutos por acción.</p>"),
              "<p>" + frase(res) + "</p>",
              "<h2>Próximos dividendos</h2>",
              ('<p class="has-small-font-size">Para cobrar un dividendo hay que tener las acciones al cierre de la sesión anterior a la fecha ex. '
               "Si la fecha ex ya ha pasado y el pago no, la fila sigue aquí hasta el día del pago.</p>")]
    if res["proximos"]:
        partes.append(_tabla(["Fecha ex", "Empresa", "Bruto por acción", "Tipo", "Fecha de pago", "Comunicado"],
                             [[(_f(d["fecha_ex"]) if not d["fecha_ex"] or d["fecha_ex"] >= h
                                else f'<span class="has-small-font-size">{_f(d["fecha_ex"])} (pasada)</span>'),
                               _empresa(d), _importe(d), d["concepto"] or "—", _f(d["fecha_pago"]), _comunicado(d)] for d in res["proximos"]]))
    else:
        partes.append("<p>No hay dividendos con fecha ex o de pago de hoy en adelante.</p>")
    partes.append(f"<h2>Pagados en los últimos {DIAS_PAGADOS} días</h2>")
    if res["pagados_90d"]:
        partes.append(_tabla(["Fecha de pago", "Empresa", "Bruto por acción", "Tipo", "Fecha ex", "Comunicado"],
                             [[_f(d["fecha_pago"]), _empresa(d), _importe(d), d["concepto"] or "—", _f(d["fecha_ex"]), _comunicado(d)]
                              for d in res["pagados_90d"]]))
    else:
        partes.append(f"<p>Ningún dividendo pagado en los últimos {DIAS_PAGADOS} días según los comunicados.</p>")
    if res["flexibles"]:
        partes.append("<h2>Dividendos flexibles</h2>")
        partes.append("<p>En el dividendo flexible el accionista elige entre recibir acciones nuevas o cobrar en efectivo (vendiendo sus "
                      "derechos a la empresa o con un dividendo en efectivo, según la empresa); quien elige acciones no cobra ese efectivo. "
                      "Cuando el comunicado fija el efectivo por acción o la fecha en que se paga, va al lado; el resto del calendario de "
                      f"cada edición está en el comunicado. Último comunicado de cada empresa en los últimos {DIAS_FLEXIBLES} días:</p>")
        partes.append("<ul>" + "".join(f'<li>{_empresa(d)} · {_f(d["fecha_comunicado"])} · <a href="{html.escape(d["enlace"])}">'
                                       f'{html.escape(d["titulo"])}</a>{_efectivo(d)}</li>' for d in res["flexibles"]) + "</ul>")
    partes.append('<h2 id="metodo">De dónde sale y cómo se lee</h2>'
                  "<p>Las empresas del IBEX 35 comunican a la CNMV sus dividendos: el importe por acción, la fecha ex (desde la que la acción "
                  "cotiza sin derecho a cobrarlo), la fecha de registro y la de pago. El Especulador lee esos comunicados cada hora, saca de cada "
                  "uno el importe bruto y las fechas, y los ordena en este calendario. Si un dato no se puede leer con seguridad del propio "
                  "comunicado, la casilla queda en blanco y el enlace lleva al documento. Cuando una empresa comunica el mismo dividendo más de "
                  "una vez (por ejemplo, el importe aprobado y después el ajustado por la autocartera), aparece una sola vez, con el dato más "
                  "reciente. Los dividendos que una empresa anuncia solo dentro de su nota de resultados entran cuando El Especulador ha revisado "
                  "el formato de esa nota (hoy, Inditex); los de las demás empresas que lo hacen así, todavía no. No hay rentabilidad por dividendo: para calcularla harían falta precios con "
                  "licencia.</p>"
                  '<p class="has-small-font-size">Fuente: CNMV, comunicados de las empresas (otra información relevante e información privilegiada), '
                  "reproducidos fielmente (gratuitos en cnmv.es). La lectura, la selección y el calendario son de El Especulador y se publican "
                  'con licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>. '
                  "Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>")
    partes.append("<!-- dividendos:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Calendario de dividendos del IBEX 35 a partir de los comunicados a la CNMV (El Especulador)",
        "description": "Próximos dividendos de las empresas del IBEX 35 con su importe bruto por acción y sus fechas ex y de pago, "
                       "leídos de los comunicados de cada empresa a la CNMV, y los pagados en los últimos 90 días.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de los comunicados de las empresas a la CNMV", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": "https://www.cnmv.es/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/calendario.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


# --------------------------------------------------------------------------- escritura
def _atomico(ruta: Path, texto: str) -> None:
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def escribir(res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    try:
        antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    except ValueError:
        antes = {}
    cambia = antes.get("huella") != res["huella"]
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/calendario.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    cols = ["empresa", "isin", "concepto", "importe", "moneda", "fecha_ex", "fecha_registro", "fecha_pago", "lectura", "fecha_comunicado", "nreg", "enlace", "titulo"]
    tmp = dd / "calendario.csv.tmp"
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(res["todos"])
    os.replace(tmp, dd / "calendario.csv")
    resumen = {k: v for k, v in res.items() if k != "todos"}
    _atomico(previo, json.dumps({**resumen, "version": VERSION, "fecha_publicacion": fecha_pub,
                                 "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "fuente": "CNMV, comunicados de las empresas del IBEX 35 (OIR e IP), leídos por el colector cnmv",
                                 "condiciones": "Datos de la CNMV reproducidos fielmente (gratuitos en cnmv.es); lectura, selección y calendario de "
                                                "El Especulador (CC BY 4.0). Sin rentabilidad por dividendo. Contenido informativo; no es asesoramiento financiero."},
                                ensure_ascii=False, indent=1, allow_nan=False))
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- dividendos:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    _atomico(salida / "fragmento-wp.html", frag.replace(marca, "\n" + ld + marca))
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    _atomico(salida / "index.html", f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendario de dividendos del IBEX 35 | El Especulador</title>
<meta name="description" content="Próximos dividendos de las empresas del IBEX 35: importe bruto por acción, fecha ex y fecha de pago, leídos de los comunicados a la CNMV.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:980px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} table{{border-collapse:collapse;width:100%;font-size:.92rem}} th,td{{border-bottom:1px solid #e3e8ef;padding:4px 6px;text-align:left}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Calendario de dividendos del IBEX 35</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/calendario.csv">un dividendo por fila</a> · <a href="datos/ultima.json">JSON</a>. Fuente: CNMV; lectura y calendario de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", help="raíz con las salidas de los demás colectores (por defecto, la carpeta madre de --salida)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    salida = Path(a.salida)
    datos = Path(a.datos) if a.datos else salida.resolve().parent
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(MADRID).date()
    divs, hasta = leer(datos)
    res = calcular(divs, hoy, hasta)
    res["huella"] = huella(res)
    cambia = escribir(res, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    print(f"Calendario del {hoy}: {res['con_fecha_ex']} dividendos con fecha ex de hoy en adelante ({res['empresas_con_fecha_ex']} empresas), "
          f"{len(res['proximos'])} próximos con pago pendiente incluido, {len(res['pagados_90d'])} pagados en {DIAS_PAGADOS} días, "
          f"{len(res['flexibles'])} empresas con dividendo flexible comunicado. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::calendario: {e}")
        sys.exit(1)
