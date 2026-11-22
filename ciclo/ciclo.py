"""Reloj del ciclo: en qué fase están España y sus socios según los indicadores adelantados de la OCDE.

Indicador 20d del catálogo de Datos de El Especulador («Reloj del ciclo»). Lee del API SDMX de la OCDE los
indicadores compuestos adelantados (CLI, serie principal: ajustada en amplitud, metodología armonizada de la OCDE)
de España y de sus principales socios y mercados, clasifica cada mes en una de las cuatro fases que describe la
OCDE (por encima o por debajo de 100 y subiendo o bajando) y publica en <salida>/ (en el servidor,
$ESPEC_DATOS_DIR/ciclo/):

  fragmento-wp.html  frase del mes, tabla de zonas, reloj de España, serie desde 1985 y método, entre
                     <!-- ciclo:inicio HUELLA --> y <!-- ciclo:fin -->
  index.html         página propia de la salida
  datos/serie.csv    mes, zona, valor de la OCDE, cambio en el mes y fase (cálculo de El Especulador)
  datos/ultima.json  resumen versionado

Fuente: OCDE, «Composite leading indicators» (conjunto DSD_STES@DF_CLI). Términos de oecd.org (última actualización,
1 de julio de 2024), leídos el 22/11/2026: los datos se pueden usar para cualquier fin, también comercial,
reconociendo a la OCDE como fuente; algunos datos pueden llevar restricciones de terceros (este conjunto no
declara ninguna en sus metadatos). Las fases, los meses en fase y los gráficos son de El Especulador.

Sin predicción ni recomendación: la fase describe dónde está el indicador de la OCDE, no lo que hará la economía.

Uso:
  python ciclo/ciclo.py --salida $ESPEC_DATOS_DIR/ciclo
  python ciclo/ciclo.py --salida /tmp/c --local cli.csv --fecha 2026-11-22
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

VERSION = "1.0.0"
MADRID = ZoneInfo("Europe/Madrid")
ZONAS = [  # código de la OCDE, nombre
    ("ESP", "España"), ("G4E", "Cuatro grandes economías europeas"), ("DEU", "Alemania"), ("FRA", "Francia"),
    ("ITA", "Italia"), ("GBR", "Reino Unido"), ("USA", "Estados Unidos"), ("JPN", "Japón"), ("CHN", "China"),
    ("MEX", "México"), ("BRA", "Brasil"), ("TUR", "Turquía"), ("G7", "G7"),
]
NOMBRE = dict(ZONAS)
API = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/{zonas}.M.LI...AA...H"
PARAMS = {"startPeriod": "1955-01", "dimensionAtObservation": "AllDimensions"}
CABECERAS = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8", "User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
DATASET = "https://www.oecd.org/en/data/datasets/oecd-composite-leading-indicators-clis.html"
GUIA = "https://oecd.org/content/dam/oecd/en/data/methods/Interpreting_OECD_Composite_Leading_Indicators.pdf"
TERMINOS = "https://www.oecd.org/en/about/terms-conditions.html"
PAGINA_WP = "https://elespeculador.com/reloj-del-ciclo-economico/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/ciclo/"
# Las cuatro fases, en el orden en que la OCDE las nombra («expansion, downturn, slowdown and recovery»;
# «Interpreting OECD Composite Leading Indicators», octubre de 2020): (por encima de 100, sube) -> nombre.
FASES = {
    (True, True): ("expansión", "expansion"),
    (True, False): ("desaceleración", "downturn"),
    (False, False): ("enfriamiento", "slowdown"),
    (False, True): ("recuperación", "recovery"),
}
ORDEN_FASES = ["expansión", "desaceleración", "enfriamiento", "recuperación"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MIN_MESES_ESP = 400          # España empieza en enero de 1985 (502 meses en octubre de 2026)
DESFASE_AVISO, DESFASE_ERROR = 3, 5
MESES_RELOJ = 13             # el reloj dibuja el último año (13 puntos: 12 movimientos)
AVISOS: list[str] = []


class DatosRaros(Exception):
    """La OCDE no responde o el fichero no tiene la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- meses
def _n(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:7]) - 1


def _mes(n: int) -> str:
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def mes_largo(mes: str) -> str:
    return f"{MESES[int(mes[5:7]) - 1]} de {mes[:4]}"


def mes_corto(mes: str) -> str:
    return f"{MESES[int(mes[5:7]) - 1][:3]}. {mes[:4]}"


# --------------------------------------------------------------------------- descarga y lectura
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    esperas = [15, 30, 60, 120] if esperas is None else esperas
    url = API.format(zonas="+".join(z for z, _ in ZONAS))
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(url, params=PARAMS, headers=CABECERAS, timeout=(20, 120))
            if r.status_code == 200 and "TIME_PERIOD" in r.text[:2000] and "OBS_VALUE" in r.text[:2000]:
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:60]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudieron descargar los CLI de la OCDE tras {len(esperas) + 1} intentos: {ultimo}")


def leer(texto: str) -> dict[str, dict[str, float]]:
    """SDMX-CSV de la OCDE -> {zona: {AAAA-MM: valor}}. Solo la serie principal (LI, AA, metodología H)."""
    lector = csv.DictReader(io.StringIO(texto.lstrip("﻿")))
    faltan = [c for c in ("REF_AREA", "TIME_PERIOD", "OBS_VALUE", "MEASURE", "ADJUSTMENT", "METHODOLOGY") if c not in (lector.fieldnames or [])]
    if faltan:
        raise DatosRaros(f"el CSV de la OCDE no trae las columnas {faltan}")
    series: dict[str, dict[str, float]] = {}
    for f in lector:
        if (f["MEASURE"], f["ADJUSTMENT"], f["METHODOLOGY"]) != ("LI", "AA", "H") or f["REF_AREA"] not in NOMBRE:
            continue
        mes = f["TIME_PERIOD"].strip()
        if len(mes) != 7 or mes[4] != "-" or not f["OBS_VALUE"].strip():
            continue
        try:
            v = float(f["OBS_VALUE"])
        except ValueError:
            raise DatosRaros(f"valor no numérico «{f['OBS_VALUE'][:20]}» en {f['REF_AREA']} {mes}") from None
        if not 70 < v < 130:
            raise DatosRaros(f"valor fuera de rango en {f['REF_AREA']} {mes}: {v} (el CLI oscila alrededor de 100)")
        series.setdefault(f["REF_AREA"], {})[mes] = v
    if len(series.get("ESP", {})) < MIN_MESES_ESP:
        raise DatosRaros(f"España trae {len(series.get('ESP', {}))} meses; se esperaban más de {MIN_MESES_ESP}")
    for z, nombre in ZONAS:
        if z not in series:
            AVISOS.append(f"la OCDE no ha devuelto el indicador de {nombre} ({z}): se publica sin esa fila")
    return series


# --------------------------------------------------------------------------- cálculos
def fases(serie: dict[str, float]) -> dict[str, dict]:
    """Cada mes con mes anterior: cambio y fase. Un cambio exactamente nulo conserva la dirección del mes anterior."""
    salida: dict[str, dict] = {}
    meses = sorted(serie)
    sube_antes = True
    for a, b in zip(meses, meses[1:]):
        if _n(b) - _n(a) != 1:
            sube_antes = True
            continue
        d = serie[b] - serie[a]
        sube = sube_antes if d == 0 else d > 0
        sube_antes = sube
        salida[b] = {"valor": serie[b], "cambio": d, "encima": serie[b] > 100, "sube": sube, "fase": FASES[(serie[b] > 100, sube)][0]}
    return salida


def _racha(f: dict[str, dict], ultimo: str, clave) -> tuple[int, str]:
    """Meses seguidos hasta el último con el mismo valor de `clave` y el primero de esa racha."""
    objetivo = clave(f[ultimo])
    n, mes = 0, ultimo
    while mes in f and clave(f[mes]) == objetivo:
        n += 1
        mes = _mes(_n(mes) - 1)
    return n, _mes(_n(mes) + 1)


def resumen_zona(serie: dict[str, float], hoy: date) -> dict:
    f = fases(serie)
    u = max(f)
    x = f[u]
    en_fase, desde_fase = _racha(f, u, lambda r: r["fase"])
    en_dir, _ = _racha(f, u, lambda r: r["sube"])
    en_lado, desde_lado = _racha(f, u, lambda r: r["encima"])
    inicio = min(f)
    reparto = {fase: 0 for fase in ORDEN_FASES}
    for r in f.values():
        reparto[r["fase"]] += 1
    return {
        "mes": u, "valor": round(x["valor"], 4), "cambio_1m": round(x["cambio"], 4),
        "cambio_6m": None if _mes(_n(u) - 6) not in serie else round(serie[u] - serie[_mes(_n(u) - 6)], 4),
        "encima_de_100": x["encima"], "sube": x["sube"], "fase": x["fase"], "fase_ocde": FASES[(x["encima"], x["sube"])][1],
        "meses_en_fase": en_fase, "fase_desde": None if desde_fase == inicio else desde_fase, "meses_en_direccion": en_dir,
        "meses_del_mismo_lado": en_lado, "lado_desde": None if desde_lado == inicio else desde_lado, "desde": min(serie), "meses": len(f),
        "reparto_fases_pct": {k: round(v / len(f) * 100, 1) for k, v in reparto.items()},
        "desfase_meses": hoy.year * 12 + hoy.month - 1 - _n(u),
    }


def calcular(series: dict[str, dict[str, float]], hoy: date) -> dict:
    res = {"zonas": {}}
    for z, nombre in ZONAS:
        if z in series and len(series[z]) >= 24:
            res["zonas"][z] = {"nombre": nombre, **resumen_zona(series[z], hoy)}
    es = res["zonas"]["ESP"]
    if es["desfase_meses"] > DESFASE_ERROR:
        raise DatosRaros(f"el último dato de España es de {es['mes']}: {es['desfase_meses']} meses de desfase; comprobar la OCDE")
    if es["desfase_meses"] > DESFASE_AVISO:
        AVISOS.append(f"el último dato de España es de {es['mes']}: {es['desfase_meses']} meses de desfase")
    viejas = [z for z, r in res["zonas"].items() if r["mes"] != es["mes"]]
    if viejas:
        AVISOS.append(f"zonas con un mes distinto del de España ({es['mes']}): {', '.join(viejas)}")
    fe = fases(series["ESP"])
    ultimos = [m for m in sorted(fe) if _n(m) > _n(es["mes"]) - MESES_RELOJ]
    res["reloj"] = [{"mes": m, "desviacion": round(fe[m]["valor"] - 100, 4), "cambio": round(fe[m]["cambio"], 4)} for m in ultimos]
    res["mes"] = es["mes"]
    res["grafico"] = {z: series[z] for z in ("ESP", "G4E") if z in series}
    return res


def huella(series: dict[str, dict[str, float]]) -> str:
    base = {"version": VERSION, "series": {z: sorted(s.items()) for z, s in sorted(series.items())}}
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return "—" if not iso else f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _p(x: float | None, dec: int = 2) -> str:
    return "—" if x is None else f"{x:.{dec}f}".replace(".", ",")


def _dif(x: float | None, dec: int = 2) -> str:
    if x is None:
        return "—"
    if round(abs(x), dec) == 0:
        return _p(0, dec)
    return ("+" if x > 0 else "−") + _p(abs(x), dec)


def _meses(n: int) -> str:
    return "un mes" if n == 1 else f"{n} meses"


def _enlace(url: str, texto: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener">{texto}</a>'


def frase(res: dict) -> str:
    es = res["zonas"]["ESP"]
    lado = "por encima" if es["encima_de_100"] else "por debajo"
    direccion = "subiendo" if es["sube"] else "bajando"
    t = [f"En {mes_largo(es['mes'])}, el indicador adelantado de la OCDE para España marcó <strong>{_p(es['valor'])}</strong>: "
         f"{lado} de 100, el nivel de su tendencia de largo plazo, y {direccion} ({_dif(es['cambio_1m'])} puntos en el mes). "
         f"Es la fase que la OCDE llama «{es['fase_ocde']}» y aquí llamamos <strong>{es['fase']}</strong>."]
    t.append(f"Lleva {_meses(es['meses_en_direccion'])} {direccion} y está {lado} de 100 desde "
             f"{mes_largo(es['lado_desde']) if es['lado_desde'] else 'el comienzo de la serie'}.")
    otras = [r for z, r in res["zonas"].items() if z != "ESP"]
    if otras:
        encima = [r["nombre"] for r in otras if r["encima_de_100"]]
        t.append(f"De las otras {len(otras)} zonas de la tabla, {len(encima)} están por encima de 100.")
    rep = es["reparto_fases_pct"]
    texto = "<p>" + " ".join(t) + "</p>"
    texto += (f"\n<p>Desde {mes_largo(es['desde'])}, España ha pasado el {_p(rep['expansión'], 0)} % de los meses en expansión, el "
              f"{_p(rep['desaceleración'], 0)} % en desaceleración, el {_p(rep['enfriamiento'], 0)} % en enfriamiento y el "
              f"{_p(rep['recuperación'], 0)} % en recuperación, según este mismo indicador tal como la OCDE lo publica hoy.</p>")
    return texto


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


COLOR_FASE = {"expansión": "#2e7d4f", "desaceleración": "#c98a1b", "enfriamiento": "#b5473a", "recuperación": "#1f6fb2"}


def grafico_reloj(puntos: list[dict]) -> str:
    """El reloj: desviación de 100 (eje horizontal) y cambio en el mes (vertical) del último año de España."""
    if len(puntos) < 2:
        return ""
    W, H, m = 520, 420, 34
    xr = max(0.5, max(abs(p["desviacion"]) for p in puntos) * 1.25)
    yr = max(0.1, max(abs(p["cambio"]) for p in puntos) * 1.25)
    def X(v): return m + (v + xr) / (2 * xr) * (W - 2 * m)
    def Y(v): return m + (1 - (v + yr) / (2 * yr)) * (H - 2 * m)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" role="img" aria-label="Reloj del ciclo de España: '
         f'el último año del indicador adelantado de la OCDE" xmlns="http://www.w3.org/2000/svg">',
         '<style>.eje{font:11px sans-serif;fill:#5b6675}.fase{font:bold 12px sans-serif}</style>']
    cuadrantes = [("recuperación", m, m), ("expansión", X(0), m), ("enfriamiento", m, Y(0)), ("desaceleración", X(0), Y(0))]
    for fase, x0, y0 in cuadrantes:
        p.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{(W - 2 * m) / 2:.1f}" height="{(H - 2 * m) / 2:.1f}" fill="{COLOR_FASE[fase]}" fill-opacity="0.07"/>')
    p.append(f'<text class="fase" x="{m + 6}" y="{m + 16}" fill="{COLOR_FASE["recuperación"]}">Recuperación</text>'
             f'<text class="fase" x="{W - m - 6}" y="{m + 16}" text-anchor="end" fill="{COLOR_FASE["expansión"]}">Expansión</text>'
             f'<text class="fase" x="{m + 6}" y="{H - m - 8}" fill="{COLOR_FASE["enfriamiento"]}">Enfriamiento</text>'
             f'<text class="fase" x="{W - m - 6}" y="{H - m - 8}" text-anchor="end" fill="{COLOR_FASE["desaceleración"]}">Desaceleración</text>')
    p.append(f'<line x1="{X(0):.1f}" y1="{m}" x2="{X(0):.1f}" y2="{H - m}" stroke="#9aa5b1"/>'
             f'<line x1="{m}" y1="{Y(0):.1f}" x2="{W - m}" y2="{Y(0):.1f}" stroke="#9aa5b1"/>'
             f'<text class="eje" x="{W / 2:.1f}" y="{H - 8}" text-anchor="middle">← por debajo de 100 · indicador · por encima de 100 →</text>'
             f'<text class="eje" x="12" y="{H / 2:.1f}" text-anchor="middle" transform="rotate(-90 12 {H / 2:.1f})">← baja en el mes · sube →</text>')
    p.append('<polyline fill="none" stroke="#5b6675" stroke-width="1.2" points="'
             + " ".join(f"{X(q['desviacion']):.1f},{Y(q['cambio']):.1f}" for q in puntos) + '"/>')
    for i, q in enumerate(puntos):
        ultimo = i == len(puntos) - 1
        p.append(f'<circle cx="{X(q["desviacion"]):.1f}" cy="{Y(q["cambio"]):.1f}" r="{5 if ultimo else 2.6}" '
                 f'fill="{"#1d2733" if ultimo else "#8592a3"}"/>')
    a, b = puntos[0], puntos[-1]
    p.append(f'<text class="eje" x="{X(a["desviacion"]) + 6:.1f}" y="{Y(a["cambio"]) - 6:.1f}">{mes_corto(a["mes"])}</text>'
             f'<text class="eje" x="{X(b["desviacion"]) + 8:.1f}" y="{Y(b["cambio"]) + 4:.1f}" font-weight="bold">{mes_corto(b["mes"])}</text>')
    p.append("</svg>")
    return "".join(p)


def grafico_linea(series: dict[str, dict[str, float]]) -> str:
    """España y las cuatro grandes europeas desde 1985, con la línea de 100."""
    if "ESP" not in series:
        return ""
    W, H, ml, mr, mt, mb = 720, 260, 40, 14, 14, 26
    desde = min(series["ESP"])
    datos = {z: {k: v for k, v in s.items() if k >= desde} for z, s in series.items()}
    todos = [v for s in datos.values() for v in s.values()]
    lo, hi = min(todos), max(todos)
    lo, hi = min(lo, 99) - 0.5, max(hi, 101) + 0.5
    x0, x1 = _n(desde), max(_n(max(s)) for s in datos.values())
    def X(k): return ml + (_n(k) - x0) / max(x1 - x0, 1) * (W - ml - mr)
    def Y(v): return mt + (hi - v) / (hi - lo) * (H - mt - mb)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Indicador adelantado de la OCDE: España y cuatro grandes '
         f'economías europeas desde {mes_largo(desde)}" xmlns="http://www.w3.org/2000/svg">',
         '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.5}</style>']
    for v in range(int(lo) + 1, int(hi) + 1):
        if v % 2 == 0 or v == 100:
            p.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="{"#9aa5b1" if v == 100 else "#e3e8ef"}"/>'
                     f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v}</text>')
    for a in range(int(desde[:4]) + 1, int(_mes(x1)[:4]) + 1):
        if a % 5 == 0:
            p.append(f'<text class="eje" x="{X(f"{a}-01"):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
    colores = {"ESP": "#1f4e8c", "G4E": "#e0a44c"}
    for z in ("G4E", "ESP"):
        if z in datos and datos[z]:
            s = datos[z]
            p.append(f'<polyline class="lin" stroke="{colores[z]}" points="' + " ".join(f"{X(k):.1f},{Y(s[k]):.1f}" for k in sorted(s)) + '"/>')
    p.append(f'<text class="eje" x="{ml + 6}" y="{mt + 12}" style="fill:#1f4e8c;font-weight:bold">España</text>'
             f'<text class="eje" x="{ml + 60}" y="{mt + 12}" style="fill:#c98a1b;font-weight:bold">Cuatro grandes economías europeas</text></svg>')
    return "".join(p)


def fragmento(res: dict, marca: str, fecha_pub: str, consultado: str) -> str:
    es = res["zonas"]["ESP"]
    partes = [f"<!-- ciclo:inicio {marca} -->",
              (f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con el dato de {mes_largo(es["mes"])}, el último que publica la '
               "OCDE. La OCDE publica estos indicadores una vez al mes y revisa los meses anteriores; la página se revisa cada día hábil.</p>"),
              frase(res)]
    filas = []
    for z, r in res["zonas"].items():
        lado = f"{'por encima' if r['encima_de_100'] else 'por debajo'} desde {mes_corto(r['lado_desde']) if r['lado_desde'] else 'el inicio'}"
        nombre = f"<strong>{r['nombre']}</strong>" if z == "ESP" else r["nombre"]
        color = COLOR_FASE[r["fase"]]
        filas.append([nombre, _p(r["valor"]), _dif(r["cambio_1m"]), f'<span style="color:{color};font-weight:600">{r["fase"]}</span>',
                      _meses(r["meses_en_fase"]), lado, mes_corto(r["mes"])])
    partes += ["<h2>España y sus socios, en el último dato</h2>",
               ("<p>España, sus vecinos europeos, las grandes economías y tres emergentes (México, Brasil y Turquía). La fase sale del "
                "nivel (por encima o por debajo de 100) y de la dirección del último mes.</p>"),
               _tabla(["Zona", "Indicador", "Cambio en el mes", "Fase", "Meses en la fase", "Respecto a 100", "Dato de"], filas)]
    reloj = grafico_reloj(res["reloj"])
    if reloj:
        partes += ["<h2>El reloj de España: el último año</h2>",
                   ("<p>Cada punto es un mes: a la derecha, por encima de 100; arriba, subiendo. En un ciclo completo, el indicador recorre "
                    "los cuadrantes en el sentido de las agujas del reloj: expansión, desaceleración, enfriamiento y recuperación.</p>"),
                   f'<figure class="wp-block-image">{reloj}</figure>']
    linea = grafico_linea(res["grafico"])
    if linea:
        partes += [f"<h2>La serie desde {es['desde'][:4]}</h2>", f'<figure class="wp-block-image">{linea}</figure>']
    partes.append(
        '<h2 id="metodo">De dónde sale y cómo se lee</h2>'
        "<p>El indicador compuesto adelantado (CLI) lo calcula y publica la OCDE cada mes para las economías del G20, España y "
        "varios agregados. Combina series de corto plazo que en el pasado han girado antes que la actividad y se presenta de modo "
        "que 100 es la tendencia de largo plazo. El Especulador toma la serie principal de la OCDE (ajustada en amplitud) sin "
        "modificarla y clasifica cada mes en una de las cuatro fases que describe la OCDE: <strong>expansión</strong> (por encima de 100 "
        "y subiendo; «expansion»), <strong>desaceleración</strong> (por encima de 100 y bajando; «downturn»), <strong>enfriamiento</strong> "
        "(por debajo de 100 y bajando; «slowdown») y <strong>recuperación</strong> (por debajo de 100 y subiendo; «recovery»). La "
        "dirección es la del cambio frente al mes anterior; si el cambio es exactamente cero, se mantiene la del mes anterior. Los meses "
        "en fase, los cruces de 100 y el reparto histórico se calculan sobre la serie tal como la publica hoy la OCDE.</p>"
        "<p>Lo que dice la OCDE de su indicador (" + _enlace(GUIA, "guía de interpretación, octubre de 2020") + "; metadatos del "
        "conjunto): da información cualitativa sobre los giros del ciclo, más por la dirección que por la cifra; no mide cuánto "
        "crecerá el PIB; la distancia a 100 no es una medida de cuánto está la economía por encima o por debajo de su tendencia; "
        "los niveles no se deben comparar entre países; se revisa cada mes, y en choques como la pandemia dio señales a la vez que la "
        "actividad, no por delante. En su experiencia, los giros de la actividad han llegado de media entre cuatro y ocho meses "
        "después de la señal del indicador.</p>"
        "<p>Lectura histórica, sin predicción: la fase describe dónde está hoy el indicador de la OCDE, no lo que hará la economía "
        "ni la bolsa.</p>"
        '<p class="has-small-font-size">Fuente: OCDE, ' + _enlace(DATASET, "Composite leading indicators (CLI)") + " (conjunto "
        f"DSD_STES@DF_CLI, serie principal ajustada en amplitud), consultado el {_f(consultado)}. Datos de la OCDE reutilizados sin "
        "modificar según sus " + _enlace(TERMINOS, "términos y condiciones") + "; la OCDE no participa en esta página ni la respalda. "
        "Las fases, los meses en fase, el reparto histórico y los gráficos son de El Especulador y se publican con licencia "
        '<a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>. '
        "Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>")
    partes.append("<!-- ciclo:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Reloj del ciclo: fase de España y sus socios según los indicadores adelantados de la OCDE (El Especulador)",
        "description": "Indicador compuesto adelantado (CLI) de la OCDE para España, cuatro grandes economías europeas, Alemania, Francia, "
                       "Italia, Reino Unido, Estados Unidos, Japón, China, México, Brasil, Turquía y el G7, con la fase del ciclo de cada mes "
                       "(expansión, desaceleración, enfriamiento o recuperación) y los meses en fase.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de los Composite leading indicators de la OCDE", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": DATASET, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


# --------------------------------------------------------------------------- escritura
def _atomico(ruta: Path, texto: str) -> None:
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def escribir(series: dict, res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    try:
        antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    except ValueError:
        antes = {}
    nueva = huella(series)
    cambia = antes.get("huella") != nueva
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    consultado = hoy.isoformat() if cambia else antes.get("consultado", hoy.isoformat())
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["mes", "zona", "nombre", "valor_ocde", "cambio_en_el_mes", "fase"])
    for z, nombre in ZONAS:
        if z not in series:
            continue
        f = fases(series[z])
        for mes in sorted(series[z]):
            r = f.get(mes)
            w.writerow([mes, z, nombre, repr(series[z][mes]), "" if r is None else f"{r['cambio']:.5f}", "" if r is None else r["fase"]])
    _atomico(dd / "serie.csv", buf.getvalue())
    _atomico(previo, json.dumps({
        **{k: v for k, v in res.items() if k != "grafico"}, "version": VERSION, "fecha_publicacion": fecha_pub, "consultado": consultado,
        "huella": nueva, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "OCDE, Composite leading indicators (DSD_STES@DF_CLI), serie LI ajustada en amplitud, metodología armonizada (" + DATASET + ")",
        "condiciones": "Datos de la OCDE sin modificar, citando a la OCDE como fuente (términos de oecd.org del 01/07/2024); fases, meses en fase, "
                       "reparto y gráficos de El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1, allow_nan=False))
    frag = fragmento(res, nueva, fecha_pub, consultado)
    marca = "\n<!-- ciclo:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    _atomico(salida / "fragmento-wp.html", frag.replace(marca, "\n" + ld + marca))
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    _atomico(salida / "index.html", f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reloj del ciclo económico: España y sus socios | El Especulador</title>
<meta name="description" content="En qué fase del ciclo están España, Europa, Estados Unidos, China y los mercados de las empresas españolas según los indicadores adelantados de la OCDE: expansión, desaceleración, enfriamiento o recuperación.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Reloj del ciclo económico: España y sus socios</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/serie.csv">todas las zonas, mes a mes, con su fase</a> · <a href="datos/ultima.json">JSON</a>. Fuente: OCDE, Composite leading indicators (datos sin modificar); fases y cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="SDMX-CSV de la OCDE ya descargado (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en Madrid)")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie (tras cambiar el código)")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(MADRID).date()
    if a.local and not Path(a.local).exists():
        raise DatosRaros(f"falta {a.local}")
    texto = Path(a.local).read_text(encoding="utf-8") if a.local else descargar()
    series = leer(texto)
    res = calcular(series, hoy)
    cambia = escribir(series, res, hoy, Path(a.salida), forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::ciclo: {av}")
    es = res["zonas"]["ESP"]
    print(f"Ciclo de {es['mes']}: España {es['valor']} ({es['fase']}, {es['meses_en_fase']} meses en la fase); "
          f"{len(res['zonas'])} zonas. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::ciclo: {e}")
        sys.exit(1)
