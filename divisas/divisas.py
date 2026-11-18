"""Divisas de exposición del IBEX: cómo se mueven frente al euro las monedas de los mercados donde ganan dinero las cotizadas españolas.

Indicador 14 del catálogo de Datos de El Especulador. Toma los tipos de cambio de referencia del euro que
publica el BCE (conjunto EXR, diarios) para el real brasileño, el peso mexicano, la lira turca, el dólar y
la libra, y publica en <salida>/:

  fragmento-wp.html   lectura del día (cesta emergente y divisa por divisa), tabla con variaciones a una
                      semana, un mes, desde enero y doce meses, percentil de tres años, máximo y mínimo de
                      52 semanas, gráfico de doce meses y método, entre <!-- divisas:inicio HUELLA --> y
                      <!-- divisas:fin -->
  index.html          página propia de la salida
  datos/ultima.json   resumen versionado
  datos/serie.csv     los tipos de cambio diarios desde 2010 (formato largo)

Convención: el BCE publica unidades de divisa por un euro (EUR/BRL = 6,20 son 6,20 reales por euro). Aquí
se habla siempre de la divisa frente al euro: si el tipo sube, la divisa se deprecia (variación negativa).
La «cesta emergente» es la media geométrica, a partes iguales, del real, el peso mexicano y la lira; se
publica como variación en cada ventana, no como nivel, para que ninguna ventana larga la domine la lira.
Sin predicción ni recomendación: la página describe el movimiento, no lo que hará ni lo que hay que hacer.

Uso:
  python divisas/divisas.py --salida docs/divisas
  python divisas/divisas.py --salida docs/divisas --local exr.csv --fecha 2026-11-18
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

VERSION = "1.0.0"
API = "https://data-api.ecb.europa.eu/service/data/EXR/"
DIVISAS = {"BRL": "Real brasileño", "MXN": "Peso mexicano", "TRY": "Lira turca", "USD": "Dólar estadounidense", "GBP": "Libra esterlina"}
CESTA = ["BRL", "MXN", "TRY"]
CLAVE = "D." + "+".join(DIVISAS) + ".EUR.SP00.A"
PARAMS = {"format": "csvdata", "startPeriod": "2010-01-01"}
PORTAL = "https://data.ecb.europa.eu/data/datasets/EXR"
PAGINA_WP = "https://elespeculador.com/divisas-del-ibex/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/divisas/"
VENTANAS = [("1 semana", 7), ("1 mes", 30), ("12 meses", 365)]
DIAS_PERCENTIL = 3 * 365
AVISOS: list[str] = []


class DatosRaros(Exception):
    """El portal no responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga y lectura
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    esperas = [15, 30, 60, 120] if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(API + CLAVE, params=PARAMS, timeout=(20, 120),
                             headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "text/csv"})
            if r.status_code == 200 and "TIME_PERIOD" in r.text[:2000]:
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:60]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudieron descargar los tipos de cambio del portal del BCE tras {len(esperas) + 1} intentos: {ultimo}")


def leer(texto: str) -> pd.DataFrame:
    """CSV del portal (csvdata) -> DataFrame ancho: índice fecha, una columna por divisa (unidades por euro)."""
    df = pd.read_csv(io.StringIO(texto))
    for col in ("KEY", "TIME_PERIOD", "OBS_VALUE"):
        if col not in df.columns:
            raise DatosRaros(f"El CSV del portal no trae la columna {col}; columnas: {list(df.columns)[:12]}")

    def divisa(clave: str) -> str | None:
        partes = str(clave).split(".")
        return next((p for p in partes if p in DIVISAS), None)

    largo = pd.DataFrame({"fecha": pd.to_datetime(df["TIME_PERIOD"], errors="coerce"), "divisa": df["KEY"].map(divisa),
                          "valor": pd.to_numeric(df["OBS_VALUE"], errors="coerce")}).dropna()
    if largo.empty:
        raise DatosRaros("El CSV del portal no trae ninguna observación de las divisas pedidas")
    ancho = largo.pivot_table(index="fecha", columns="divisa", values="valor", aggfunc="last").sort_index()
    faltan = [d for d in DIVISAS if d not in ancho.columns]
    if faltan:
        raise DatosRaros(f"El portal no ha devuelto {', '.join(faltan)}")
    if (ancho <= 0).any().any():
        raise DatosRaros("Hay tipos de cambio no positivos en la respuesta del portal")
    return ancho[list(DIVISAS)]


# --------------------------------------------------------------------------- cálculo
def _anterior(s: pd.Series, fecha: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    antes = s[s.index <= fecha].dropna()
    if antes.empty:
        return None
    return antes.index[-1], float(antes.iloc[-1])


def variacion_divisa(s: pd.Series, fecha: pd.Timestamp, dias: int) -> float | None:
    """Variación de la divisa frente al euro (%) entre el último dato hasta `fecha - dias` y el dato en `fecha`.
    El tipo es unidades por euro: si sube, la divisa baja; por eso se invierte."""
    ant = _anterior(s, fecha - timedelta(days=dias))
    if ant is None or pd.isna(s.get(fecha)):
        return None
    return (ant[1] / float(s.loc[fecha]) - 1) * 100


def variacion_desde_enero(s: pd.Series, fecha: pd.Timestamp) -> float | None:
    fin_anterior = pd.Timestamp(year=fecha.year - 1, month=12, day=31)
    ant = _anterior(s, fin_anterior)
    if ant is None or pd.isna(s.get(fecha)):
        return None
    return (ant[1] / float(s.loc[fecha]) - 1) * 100


def percentil(serie: pd.Series, valor: float) -> float:
    """Porcentaje de observaciones menores o iguales que el valor (definición «débil»)."""
    s = serie.dropna()
    return float((s <= valor).mean() * 100) if len(s) else float("nan")


def cesta_variacion(df: pd.DataFrame, fecha: pd.Timestamp, dias: int | None) -> float | None:
    """Variación (%) de la cesta emergente: media geométrica, a partes iguales, de las variaciones de sus divisas."""
    prod = 1.0
    for d in CESTA:
        v = variacion_desde_enero(df[d], fecha) if dias is None else variacion_divisa(df[d], fecha, dias)
        if v is None:
            return None
        prod *= 1 + v / 100
    return (prod ** (1 / len(CESTA)) - 1) * 100


def calcular(df: pd.DataFrame, hoy: date) -> dict:
    fecha = df.index.max()
    if (hoy - fecha.date()).days > 10:
        raise DatosRaros(f"El último tipo de cambio es del {fecha.date()}: más de 10 días de desfase")
    if (hoy - fecha.date()).days > 5:
        AVISOS.append(f"El último tipo de cambio es del {fecha.date()} ({(hoy - fecha.date()).days} días)")
    divisas = {}
    for d, nombre in DIVISAS.items():
        s = df[d].dropna()
        tres = s[s.index > fecha - timedelta(days=DIAS_PERCENTIL)]
        anio = s[s.index > fecha - timedelta(days=365)]
        ult = float(s.loc[fecha]) if fecha in s.index else None
        if ult is None:
            AVISOS.append(f"{d}: sin dato el {fecha.date()}; se usa el anterior")
            f2, ult = _anterior(s, fecha)
        else:
            f2 = fecha
        divisas[d] = {"nombre": nombre, "tipo": round(ult, 4), "fecha": f2.date().isoformat(), "en_cesta": d in CESTA,
                      "variaciones": {n: (round(variacion_divisa(s, f2, dias), 2) if variacion_divisa(s, f2, dias) is not None else None) for n, dias in VENTANAS},
                      "desde_enero": (round(variacion_desde_enero(s, f2), 2) if variacion_desde_enero(s, f2) is not None else None),
                      "percentil_euro_3a": round(percentil(tres, ult), 1), "sesiones_3a": int(len(tres)),
                      "max_52s": round(float(anio.max()), 4), "fecha_max_52s": anio.idxmax().date().isoformat(),
                      "min_52s": round(float(anio.min()), 4), "fecha_min_52s": anio.idxmin().date().isoformat()}
    cesta = {"divisas": CESTA, "variaciones": {n: (round(cesta_variacion(df, fecha, dias), 2) if cesta_variacion(df, fecha, dias) is not None else None) for n, dias in VENTANAS},
             "desde_enero": (round(cesta_variacion(df, fecha, None), 2) if cesta_variacion(df, fecha, None) is not None else None)}
    mayor = max(DIVISAS, key=lambda d: abs(divisas[d]["variaciones"]["12 meses"] or 0))
    return {"fecha": fecha.date().isoformat(), "divisas": divisas, "cesta": cesta, "mayor_movimiento_12m": mayor,
            "primera_fecha": df.index.min().date().isoformat(), "observaciones": int(df.notna().sum().sum())}


def huella(res: dict) -> str:
    base = {"version": VERSION, "fecha": res["fecha"], "tipos": {d: v["tipo"] for d, v in res["divisas"].items()}}
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _pct(x: float | None, dec: int = 1) -> str:
    if x is None:
        return "—"
    s = f"{x:+.{dec}f}".replace(".", ",").replace("-", "−")
    return s + " %"


def _n(x: float | None, dec: int = 4) -> str:
    return "—" if x is None else f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def _zona(p: float) -> str:
    if p >= 90:
        return "zona más débil de tres años"
    if p >= 75:
        return "débil frente a los últimos tres años"
    if p <= 10:
        return "zona más fuerte de tres años"
    if p <= 25:
        return "fuerte frente a los últimos tres años"
    return "en su rango de tres años"


def grafico_svg(df: pd.DataFrame, fecha: pd.Timestamp) -> str:
    """Valor de cada divisa en euros, doce meses, con base 100 en el primer día: baja = se deprecia."""
    W, H, ml, mr, mt, mb = 720, 280, 40, 12, 10, 28
    ventana = df[(df.index > fecha - timedelta(days=365)) & (df.index <= fecha)].dropna(how="all")
    if ventana.empty:
        return ""
    base = ventana.iloc[0]
    reb = 100 * base / ventana      # unidades por euro inversas: valor de la divisa
    y0, y1 = float(reb.min().min()) * 0.98, float(reb.max().max()) * 1.02
    x0, x1 = ventana.index.min(), ventana.index.max()
    def X(t): return ml + (t - x0) / max((x1 - x0), pd.Timedelta(days=1)) * (W - ml - mr)
    def Y(v): return mt + (1 - (v - y0) / max(y1 - y0, 1e-9)) * (H - mt - mb)
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Valor en euros de cada divisa, doce meses, base 100" xmlns="http://www.w3.org/2000/svg">',
              '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
    for i in range(5):
        v = y0 + (y1 - y0) * i / 4
        partes.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                      f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    if y0 < 100 < y1:
        partes.append(f'<line x1="{ml}" y1="{Y(100):.1f}" x2="{W - mr}" y2="{Y(100):.1f}" stroke="#9aa5b1" stroke-dasharray="4 3"/>')
    for m in pd.date_range(x0, x1, freq="MS"):
        partes.append(f'<text class="eje" x="{X(m):.1f}" y="{H - 8}" text-anchor="middle">{m.strftime("%m/%y")}</text>')
    colores = {"BRL": "#1f4e8c", "MXN": "#2a9d8f", "TRY": "#c0392b", "USD": "#555555", "GBP": "#e0a44c"}
    for d in DIVISAS:
        s = reb[d].dropna()
        puntos = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        partes.append(f'<polyline class="lin" stroke="{colores[d]}" points="{puntos}"/>')
    x = ml + 6
    for d in DIVISAS:
        partes.append(f'<text class="eje" x="{x}" y="{mt + 14}" fill="{colores[d]}">{d}</text>')
        x += 42
    partes.append("</svg>")
    return "".join(partes)


def fragmento(res: dict, df: pd.DataFrame, fecha_pub: str) -> str:
    c = res["cesta"]
    dv = res["divisas"]
    mayor = res["mayor_movimiento_12m"]
    frase = (f"La cesta emergente del IBEX (real brasileño, peso mexicano y lira turca, a partes iguales) se ha movido <strong>{_pct(c['variaciones']['12 meses'])}</strong> "
             f"frente al euro en doce meses, {_pct(c['variaciones']['1 mes'])} en el último mes y {_pct(c['desde_enero'])} desde enero. "
             f"La divisa que más se ha movido en doce meses es {dv[mayor]['nombre'].lower()}: {_pct(dv[mayor]['variaciones']['12 meses'])}. "
             f"Dólar {_pct(dv['USD']['variaciones']['12 meses'])} y libra {_pct(dv['GBP']['variaciones']['12 meses'])} en doce meses.")
    filas = []
    for d, v in dv.items():
        filas.append([f"<strong>{v['nombre']}</strong> ({d})" + (" · cesta" if v["en_cesta"] else ""), _n(v["tipo"], 4 if v["tipo"] < 100 else 2), _pct(v["variaciones"]["1 semana"]),
                      _pct(v["variaciones"]["1 mes"]), _pct(v["desde_enero"]), _pct(v["variaciones"]["12 meses"]),
                      f"{v['percentil_euro_3a']:.0f} ({_zona(v['percentil_euro_3a'])})", f"{_n(v['max_52s'], 4 if v['max_52s'] < 100 else 2)} · {_n(v['min_52s'], 4 if v['min_52s'] < 100 else 2)}"])
    partes = [f"<!-- divisas:inicio {res['huella']} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con los tipos de referencia del BCE del {_f(res["fecha"])}. Tipos en unidades de divisa por euro; '
              "las variaciones son de la divisa frente al euro (negativa = la divisa se ha depreciado).</p>",
              "<p>" + frase + "</p>",
              "<h2>Divisa por divisa</h2>",
              _tabla(["Divisa", "Por euro", "1 semana", "1 mes", "Desde enero", "12 meses", "Euro en percentil de 3 años", "Máx. · mín. del euro en 52 semanas"], filas),
              '<p class="has-small-font-size">«Euro en percentil de 3 años»: porcentaje de sesiones de los últimos tres años en que el euro ha estado igual o más bajo frente a esa divisa; '
              "90 quiere decir que el euro solo ha estado más alto el 10 % de las sesiones, es decir, la divisa está en su zona más débil de tres años.</p>",
              "<h2>Los últimos doce meses</h2>",
              '<figure class="wp-block-image">' + grafico_svg(df, pd.Timestamp(res["fecha"])) + "</figure>",
              '<p class="has-small-font-size">Valor en euros de cada divisa con base 100 en el primer día de la ventana: una línea que baja es una divisa que se deprecia frente al euro.</p>',
              '<h2 id="metodo">Qué mide y cómo se hace</h2>'
              "<p>Una parte importante de los beneficios de las grandes cotizadas españolas se genera en Brasil, México, Turquía, Estados Unidos y el Reino Unido, "
              "y se convierte a euros al tipo de cambio: históricamente, cuando una de esas divisas se deprecia, los resultados en euros del negocio en ese país "
              "valen menos, y al revés. Esta página sigue las cinco divisas con los tipos de cambio de referencia del Banco Central Europeo (fijados cada día hábil "
              "hacia las 16:00, hora central europea), sin modificarlos. Las variaciones comparan el dato del día con el último disponible una semana, un mes o doce "
              "meses antes, y con el cierre del año anterior. La cesta emergente es la media geométrica, a partes iguales, de las variaciones del real, el peso mexicano y "
              "la lira en cada ventana: se publica como variación y no como nivel para que la lira, que acumula una depreciación mucho mayor, no domine una serie larga. "
              "El percentil de tres años y el máximo y el mínimo de 52 semanas se calculan sobre el tipo de cambio. Lectura histórica, sin predicción: describe dónde "
              "están las divisas, no hacia dónde van ni qué hacer con una acción.</p>"
              f'<p class="has-small-font-size">Fuente: BCE, <a href="{PORTAL}">tipos de cambio de referencia del euro (conjunto EXR)</a>, desde {_f(res["primera_fecha"])}. '
              "Reutilización según la política del SEBC, citando la fuente y sin modificar las series; la cesta, las variaciones y los percentiles son cálculo de El Especulador "
              "(CC BY 4.0). Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>",
              "<!-- divisas:fin -->"]
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Divisas de exposición del IBEX: real, peso mexicano, lira, dólar y libra frente al euro (El Especulador)",
        "description": "Tipos de cambio de referencia del BCE de las cinco divisas con más peso en los resultados de las cotizadas españolas, con variaciones, "
                       "percentil de tres años, máximos y mínimos de 52 semanas y una cesta emergente a partes iguales, actualizado cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de los tipos de cambio de referencia del BCE", "license": "https://creativecommons.org/licenses/by/4.0/",
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
    largo = df.stack().reset_index()
    largo.columns = ["fecha", "divisa", "unidades_por_euro"]
    largo["fecha"] = largo["fecha"].dt.date
    largo.sort_values(["divisa", "fecha"]).to_csv(dd / "serie.csv", index=False)
    previo.write_text(json.dumps({**res, "version": VERSION, "fecha_publicacion": fecha_pub,
                                  "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "fuente": "BCE, tipos de cambio de referencia del euro (EXR), reproducidos sin modificar",
                                  "condiciones": "Política de reutilización del SEBC: citar la fuente, no modificar las series. Cesta, variaciones y percentiles de "
                                                 "El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero."},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, df, fecha_pub)
    marca = "\n<!-- divisas:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Divisas de exposición del IBEX: real, peso, lira, dólar y libra frente al euro | El Especulador</title>
<meta name="description" content="Cómo se mueven frente al euro las divisas donde ganan dinero las cotizadas españolas: real brasileño, peso mexicano, lira turca, dólar y libra, con los tipos de referencia del BCE.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:980px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} table{{border-collapse:collapse;width:100%;font-size:.92rem}} th,td{{border-bottom:1px solid #e3e8ef;padding:4px 6px;text-align:left}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Divisas de exposición del IBEX</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/serie.csv">tipos de cambio diarios desde 2010</a> · <a href="datos/ultima.json">JSON</a>. Fuente: BCE (EXR); cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="CSV del portal ya descargado (pruebas)")
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
    c = res["cesta"]["variaciones"]
    print(f"Tipos del {res['fecha']}: " + ", ".join(f"{d} {v['tipo']}" for d, v in res["divisas"].items())
          + f". Cesta emergente: {c['1 mes']:+.2f} % en 1 mes, {c['12 meses']:+.2f} % en 12 meses. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
