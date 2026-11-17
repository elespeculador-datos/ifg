"""Semáforo de la prima de riesgo: la deuda española frente a Alemania, Italia y Francia.

Indicador 3 del catálogo de Datos de El Especulador. Lee de Eurostat los tipos de interés
a largo plazo del criterio de convergencia (rendimiento del bono a diez años en el mercado
secundario, dato diario recogido por el BCE de los bancos centrales nacionales) de España,
Alemania, Italia y Francia, y publica:

  <salida>/fragmento-wp.html   texto, tablas y gráfico entre <!-- prima:inicio HUELLA --> y <!-- prima:fin -->
  <salida>/index.html          página propia de la salida
  <salida>/datos/serie.csv     rendimientos (%) y diferenciales (puntos básicos), formato largo
  <salida>/datos/ultima.json   resumen versionado para webs y widgets

Fuente: Eurostat, conjunto irt_lt_mcby_d. Política de Eurostat: reutilización libre, también
comercial, citando «Fuente: Eurostat» y declarando las modificaciones. Los rendimientos se
reproducen sin modificar; los diferenciales, percentiles, variaciones y episodios son cálculos
propios de El Especulador (CC BY 4.0). El pulso del Tesoro sale de las salidas de letras/ y
bonos/ (D. G. del Tesoro y Política Financiera), si están al lado de la de este colector.

Uso:
  python prima/prima.py --salida docs/prima                 descarga y publica
  python prima/prima.py --salida docs/prima --local F.json  usa una respuesta JSON-stat ya descargada
  python prima/prima.py --salida docs/prima --fecha 2026-11-17   fija el día (pruebas)
  python prima/prima.py --salida docs/prima --tesoro /var/www/datos   carpeta con letras/ y bonos/
"""
from __future__ import annotations

import argparse
import csv
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
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_d"
PAISES = {"ES": "España", "DE": "Alemania", "IT": "Italia", "FR": "Francia"}
PARAMS = [("format", "JSON"), ("lang", "EN")] + [("geo", p) for p in PAISES]
PORTAL = "https://ec.europa.eu/eurostat/databrowser/view/irt_lt_mcby_d/default/table?lang=en"
METADATOS = "https://ec.europa.eu/eurostat/cache/metadata/en/irt_lt_mcby_esms.htm"
PAGINA_WP = "https://elespeculador.com/prima-de-riesgo-espana/"
# Dirección pública de la salida. Sin la variable de entorno, GitHub Pages (valor histórico);
# en el servidor smpro-datos-1, ESPEC_DATOS_BASE vale https://datos.elespeculador.com/.
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/prima/"
METODOLOGIA = PAGINA_WP + "#metodo"

# Diferenciales que se publican, en puntos básicos: (nombre, país que paga, país de referencia).
DIFERENCIALES = [("es_de", "ES", "DE"), ("it_de", "IT", "DE"), ("fr_de", "FR", "DE"), ("es_it", "ES", "IT"), ("es_fr", "ES", "FR")]
NOMBRE_DIF = {"es_de": "España-Alemania", "it_de": "Italia-Alemania", "fr_de": "Francia-Alemania",
              "es_it": "España-Italia", "es_fr": "España-Francia"}
DESDE_HISTORICO = "2000-01-01"   # el percentil histórico se calcula desde aquí (toda la vida del euro)
VENTANA_SEMAFORO_DIAS = 3 * 365  # el semáforo compara con los últimos tres años
# Episodios de referencia: ventanas fijadas de antemano; se publica el máximo que marcó el
# diferencial España-Alemania dentro de cada una (dato, no decisión).
EPISODIOS = [
    ("Crisis del Sistema Monetario Europeo", "1992-08-01", "1993-08-31"),
    ("Quiebra de Lehman Brothers", "2008-09-01", "2009-03-31"),
    ("Crisis del euro", "2010-04-01", "2012-12-31"),
    ("Pandemia", "2020-02-15", "2020-06-30"),
    ("Subida de tipos del BCE", "2022-02-24", "2022-12-31"),
]
TRAMOS = [(90, "muy alto"), (75, "alto"), (50, "por encima de lo habitual"), (25, "habitual"), (0, "bajo")]
SEMAFORO = [(90, "rojo"), (50, "ámbar"), (0, "verde")]
AVISOS: list[str] = []


class DatosRaros(Exception):
    """Eurostat no responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    """Devuelve la respuesta JSON-stat de Eurostat. Reintenta con esperas crecientes."""
    esperas = [15, 30, 60, 120] if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(API, params=PARAMS, timeout=(20, 120),
                             headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/json"})
            if r.status_code == 200 and '"value"' in r.text:
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:300]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar irt_lt_mcby_d de Eurostat tras {len(esperas) + 1} intentos: {ultimo}")


# --------------------------------------------------------------------------- lectura
def leer(texto: str) -> tuple[pd.DataFrame, dict]:
    """JSON-stat 2.0 de Eurostat -> (DataFrame largo con fecha, pais y valor, metadatos).

    El formato es autodescriptivo: `id` da el orden de las dimensiones, `size` su tamaño y
    cada dimensión trae el índice de sus categorías. Los valores vienen en `value` como un
    diccionario «posición -> valor» (solo las celdas con dato) o como una lista. Se localizan
    las dimensiones por su nombre (geo, time), no por su posición.
    """
    try:
        d = json.loads(texto)
    except json.JSONDecodeError as e:
        raise DatosRaros(f"La respuesta de Eurostat no es JSON: {e}") from None
    if "error" in d and "value" not in d:
        raise DatosRaros(f"Eurostat devuelve un error: {str(d['error'])[:300]}")
    for campo in ("id", "size", "dimension", "value"):
        if campo not in d:
            raise DatosRaros(f"La respuesta JSON-stat no trae el campo {campo}; campos: {list(d)[:12]}")
    ids, tam = list(d["id"]), list(d["size"])
    if "geo" not in ids or "time" not in ids:
        raise DatosRaros(f"Faltan las dimensiones geo o time: {ids}")

    def categorias(dim: str) -> list[str]:
        idx = d["dimension"][dim]["category"]["index"]
        if isinstance(idx, dict):
            return [k for k, _ in sorted(idx.items(), key=lambda kv: kv[1])]
        return list(idx)

    cats = {dim: categorias(dim) for dim in ids}
    for dim in ids:
        if len(cats[dim]) != tam[ids.index(dim)]:
            raise DatosRaros(f"La dimensión {dim} declara {tam[ids.index(dim)]} categorías y trae {len(cats[dim])}")
    # Las dimensiones que no son geo ni time deben tener una sola categoría (freq=D, int_rt=MCBY).
    for dim in ids:
        if dim not in ("geo", "time") and len(cats[dim]) != 1:
            raise DatosRaros(f"La dimensión {dim} trae {len(cats[dim])} categorías ({cats[dim][:5]}): se esperaba una sola")
    pasos = []  # tamaño del salto de cada dimensión en el índice lineal (orden fila mayor)
    acumulado = 1
    for n in reversed(tam):
        pasos.insert(0, acumulado)
        acumulado *= n
    paso_geo, paso_time = pasos[ids.index("geo")], pasos[ids.index("time")]
    valores = d["value"]
    if isinstance(valores, list):
        valores = {i: v for i, v in enumerate(valores) if v is not None}
    filas = []
    for i_geo, geo in enumerate(cats["geo"]):
        if geo not in PAISES:
            continue
        for i_t, t in enumerate(cats["time"]):
            v = valores.get(str(i_geo * paso_geo + i_t * paso_time))
            if v is None:
                v = valores.get(i_geo * paso_geo + i_t * paso_time)
            if v is None:
                continue
            filas.append((t, geo, v))
    df = pd.DataFrame(filas, columns=["fecha", "pais", "valor"])
    if df.empty:
        raise DatosRaros("Eurostat no ha devuelto ningún valor para los países pedidos")
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna().sort_values(["pais", "fecha"]).drop_duplicates(["pais", "fecha"], keep="last").reset_index(drop=True)
    faltan = [p for p in PAISES if p not in set(df["pais"])]
    if faltan:
        raise DatosRaros(f"Eurostat no ha devuelto datos de {', '.join(PAISES[p] for p in faltan)}")
    n_es = int((df["pais"] == "ES").sum())
    if n_es < 2000:
        raise DatosRaros(f"El rendimiento español trae {n_es} observaciones: demasiado pocas para una serie diaria desde los años noventa")
    if ((df["valor"] < -3) | (df["valor"] > 40)).any():
        raise DatosRaros("Hay rendimientos fuera del rango -3 % a 40 %: el conjunto ha cambiado de unidad o de criterio")
    meta = {"etiqueta": d.get("label"), "actualizado": d.get("updated"), "fuente": d.get("source")}
    return df, meta


# --------------------------------------------------------------------------- cálculos
def percentil(serie: pd.Series, valor: float) -> float:
    """Porcentaje de observaciones de la serie menores o iguales que el valor (definición «débil»)."""
    s = serie.dropna()
    return float((s <= valor).mean() * 100) if len(s) else float("nan")


def tramo(p: float) -> str:
    for umbral, nombre in TRAMOS:
        if p >= umbral:
            return nombre
    return TRAMOS[-1][1]


def semaforo(p: float) -> str:
    for umbral, nombre in SEMAFORO:
        if p >= umbral:
            return nombre
    return SEMAFORO[-1][1]


def variacion(s: pd.Series, fecha: pd.Timestamp, dias: int) -> float | None:
    """Diferencia entre el valor en `fecha` y el último valor disponible `dias` días antes (o anterior)."""
    antes = s[s.index <= fecha - timedelta(days=dias)]
    if antes.empty:
        return None
    return float(s.loc[fecha] - antes.iloc[-1])


def ultima_vez_igual_o_mayor(s: pd.Series, fecha: pd.Timestamp, valor: float, margen_dias: int = 180) -> str | None:
    """Última fecha, al menos `margen_dias` antes, en que la serie estuvo igual o por encima del valor actual."""
    s = s[s.index <= fecha - timedelta(days=margen_dias)]
    s = s[s >= valor]
    return s.index[-1].date().isoformat() if len(s) else None


def episodios(s: pd.Series) -> list[dict]:
    salida = []
    for nombre, desde, hasta in EPISODIOS:
        trozo = s[(s.index >= desde) & (s.index <= hasta)]
        if trozo.empty:
            continue
        salida.append({"episodio": nombre, "desde": desde, "hasta": hasta,
                       "maximo": round(float(trozo.max()), 1), "fecha_maximo": trozo.idxmax().date().isoformat()})
    return salida


def diferenciales(niveles: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Diferenciales en puntos básicos, solo en las fechas en que los dos países tienen dato (misma fecha)."""
    out = {}
    for nombre, a, b in DIFERENCIALES:
        if a in niveles and b in niveles:
            d = ((niveles[a] - niveles[b]) * 100).dropna()
            if not d.empty:
                out[nombre] = d.round(1)
    return out


def _r(x: float | None, dec: int = 1) -> float | None:
    return None if x is None or pd.isna(x) else round(float(x), dec)


def _ficha(s: pd.Series, f: pd.Timestamp, hoy: date, dec: int) -> dict:
    v = float(s.loc[f])
    hist = s[s.index >= DESDE_HISTORICO]
    tres = s[s.index > f - timedelta(days=VENTANA_SEMAFORO_DIAS)]
    p = percentil(hist, v)
    p3 = percentil(tres, v)
    return {
        "fecha": f.date().isoformat(), "valor": round(v, dec), "desde": s.index[0].date().isoformat(), "observaciones": int(len(s)),
        "percentil_historico": _r(p), "tramo_historico": tramo(p), "desde_historico": hist.index[0].date().isoformat() if len(hist) else None,
        "percentil_3a": _r(p3), "semaforo": semaforo(p3),
        "variacion_1s": _r(variacion(s, f, 7), dec), "variacion_4s": _r(variacion(s, f, 28), dec),
        "variacion_13s": _r(variacion(s, f, 91), dec), "variacion_52s": _r(variacion(s, f, 364), dec),
        "maximo_historico": round(float(hist.max()), dec) if len(hist) else None,
        "fecha_maximo_historico": hist.idxmax().date().isoformat() if len(hist) else None,
        "minimo_historico": round(float(hist.min()), dec) if len(hist) else None,
        "fecha_minimo_historico": hist.idxmin().date().isoformat() if len(hist) else None,
        "ultima_vez_igual_o_mayor": ultima_vez_igual_o_mayor(s, f, v),
    }


def calcular(df: pd.DataFrame, hoy: date, tesoro: dict | None = None) -> dict:
    niveles = {p: g.set_index("fecha")["valor"].sort_index() for p, g in df.groupby("pais")}
    difs = diferenciales(niveles)
    if "es_de" not in difs:
        raise DatosRaros("No hay fechas comunes entre los rendimientos de España y Alemania")
    es_de = difs["es_de"]
    f = es_de.index[-1]
    res = {"fecha": f.date().isoformat(), "desfase_dias": (hoy - f.date()).days, "niveles": {}, "diferenciales": {}}
    if res["desfase_dias"] > 7:
        AVISOS.append(f"El último diferencial España-Alemania es del {res['fecha']}: {res['desfase_dias']} días de desfase")
    if res["desfase_dias"] > 45:
        raise DatosRaros(f"El diferencial lleva {res['desfase_dias']} días sin dato nuevo: comprobar Eurostat")
    for p, s in niveles.items():
        fp = s.index[-1]
        res["niveles"][p] = {"pais": PAISES[p], **_ficha(s, fp, hoy, 2)}
    for n, s in difs.items():
        res["diferenciales"][n] = {"nombre": NOMBRE_DIF[n], **_ficha(s, s.index[-1], hoy, 1)}
    # Fechas distintas entre series: se avisa, no se mezcla (cada ficha lleva su fecha).
    fechas = {v["fecha"] for v in res["niveles"].values()}
    if len(fechas) > 1:
        AVISOS.append("Los países no comparten la última fecha: " + ", ".join(f"{v['pais']} {v['fecha']}" for v in res["niveles"].values()))
    res["episodios"] = episodios(es_de)
    orden = sorted(res["niveles"].values(), key=lambda v: v["valor"], reverse=True)
    res["ranking"] = [v["pais"] for v in orden]
    desde = pd.Timestamp(f) - pd.Timedelta(days=VENTANA_SEMAFORO_DIAS)
    res["grafico"] = {n: difs[n][difs[n].index >= desde] for n in ("es_de", "it_de", "fr_de") if n in difs}
    res["tesoro"] = tesoro or {}
    return res


# --------------------------------------------------------------------------- pulso del Tesoro
def leer_tesoro(carpeta: Path | None) -> dict:
    """Última subasta de letras a 12 meses y de obligaciones a 10 años, de las salidas de letras/ y bonos/.

    Son datos de la D. G. del Tesoro y Política Financiera que ya publican esos colectores; aquí
    solo se reproducen. Si las salidas no están, el bloque no se publica (no se inventa nada).
    """
    out: dict = {}
    if carpeta is None:
        return out
    try:
        ruta = carpeta / "letras" / "datos" / "ultima.json"
        if ruta.exists():
            d = json.loads(ruta.read_text(encoding="utf-8"))
            u = (d.get("ultimas") or {}).get("12")
            if u and u.get("marginal") is not None and u.get("fecha"):
                sol, adj = u.get("solicitado"), u.get("adjudicado")
                out["letras_12m"] = {"fecha": u["fecha"], "marginal": float(u["marginal"]),
                                     "cobertura": round(sol / adj, 2) if sol and adj else None, "fuente": d.get("fuente")}
        ruta = carpeta / "bonos" / "datos" / "ultima.json"
        if ruta.exists():
            d = json.loads(ruta.read_text(encoding="utf-8"))
            diez = [u for u in (d.get("ultimas") or []) if isinstance(u, dict) and u.get("plazo") == 10
                    and u.get("marginal") is not None and u.get("fecha") and not u.get("indexado")]
            if diez:
                u = max(diez, key=lambda x: x["fecha"])
                out["obligaciones_10a"] = {"fecha": u["fecha"], "marginal": float(u["marginal"]), "denominacion": u.get("denominacion"),
                                           "cobertura": u.get("cobertura"), "fuente": d.get("fuente")}
    except (OSError, ValueError, TypeError, ZeroDivisionError) as e:
        AVISOS.append(f"No se ha podido leer el pulso del Tesoro: {e}")
        return {}
    return out


def huella(res: dict) -> str:
    base = {n: [v["fecha"], v["valor"]] for n, v in res["niveles"].items()}
    base.update({n: [v["fecha"], v["valor"]] for n, v in res["diferenciales"].items()})
    base["tesoro"] = {k: [v.get("fecha"), v.get("marginal")] for k, v in res["tesoro"].items()}
    base["version"] = VERSION
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return "—" if not iso else pd.Timestamp(iso).strftime("%d/%m/%Y")


def _v(x: float | None, dec: int = 1) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:.{dec}f}".replace(".", ",")


def _dif(x: float | None, dec: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    if abs(x) < 0.5 * 10 ** (-dec):
        return _v(0.0, dec)
    return ("+" if x > 0 else "") + f"{x:.{dec}f}".replace(".", ",")


def _pb(x: float | None) -> str:
    """Variación de un rendimiento (puntos porcentuales) expresada en puntos básicos enteros."""
    return "—" if x is None or pd.isna(x) else _dif(x * 100, 0)


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_svg(series: dict[str, pd.Series]) -> str:
    """Diferenciales frente a Alemania, últimos tres años, en SVG sin dependencias. Atributos con punto decimal."""
    W, H, ml, mr, mt, mb = 720, 260, 44, 12, 10, 28
    series = {n: s for n, s in series.items() if not s.empty}
    if not series:
        return ""
    todas = pd.concat(series.values())
    x0, x1 = todas.index.min(), todas.index.max()
    y0 = min(0.0, float(todas.min()))
    y1 = max(10.0, float(todas.max()) * 1.1)
    def X(t): return ml + (t - x0) / max((x1 - x0), pd.Timedelta(days=1)) * (W - ml - mr)
    def Y(v): return mt + (1 - (v - y0) / (y1 - y0)) * (H - mt - mb)
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Prima de riesgo frente a Alemania: España, Italia y Francia, últimos tres años" xmlns="http://www.w3.org/2000/svg">',
              '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
    for i in range(5):
        v = y0 + (y1 - y0) * i / 4
        partes.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                      f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    for a in range(x0.year, x1.year + 1):
        t = pd.Timestamp(year=a, month=1, day=1)
        if x0 <= t <= x1:
            partes.append(f'<text class="eje" x="{X(t):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
    colores = {"es_de": "#1f4e8c", "it_de": "#c0392b", "fr_de": "#e0a44c"}
    for n, s in series.items():
        puntos = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        partes.append(f'<polyline class="lin" stroke="{colores.get(n, "#888")}" points="{puntos}"/>')
    x = ml + 6
    for n, texto in (("es_de", "España"), ("it_de", "Italia"), ("fr_de", "Francia")):
        if n in series:
            partes.append(f'<text class="eje" x="{x}" y="{mt + 14}" fill="{colores[n]}">{texto}</text>')
            x += 58
    partes.append(f'<text class="eje" x="{W - mr}" y="{mt + 14}" text-anchor="end">puntos básicos</text></svg>')
    return "".join(partes)


def fragmento(res: dict, fecha_pub: str) -> str:
    es_de = res["diferenciales"]["es_de"]
    es, de = res["niveles"]["ES"], res["niveles"]["DE"]
    partes = [f"<!-- prima:inicio {huella(res)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con los rendimientos de Eurostat del {_f(es_de["fecha"])}.</p>']
    frase = (f"<p><strong>Semáforo: {es_de['semaforo']}.</strong> La prima de riesgo de España (diferencial entre el bono español y el alemán "
             f"a diez años) marcó <strong>{_v(es_de['valor'])} puntos básicos</strong> el {_f(es_de['fecha'])}: el bono español rendía el "
             f"{_v(es['valor'], 2)} % y el alemán el {_v(de['valor'], 2)} %. Frente a los últimos tres años está en el percentil "
             f"{_v(es_de['percentil_3a'], 0)} (ha estado igual o más baja el {_v(es_de['percentil_3a'], 0)} % de las sesiones); "
             f"desde {es_de['desde_historico'][:4]}, en el percentil {_v(es_de['percentil_historico'], 0)}, un nivel {es_de['tramo_historico']} "
             f"en términos históricos.")
    if es_de["ultima_vez_igual_o_mayor"]:
        frase += f" La última vez que estuvo igual o más alta, sin contar los últimos seis meses, fue el {_f(es_de['ultima_vez_igual_o_mayor'])}."
    frase += (f" En una semana ha variado {_dif(es_de['variacion_1s'])} puntos básicos; en cuatro, {_dif(es_de['variacion_4s'])}; en trece, "
              f"{_dif(es_de['variacion_13s'])}; en un año, {_dif(es_de['variacion_52s'])}. Máximo desde {es_de['desde_historico'][:4]}: "
              f"{_v(es_de['maximo_historico'])} puntos básicos el {_f(es_de['fecha_maximo_historico'])}.</p>")
    partes.append(frase)
    partes += ["<h2>Los cuatro bonos a diez años</h2>",
               "<p>Rendimiento del bono a diez años en el mercado secundario, del más alto al más bajo. Es el tipo de interés al que cada "
               "Estado se financia a largo plazo en el mercado.</p>",
               _tabla(["País", "Rendimiento a 10 años", "1 semana (pb)", "4 semanas (pb)", "1 año (pb)", "Percentil desde 2000", "Dato del"],
                      [[v["pais"], _v(v["valor"], 2) + " %", _pb(v["variacion_1s"]), _pb(v["variacion_4s"]), _pb(v["variacion_52s"]),
                        _v(v["percentil_historico"], 0), _f(v["fecha"])]
                       for p in res["ranking"] for v in [next(x for x in res["niveles"].values() if x["pais"] == p)]])]
    partes += ["<h2>Diferenciales: quién paga más que quién</h2>",
               "<p>En puntos básicos (100 puntos básicos = 1 punto porcentual). Un diferencial positivo significa que el primer país paga "
               "más que el segundo por financiarse a diez años.</p>",
               _tabla(["Diferencial", "Puntos básicos", "1 semana", "4 semanas", "13 semanas", "1 año", "Percentil 3 años", "Percentil desde 2000", "Semáforo"],
                      [[v["nombre"], _v(v["valor"]), _dif(v["variacion_1s"]), _dif(v["variacion_4s"]), _dif(v["variacion_13s"]), _dif(v["variacion_52s"]),
                        _v(v["percentil_3a"], 0), _v(v["percentil_historico"], 0), v["semaforo"]]
                       for n, _, _ in DIFERENCIALES if (v := res["diferenciales"].get(n))])]
    t = res.get("tesoro") or {}
    if t:
        filas = []
        if "letras_12m" in t:
            l = t["letras_12m"]
            filas.append(["Letras a 12 meses", _f(l["fecha"]), _v(l["marginal"], 3) + " %", _v(l.get("cobertura"), 2) if l.get("cobertura") else "—"])
        if "obligaciones_10a" in t:
            o = t["obligaciones_10a"]
            filas.append([f"Obligaciones a 10 años ({o['denominacion']})" if o.get("denominacion") else "Obligaciones a 10 años",
                          _f(o["fecha"]), _v(o["marginal"], 3) + " %", _v(o.get("cobertura"), 2) if o.get("cobertura") else "—"])
        if filas:
            partes += ["<h2>El pulso del Tesoro: las últimas subastas</h2>",
                       "<p>Tipo marginal y ratio de cobertura (dinero pedido entre dinero adjudicado) de la última subasta de cada referencia, "
                       "según la D. G. del Tesoro y Política Financiera. Los detalles están en las páginas de letras y de bonos y obligaciones.</p>",
                       _tabla(["Subasta", "Fecha", "Tipo marginal", "Cobertura"], filas)]
    if res["episodios"]:
        partes += ["<h2>Los episodios de referencia</h2>",
                   "<p>Máximo que marcó la prima de riesgo España-Alemania dentro de cada episodio, con su fecha. Las ventanas están fijadas de "
                   "antemano; el valor es el que da el dato.</p>",
                   _tabla(["Episodio", "Máximo (puntos básicos)", "Fecha", "Dato actual respecto a ese máximo"],
                          [[e["episodio"], _v(e["maximo"]), _f(e["fecha_maximo"]),
                            (f"{es_de['valor'] / e['maximo'] * 100:.0f} %") if e["maximo"] else "—"] for e in res["episodios"]])]
    svg = grafico_svg(res["grafico"])
    if svg:
        partes += ["<h2>Los últimos tres años</h2>", f'<figure class="wp-block-image">{svg}</figure>']
    partes += ['<h2 id="metodo">Cómo se hace</h2>',
               "<p>Los rendimientos son los tipos de interés a largo plazo del criterio de convergencia que publica Eurostat: el rendimiento "
               "del bono del Estado a diez años en el mercado secundario, bruto de impuestos, dato diario que el Banco Central Europeo recoge "
               "de los bancos centrales nacionales. El Especulador no modifica esas series; calcula sobre ellas los diferenciales en puntos "
               "básicos (solo en las fechas en que los dos países tienen dato), las variaciones a una, cuatro, trece y cincuenta y dos semanas, "
               "y dos percentiles: el de los últimos tres años, que mueve el semáforo (verde por debajo del percentil 50, ámbar entre el 50 y "
               "el 90, rojo desde el 90), y el histórico desde 2000, que da el contexto (tramos «bajo», «habitual», «por encima de lo habitual», "
               "«alto» y «muy alto» en los percentiles 25, 50, 75 y 90). El semáforo describe el presente frente al pasado reciente; no "
               "anticipa nada. El pulso del Tesoro reproduce los resultados de las últimas subastas tal como los publica el Tesoro.</p>",
               f'<p class="has-small-font-size">Fuente: Eurostat, <a href="{PORTAL}">conjunto irt_lt_mcby_d</a> (tipos de interés a largo plazo '
               f"del criterio de convergencia, recogidos por el BCE), reproducido sin modificar; pulso del Tesoro: D. G. del Tesoro y Política "
               f"Financiera, a través de las páginas de letras y bonos de El Especulador. Los diferenciales, percentiles, variaciones y episodios "
               f"son cálculos de El Especulador y se publican con licencia CC BY 4.0. Contenido informativo y educativo; no es asesoramiento "
               f"financiero ni recomendación de inversión.</p>",
               "<!-- prima:fin -->"]
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Prima de riesgo de España frente a Alemania, Italia y Francia, con semáforo histórico (El Especulador)",
        "description": "Rendimiento del bono a diez años de España, Alemania, Italia y Francia (Eurostat, criterio de convergencia) y sus "
                       "diferenciales en puntos básicos, con percentil de tres años, percentil histórico desde 2000, variaciones y máximos "
                       "de cada episodio de referencia, actualizado cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de Eurostat (irt_lt_mcby_d)", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": PORTAL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(df: pd.DataFrame, res: dict, meta: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    """Escribe los cuatro ficheros. Si la huella no cambia y no se fuerza, no toca nada."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(res)
    cambia = antes.get("huella") != nueva
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    niveles = {p: g.set_index("fecha")["valor"].sort_index() for p, g in df.groupby("pais")}
    difs = diferenciales(niveles)
    with (dd / "serie.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "serie", "unidad", "valor"])
        for p, s in niveles.items():
            for t, v in s.items():
                w.writerow([t.date().isoformat(), p.lower(), "porcentaje", f"{v:.4g}"])
        for n, s in difs.items():
            for t, v in s.items():
                w.writerow([t.date().isoformat(), n, "puntos_basicos", f"{v:.1f}"])
    previo.write_text(json.dumps({
        "version": VERSION, "fecha_publicacion": fecha_pub, "fecha_dato": res["fecha"], "desfase_dias": res["desfase_dias"],
        "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "eurostat_actualizado": meta.get("actualizado"),
        "semaforo": res["diferenciales"]["es_de"]["semaforo"], "prima_es_de": res["diferenciales"]["es_de"]["valor"],
        "niveles": res["niveles"], "diferenciales": res["diferenciales"], "ranking": res["ranking"],
        "episodios": res["episodios"], "tesoro": res["tesoro"],
        "fuente": "Eurostat, conjunto irt_lt_mcby_d (" + PORTAL + "); pulso del Tesoro: D. G. del Tesoro y Política Financiera",
        "condiciones": "Rendimientos de Eurostat reproducidos sin modificar, citando la fuente; diferenciales, percentiles, variaciones y "
                       "episodios son cálculos de El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- prima:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prima de riesgo de España: semáforo frente a Alemania, Italia y Francia | El Especulador</title>
<meta name="description" content="Prima de riesgo de España a diez años frente a Alemania, Italia y Francia, con semáforo de tres años, percentil histórico desde 2000, variaciones, máximos de 2012 y 2020 y el pulso de las subastas del Tesoro.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Prima de riesgo de España: semáforo frente a Alemania, Italia y Francia</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/serie.csv">rendimientos y diferenciales diarios</a> · <a href="datos/ultima.json">JSON</a>. Los rendimientos son de Eurostat y se reutilizan sin modificar, citando «Fuente: Eurostat»; los diferenciales, percentiles, variaciones y episodios son cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="respuesta JSON-stat de Eurostat ya descargada (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en UTC)")
    ap.add_argument("--tesoro", help="carpeta que contiene letras/ y bonos/ (por defecto, la carpeta madre de --salida)")
    ap.add_argument("--forzar", action="store_true", help="reescribir los ficheros aunque la huella no cambie (tras cambiar el código)")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).date()
    salida = Path(a.salida)
    texto = Path(a.local).read_text(encoding="utf-8") if a.local else descargar()
    df, meta = leer(texto)
    tesoro = leer_tesoro(Path(a.tesoro) if a.tesoro else salida.resolve().parent)
    res = calcular(df, hoy, tesoro)
    cambia = escribir(df, res, meta, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    d = res["diferenciales"]["es_de"]
    print(f"Prima España-Alemania {d['valor']} pb ({d['fecha']}), semáforo {d['semaforo']}, percentil 3 años {d['percentil_3a']}, "
          f"histórico {d['percentil_historico']}. Eurostat actualizado: {meta.get('actualizado')}. {len(df)} observaciones. "
          f"{'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
