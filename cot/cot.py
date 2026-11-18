"""Posicionamiento especulativo: cómo están colocados los grandes especuladores en los futuros que mueven a los mercados (COT de la CFTC).

Indicador 20a del catálogo de Datos de El Especulador (premium: lector de tntbolsa). Lee el informe semanal
Commitments of Traders de la CFTC (conjunto «Legacy, futures only», API Socrata, dominio público) para una
lista fija de mercados: euro, libra, yen, índice dólar, oro, plata, platino, cobre, petróleo WTI, gas natural,
S&P 500, Nasdaq 100, nota a 10 años, VIX, bitcoin, trigo, maíz y soja. Para cada uno publica la posición neta de
los no comerciales (largos menos cortos: los grandes especuladores), su variación semanal, el índice COT de tres
años (0 = el neto más corto de tres años, 100 = el más largo), el percentil de tres años, el neto sobre el
interés abierto y el neto de los comerciales (coberturistas), en <salida>/:

  fragmento-wp.html   tabla por mercado con semáforo de extremos, los cinco mercados más largos y más cortos
                      en términos de índice COT, gráfico de tres años del euro y del oro y método, entre
                      <!-- cot:inicio HUELLA --> y <!-- cot:fin -->
  index.html          página propia de la salida
  datos/ultima.json   resumen versionado
  datos/serie.csv     netos semanales de todos los mercados desde 2015 (formato largo)

Sin predicción ni recomendación: un extremo describe cómo están colocados, no lo que harán los precios.

Uso:
  python cot/cot.py --salida docs/cot
  python cot/cot.py --salida docs/cot --local respuesta.json --fecha 2026-11-14
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

VERSION = "1.0.0"
API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
PORTAL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
PAGINA_WP = "https://elespeculador.com/posicionamiento-especulativo-cot/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/cot/"
DESDE = "2015-01-01"
SEMANAS_3A = 156
# código de la CFTC -> (nombre, grupo). El nombre del mercado cambió en 2022 en la CFTC; el código no.
MERCADOS = {
    "099741": ("Euro (EUR/USD)", "divisas"), "096742": ("Libra esterlina", "divisas"), "097741": ("Yen japonés", "divisas"),
    "098662": ("Índice dólar", "divisas"), "133741": ("Bitcoin", "divisas"),
    "088691": ("Oro", "metales"), "084691": ("Plata", "metales"), "076651": ("Platino", "metales"), "085692": ("Cobre", "metales"),
    "067651": ("Petróleo WTI", "energía"), "023651": ("Gas natural (Henry Hub)", "energía"),
    "13874A": ("S&P 500 (E-mini)", "bolsa y tipos"), "209742": ("Nasdaq 100 (mini)", "bolsa y tipos"), "043602": ("Nota del Tesoro a 10 años", "bolsa y tipos"),
    "1170E1": ("VIX", "bolsa y tipos"),
    "001602": ("Trigo (SRW)", "agrícolas"), "002602": ("Maíz", "agrícolas"), "005602": ("Soja", "agrícolas"),
}
CAMPOS = ["report_date_as_yyyy_mm_dd", "cftc_contract_market_code", "market_and_exchange_names", "open_interest_all",
          "noncomm_positions_long_all", "noncomm_positions_short_all", "comm_positions_long_all", "comm_positions_short_all"]
DIAS_AVISO, DIAS_FALLO = 12, 30
AVISOS: list[str] = []


class DatosRaros(Exception):
    """La CFTC no responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga y lectura
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    esperas = [15, 30, 60, 120] if esperas is None else esperas
    ultimo = None
    codigos = ",".join(f"'{c}'" for c in MERCADOS)
    params = {"$select": ",".join(CAMPOS), "$where": f"cftc_contract_market_code in ({codigos}) AND report_date_as_yyyy_mm_dd >= '{DESDE}'",
              "$order": "report_date_as_yyyy_mm_dd", "$limit": 50000}
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(API, params=params, timeout=(20, 120), headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"})
            if r.status_code == 200 and r.text.strip().startswith("["):
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:60]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar el COT de la CFTC tras {len(esperas) + 1} intentos: {ultimo}")


def leer(texto: str) -> pd.DataFrame:
    """JSON de Socrata -> DataFrame: fecha, codigo, mercado, oi, nc_largo, nc_corto, c_largo, c_corto, neto_nc, neto_c."""
    try:
        filas = json.loads(texto)
    except json.JSONDecodeError as e:
        raise DatosRaros(f"La respuesta de la CFTC no es JSON ({e})")
    if not isinstance(filas, list) or not filas:
        raise DatosRaros("La respuesta de la CFTC está vacía")
    df = pd.DataFrame(filas)
    faltan = [c for c in CAMPOS if c not in df.columns]
    if faltan:
        raise DatosRaros(f"La respuesta de la CFTC no trae las columnas {faltan}")
    out = pd.DataFrame({"fecha": pd.to_datetime(df["report_date_as_yyyy_mm_dd"], errors="coerce"), "codigo": df["cftc_contract_market_code"].astype(str).str.strip(),
                        "mercado": df["market_and_exchange_names"].astype(str).str.strip()})
    for col, nuevo in (("open_interest_all", "oi"), ("noncomm_positions_long_all", "nc_largo"), ("noncomm_positions_short_all", "nc_corto"),
                       ("comm_positions_long_all", "c_largo"), ("comm_positions_short_all", "c_corto")):
        out[nuevo] = pd.to_numeric(df[col], errors="coerce")
    out = out.dropna(subset=["fecha", "oi", "nc_largo", "nc_corto"])
    out = out[out["codigo"].isin(MERCADOS)]
    if out.empty:
        raise DatosRaros("La respuesta de la CFTC no trae ninguno de los mercados pedidos")
    if (out[["oi", "nc_largo", "nc_corto"]] < 0).any().any():
        raise DatosRaros("Hay posiciones negativas en la respuesta de la CFTC")
    out["neto_nc"] = out["nc_largo"] - out["nc_corto"]
    out["neto_c"] = out["c_largo"] - out["c_corto"]
    out = out.drop_duplicates(["fecha", "codigo"], keep="last").sort_values(["codigo", "fecha"]).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- cálculo
def percentil(serie: pd.Series, valor: float) -> float:
    s = serie.dropna()
    return float((s <= valor).mean() * 100) if len(s) else float("nan")


def indice_cot(serie: pd.Series, valor: float) -> float | None:
    """Índice COT clásico: dónde está el neto entre el mínimo y el máximo de la ventana (0-100)."""
    s = serie.dropna()
    if len(s) < 52:
        return None
    lo, hi = float(s.min()), float(s.max())
    if hi - lo < 1e-9:
        return None
    return (float(valor) - lo) / (hi - lo) * 100


def tramo(ix: float | None, pct: float | None) -> str:
    if ix is None or pct is None:
        return "sin historial suficiente"
    if ix >= 90 or pct >= 90:
        return "largo extremo"
    if ix >= 75 or pct >= 75:
        return "largo"
    if ix <= 10 or pct <= 10:
        return "corto extremo"
    if ix <= 25 or pct <= 25:
        return "corto"
    return "zona media"


def calcular(df: pd.DataFrame, hoy: date) -> dict:
    ultima = df["fecha"].max()
    desfase = (hoy - ultima.date()).days
    if desfase > DIAS_FALLO:
        raise DatosRaros(f"El último informe de la CFTC es del {ultima.date()}: más de {DIAS_FALLO} días")
    if desfase > DIAS_AVISO:
        AVISOS.append(f"El último informe de la CFTC es del {ultima.date()} ({desfase} días; la CFTC retrasa la publicación en festivos)")
    mercados = {}
    for codigo, (nombre, grupo) in MERCADOS.items():
        s = df[df["codigo"] == codigo].set_index("fecha").sort_index()
        if s.empty:
            AVISOS.append(f"{nombre} ({codigo}): sin datos en la respuesta de la CFTC")
            continue
        f = s.index.max()
        if (ultima - f).days > 21:
            AVISOS.append(f"{nombre} ({codigo}): su último informe es del {f.date()}, anterior al general ({ultima.date()})")
        tres = s[s.index > f - timedelta(weeks=SEMANAS_3A)]["neto_nc"]
        neto = float(s.loc[f, "neto_nc"])
        prev = s[s.index < f]
        neto_prev = float(prev["neto_nc"].iloc[-1]) if len(prev) else None
        hace4 = s[s.index <= f - timedelta(weeks=4)]
        neto_4s = float(hace4["neto_nc"].iloc[-1]) if len(hace4) else None
        ix = indice_cot(tres, neto)
        pct = percentil(tres, neto) if len(tres) >= 52 else None
        oi = float(s.loc[f, "oi"])
        mercados[codigo] = {"nombre": nombre, "grupo": grupo, "mercado_cftc": str(s.loc[f, "mercado"]), "fecha": f.date().isoformat(),
                            "neto_especuladores": int(neto), "largos": int(s.loc[f, "nc_largo"]), "cortos": int(s.loc[f, "nc_corto"]),
                            "variacion_semana": int(neto - neto_prev) if neto_prev is not None else None,
                            "variacion_4_semanas": int(neto - neto_4s) if neto_4s is not None else None,
                            "interes_abierto": int(oi), "neto_sobre_oi": round(neto / oi * 100, 1) if oi else None,
                            "neto_comerciales": int(s.loc[f, "neto_c"]) if pd.notna(s.loc[f, "neto_c"]) else None,
                            "indice_cot_3a": round(ix, 1) if ix is not None else None, "percentil_3a": round(pct, 1) if pct is not None else None,
                            "semanas_3a": int(len(tres)), "tramo": tramo(ix, pct),
                            "max_3a": int(tres.max()), "fecha_max_3a": tres.idxmax().date().isoformat(), "min_3a": int(tres.min()), "fecha_min_3a": tres.idxmin().date().isoformat()}
    if not mercados:
        raise DatosRaros("Ningún mercado con datos")
    con_ix = [m for m in mercados.values() if m["indice_cot_3a"] is not None]
    largos = sorted(con_ix, key=lambda m: -m["indice_cot_3a"])[:5]
    cortos = sorted(con_ix, key=lambda m: m["indice_cot_3a"])[:5]
    extremos = [m for m in con_ix if m["tramo"] in ("largo extremo", "corto extremo")]
    return {"fecha": ultima.date().isoformat(), "desfase_dias": desfase, "mercados": mercados, "mas_largos": [m["nombre"] for m in largos],
            "mas_cortos": [m["nombre"] for m in cortos], "extremos": [(m["nombre"], m["tramo"]) for m in extremos],
            "primera_fecha": df["fecha"].min().date().isoformat(), "observaciones": int(len(df))}


def huella(res: dict) -> str:
    base = {"version": VERSION, "fecha": res["fecha"], "netos": {c: m["neto_especuladores"] for c, m in res["mercados"].items()}}
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _n(x: int | float | None, signo: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{abs(x):,.0f}".replace(",", ".")
    return ("−" if x < 0 else ("+" if signo and x > 0 else "")) + s


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_svg(df: pd.DataFrame, codigos: list[str], fecha: pd.Timestamp) -> str:
    """Neto de los especuladores, tres años, un panel por mercado (en miles de contratos)."""
    W, H, ml, mr, mt, mb = 720, 200, 48, 12, 14, 26
    partes = []
    colores = ["#1f4e8c", "#e0a44c", "#2a9d8f", "#c0392b"]
    for k, codigo in enumerate(codigos):
        s = df[(df["codigo"] == codigo) & (df["fecha"] > fecha - timedelta(weeks=SEMANAS_3A)) & (df["fecha"] <= fecha)].set_index("fecha")["neto_nc"].sort_index() / 1000
        if s.empty:
            continue
        nombre = MERCADOS[codigo][0]
        y0, y1 = min(0.0, float(s.min()) * 1.05), max(0.0, float(s.max()) * 1.05)
        if y1 - y0 < 1e-9:
            continue
        x0, x1 = s.index.min(), s.index.max()
        def X(t): return ml + (t - x0) / max((x1 - x0), pd.Timedelta(days=1)) * (W - ml - mr)
        def Y(v): return mt + (1 - (v - y0) / (y1 - y0)) * (H - mt - mb)
        p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Neto de los especuladores en {nombre}, tres años" xmlns="http://www.w3.org/2000/svg">',
             '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
        for i in range(5):
            v = y0 + (y1 - y0) * i / 4
            p.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                     f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
        if y0 < 0 < y1:
            p.append(f'<line x1="{ml}" y1="{Y(0):.1f}" x2="{W - mr}" y2="{Y(0):.1f}" stroke="#9aa5b1" stroke-dasharray="4 3"/>')
        for a in range(x0.year, x1.year + 1):
            t = pd.Timestamp(year=a, month=1, day=1)
            if x0 <= t <= x1:
                p.append(f'<text class="eje" x="{X(t):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
        puntos = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        p.append(f'<polyline class="lin" stroke="{colores[k % 4]}" points="{puntos}"/>')
        p.append(f'<text class="eje" x="{ml + 6}" y="{mt + 12}" fill="{colores[k % 4]}">{nombre}, miles de contratos netos</text></svg>')
        partes.append('<figure class="wp-block-image">' + "".join(p) + "</figure>")
    return "\n".join(partes)


def fragmento(res: dict, df: pd.DataFrame, fecha_pub: str) -> str:
    m = res["mercados"]
    ext = res["extremos"]
    frase = (f"Con el informe del {_f(res['fecha'])}, los grandes especuladores están más largos, en términos de tres años, en "
             f"{', '.join(res['mas_largos'][:3])}, y más cortos en {', '.join(res['mas_cortos'][:3])}. ")
    if ext:
        frase += "En extremo de tres años: " + "; ".join(f"{n} ({t})" for n, t in ext) + "."
    else:
        frase += "Ningún mercado está en un extremo de tres años."
    eur = m.get("099741")
    if eur:
        frase += (f" En el euro, el neto es de {_n(eur['neto_especuladores'])} contratos ({_n(eur['variacion_semana'], True)} en la semana), índice COT "
                  f"{eur['indice_cot_3a']:.0f} de 100.") if eur["indice_cot_3a"] is not None else ""
    filas = []
    for grupo in ("divisas", "metales", "energía", "bolsa y tipos", "agrícolas"):
        for c, v in m.items():
            if v["grupo"] != grupo:
                continue
            filas.append([f"<strong>{v['nombre']}</strong>", _n(v["neto_especuladores"]), _n(v["variacion_semana"], True), _n(v["variacion_4_semanas"], True),
                          f"{v['neto_sobre_oi']:+.1f} %".replace(".", ",").replace("-", "−") if v["neto_sobre_oi"] is not None else "—",
                          f"{v['indice_cot_3a']:.0f}" if v["indice_cot_3a"] is not None else "—", f"{v['percentil_3a']:.0f}" if v["percentil_3a"] is not None else "—",
                          v["tramo"], _n(v["neto_comerciales"])])
    partes = [f"<!-- cot:inicio {res['huella']} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con el informe Commitments of Traders de la CFTC con datos del martes {_f(res["fecha"])} '
              "(publicado el viernes siguiente). Contratos de futuros; neto = largos − cortos de los no comerciales (grandes especuladores).</p>",
              "<p>" + frase + "</p>",
              "<h2>Mercado por mercado</h2>",
              _tabla(["Mercado", "Neto especuladores", "Semana", "4 semanas", "Neto / interés abierto", "Índice COT 3 años", "Percentil 3 años", "Lectura", "Neto comerciales"], filas),
              '<p class="has-small-font-size">Índice COT: 0 es el neto más corto de los últimos tres años y 100 el más largo. Percentil: porcentaje de semanas de tres años con un '
              "neto igual o menor. Lectura: «largo extremo» o «corto extremo» desde 90 o hasta 10 en cualquiera de los dos; «largo» o «corto» desde 75 o hasta 25; en medio, «zona media». "
              "Los comerciales son los que usan el futuro para cubrir su negocio (productores, bancos): suelen ir al revés de los especuladores.</p>",
              "<h2>Tres años de posicionamiento</h2>",
              grafico_svg(df, ["099741", "088691", "067651", "13874A"], pd.Timestamp(res["fecha"])),
              '<h2 id="metodo">Qué es y cómo se lee</h2>'
              "<p>Cada viernes la CFTC publica cómo estaban repartidas, el martes anterior, las posiciones abiertas en cada futuro de EE. UU. entre tres grupos: "
              "los no comerciales (fondos y grandes especuladores), los comerciales (quienes cubren un negocio real) y los pequeños. El Especulador toma el "
              "informe «Legacy, futures only» por el código de cada mercado, sin modificar las cifras, y calcula el neto de los especuladores, sus variaciones, "
              "el índice COT y el percentil sobre una ventana de tres años (156 semanas; con menos de 52 no se publica), y el neto sobre el interés abierto. "
              "Históricamente, los extremos de posicionamiento han coincidido con fases en las que el mercado tenía poco combustible para seguir en la misma "
              "dirección, pero un extremo puede durar meses: esta página describe cómo están colocados los grandes especuladores, no lo que hará el precio, "
              "y no es una señal de compra ni de venta.</p>"
              f'<p class="has-small-font-size">Fuente: CFTC, <a href="{PORTAL}">Commitments of Traders</a> (informe Legacy, futures only, API pública), datos desde {_f(res["primera_fecha"])}. '
              "Obra del Gobierno de Estados Unidos, de dominio público; los cálculos (neto, índice COT, percentiles) son de El Especulador y se publican con licencia CC BY 4.0. "
              "Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>",
              "<!-- cot:fin -->"]
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Posicionamiento de los grandes especuladores en los futuros de EE. UU. (COT de la CFTC, El Especulador)",
        "description": "Neto de los no comerciales, índice COT y percentil de tres años en euro, libra, yen, índice dólar, bitcoin, oro, plata, platino, cobre, "
                       "petróleo, gas natural, S&P 500, Nasdaq 100, nota a 10 años, VIX, trigo, maíz y soja, cada semana.",
        "url": PAGINA_WP, "inLanguage": "es",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir del informe Commitments of Traders de la CFTC", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": PORTAL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(df: pd.DataFrame, res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    cambia = antes.get("huella") != res["huella"]
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    largo = df.copy()
    largo["nombre"] = largo["codigo"].map(lambda c: MERCADOS[c][0])
    largo["fecha"] = largo["fecha"].dt.date
    largo[["fecha", "codigo", "nombre", "oi", "nc_largo", "nc_corto", "neto_nc", "c_largo", "c_corto", "neto_c"]].sort_values(["codigo", "fecha"]).to_csv(dd / "serie.csv", index=False)
    previo.write_text(json.dumps({**res, "version": VERSION, "fecha_publicacion": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "fuente": "CFTC, Commitments of Traders (Legacy, futures only), API pública",
                                  "condiciones": "Obra del Gobierno de EE. UU., dominio público; neto, índice COT y percentiles de El Especulador (CC BY 4.0). "
                                                 "Contenido informativo; no es asesoramiento financiero."},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, df, fecha_pub)
    marca = "\n<!-- cot:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Posicionamiento especulativo (COT de la CFTC) | El Especulador</title>
<meta name="description" content="Cómo están colocados los grandes especuladores en los futuros de divisas, metales, energía, bolsa, tipos y agrícolas, con el índice COT y el percentil de tres años.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} table{{border-collapse:collapse;width:100%;font-size:.9rem}} th,td{{border-bottom:1px solid #e3e8ef;padding:4px 6px;text-align:left}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Posicionamiento especulativo (COT)</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/serie.csv">netos semanales desde 2015</a> · <a href="datos/ultima.json">JSON</a>. Fuente: CFTC (dominio público); cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="JSON de la API ya descargado (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else date.today()
    texto = Path(a.local).read_text(encoding="utf-8") if a.local else descargar()
    df = leer(texto)
    res = calcular(df, hoy)
    res["huella"] = huella(res)
    cambia = escribir(df, res, hoy, Path(a.salida), forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    print(f"Informe del {res['fecha']}: {len(res['mercados'])} mercados; más largos {res['mas_largos'][:3]}; más cortos {res['mas_cortos'][:3]}; "
          f"extremos {res['extremos']}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
