"""Estrés financiero de España: el CISS del BCE, día a día.

Indicador 2 del catálogo de Datos de El Especulador. Lee del portal de datos del
BCE el indicador compuesto de estrés sistémico (CISS) de España, de la zona euro,
de Alemania, Francia e Italia, y el CISS soberano de España, Alemania, Francia e
Italia, y publica:

  docs/estres/fragmento-wp.html   tablas y gráfico entre <!-- estres:inicio HUELLA --> y <!-- estres:fin -->
  docs/estres/index.html          página propia en GitHub Pages
  docs/estres/datos/serie.csv     todas las series, formato largo (fecha, serie, valor)
  docs/estres/datos/ultima.json   resumen versionado para webs y widgets

Fuente: BCE, portal de datos, conjunto CISS. Condiciones del SEBC: reutilización
gratuita citando la fuente y sin modificar las estadísticas; los cálculos propios
(percentiles, variaciones, episodios) se declaran como tales. Elaboración propia
de El Especulador con licencia CC BY 4.0.

Uso:
  python estres/estres.py --salida docs/estres              descarga y publica
  python estres/estres.py --salida docs/estres --local F.csv usa un CSV del portal ya descargado
  python estres/estres.py --salida docs/estres --fecha 2026-11-02   fija el día (pruebas)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

VERSION = "1.0.0"
API = "https://data-api.ecb.europa.eu/service/data/CISS/"
# Claves del conjunto CISS: frecuencia diaria, zona, indicador (SS_CIN: CISS nuevo;
# SOV_CIN: CISS soberano). El portal solo devuelve las combinaciones que existen.
CLAVE = "D.ES+U2+DE+FR+IT.Z0Z.4F.EC.SS_CIN+SOV_CIN.IDX"
PARAMS = {"format": "csvdata", "startPeriod": "1980-01-01"}
PORTAL = "https://data.ecb.europa.eu/data/datasets/CISS"
PAGINA_WP = "https://elespeculador.com/estres-financiero-espana/"
PAGES = "https://elespeculador-datos.github.io/ifg/estres/"
METODOLOGIA = PAGINA_WP + "#metodo"

ZONAS = {"ES": "España", "U2": "Zona euro", "DE": "Alemania", "FR": "Francia", "IT": "Italia"}
SERIES = {  # nombre interno -> (zona, indicador)
    "es": ("ES", "SS_CIN"), "ea": ("U2", "SS_CIN"), "de": ("DE", "SS_CIN"), "fr": ("FR", "SS_CIN"), "it": ("IT", "SS_CIN"),
    "es_sob": ("ES", "SOV_CIN"), "de_sob": ("DE", "SOV_CIN"), "fr_sob": ("FR", "SOV_CIN"), "it_sob": ("IT", "SOV_CIN"),
}
# Episodios de referencia: ventanas fijadas de antemano; el valor que se publica es el
# máximo que el propio indicador marcó dentro de cada ventana (dato, no decisión).
EPISODIOS = [
    ("Crisis del Sistema Monetario Europeo", "1992-08-01", "1993-08-31"),
    ("Quiebra de Lehman Brothers", "2008-09-01", "2009-03-31"),
    ("Crisis del euro", "2010-04-01", "2012-12-31"),
    ("Pandemia", "2020-02-15", "2020-06-30"),
    ("Invasión de Ucrania y crisis energética", "2022-02-24", "2022-12-31"),
]
TRAMOS = [(90, "muy alto"), (75, "alto"), (50, "por encima de lo habitual"), (25, "habitual"), (0, "bajo")]
AVISOS: list[str] = []


class DatosRaros(Exception):
    """El portal no responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    """Devuelve el CSV del portal de datos del BCE. Reintenta con esperas crecientes."""
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
    raise DatosRaros(f"No se pudo descargar el CISS del portal del BCE tras {len(esperas) + 1} intentos: {ultimo}")


# --------------------------------------------------------------------------- lectura
def leer(texto: str) -> pd.DataFrame:
    """CSV del portal (formato csvdata) -> DataFrame largo con fecha, serie y valor."""
    df = pd.read_csv(io.StringIO(texto))
    for col in ("KEY", "TIME_PERIOD", "OBS_VALUE"):
        if col not in df.columns:
            raise DatosRaros(f"El CSV del portal no trae la columna {col}; columnas: {list(df.columns)[:12]}")
    # La clave viene como «CISS.D.ES.Z0Z.4F.EC.SS_CIN.IDX» (con el conjunto delante) o sin
    # él; se localizan la zona y el indicador por su valor, no por su posición.
    inverso = {v: k for k, v in SERIES.items()}

    def nombre(clave: str) -> str | None:
        partes = str(clave).split(".")
        zona = next((p for p in partes if p in ZONAS), None)
        indicador = next((p for p in partes if p in ("SS_CIN", "SOV_CIN")), None)
        return inverso.get((zona, indicador))

    if df["KEY"].astype(str).str.count(r"\.").min() < 6:
        raise DatosRaros(f"Claves con forma inesperada: {df['KEY'].head(3).tolist()}")
    df = pd.DataFrame({
        "fecha": pd.to_datetime(df["TIME_PERIOD"], errors="coerce"),
        "serie": df["KEY"].map(nombre),
        "valor": pd.to_numeric(df["OBS_VALUE"], errors="coerce"),
    })
    df = df.dropna(subset=["fecha", "serie", "valor"]).sort_values(["serie", "fecha"]).reset_index(drop=True)
    if "es" not in set(df["serie"]):
        raise DatosRaros("El portal no ha devuelto el CISS de España")
    n_es = (df["serie"] == "es").sum()
    if n_es < 5000:
        raise DatosRaros(f"El CISS de España trae {n_es} observaciones: demasiado pocas para la serie desde 1980")
    if ((df["valor"] < 0) | (df["valor"] > 1)).any():
        raise DatosRaros("Hay valores fuera del rango 0-1 del CISS: el fichero ha cambiado de criterio")
    return df


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
                       "maximo": round(float(trozo.max()), 3), "fecha_maximo": trozo.idxmax().date().isoformat()})
    return salida


def calcular(df: pd.DataFrame, hoy: date) -> dict:
    series = {n: g.set_index("fecha")["valor"].sort_index() for n, g in df.groupby("serie")}
    res = {"series": {}}
    for n, s in series.items():
        s = s[~s.index.duplicated(keep="last")]
        f = s.index[-1]
        v = float(s.iloc[-1])
        p = percentil(s, v)
        res["series"][n] = {
            "zona": ZONAS[SERIES[n][0]], "indicador": "CISS" if SERIES[n][1] == "SS_CIN" else "CISS soberano",
            "fecha": f.date().isoformat(), "valor": round(v, 3), "percentil": round(p, 1), "tramo": tramo(p),
            "desde": s.index[0].date().isoformat(), "observaciones": int(len(s)),
            "variacion_1s": _r(variacion(s, f, 7)), "variacion_4s": _r(variacion(s, f, 28)), "variacion_13s": _r(variacion(s, f, 91)),
            "maximo": round(float(s.max()), 3), "fecha_maximo": s.idxmax().date().isoformat(),
            "ultima_vez_igual_o_mayor": ultima_vez_igual_o_mayor(s, f, v),
        }
    es = res["series"]["es"]
    res["episodios"] = episodios(series["es"])
    res["fecha"] = es["fecha"]
    res["desfase_dias"] = (hoy - date.fromisoformat(es["fecha"])).days
    if res["desfase_dias"] > 10:
        AVISOS.append(f"El último dato del CISS de España es del {es['fecha']}: {res['desfase_dias']} días de desfase")
    if res["desfase_dias"] > 45:
        raise DatosRaros(f"El CISS de España lleva {res['desfase_dias']} días sin dato nuevo: comprobar el portal del BCE")
    res["grafico"] = {n: series[n][series[n].index >= pd.Timestamp(hoy) - pd.Timedelta(days=3 * 365)] for n in ("es", "ea") if n in series}
    return res


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def huella(res: dict) -> str:
    base = {n: [v["fecha"], v["valor"]] for n, v in res["series"].items()}
    base["version"] = VERSION
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return "—" if not iso else pd.Timestamp(iso).strftime("%d/%m/%Y")


def _v(x: float | None, dec: int = 3) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:.{dec}f}".replace(".", ",")


def _dif(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    return ("+" if x > 0 else "") + f"{x:.3f}".replace(".", ",")


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_svg(series: dict[str, pd.Series]) -> str:
    """Línea del CISS de España y de la zona euro, últimos tres años, en SVG sin dependencias."""
    W, H, ml, mr, mt, mb = 720, 260, 40, 12, 10, 28
    todas = pd.concat(series.values())
    if todas.empty:
        return ""
    x0, x1 = todas.index.min(), todas.index.max()
    y1 = max(0.1, float(todas.max()) * 1.1)
    def X(t): return ml + (t - x0) / max((x1 - x0), pd.Timedelta(days=1)) * (W - ml - mr)
    def Y(v): return mt + (1 - v / y1) * (H - mt - mb)
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Estrés financiero: España y zona euro, últimos tres años" xmlns="http://www.w3.org/2000/svg">',
              '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
    for i in range(5):
        v = y1 * i / 4
        partes.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                      f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.2f}</text>'.replace(".", ","))
    for a in range(x0.year, x1.year + 1):
        t = pd.Timestamp(year=a, month=1, day=1)
        if x0 <= t <= x1:
            partes.append(f'<text class="eje" x="{X(t):.1f}" y="{H - 8}" text-anchor="middle">{a}</text>')
    colores = {"es": "#1f4e8c", "ea": "#e0a44c"}
    for n, s in series.items():
        puntos = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        partes.append(f'<polyline class="lin" stroke="{colores.get(n, "#888")}" points="{puntos}"/>')
    partes.append(f'<text class="eje" x="{ml + 6}" y="{mt + 14}" fill="#1f4e8c">España</text>'
                  f'<text class="eje" x="{ml + 66}" y="{mt + 14}" fill="#e0a44c">Zona euro</text></svg>')
    return "".join(partes)


def fragmento(res: dict, fecha_pub: str) -> str:
    es = res["series"]["es"]
    partes = [f"<!-- estres:inicio {huella(res)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con el dato del BCE del {_f(es["fecha"])}.</p>']
    frase = (f"<p>El indicador de estrés financiero de España (CISS del BCE) marcó <strong>{_v(es['valor'])}</strong> el {_f(es['fecha'])}, "
             f"en una escala de 0 a 1. Es el percentil {_v(es['percentil'], 0)} de su historia desde {es['desde'][:4]}: ha estado igual o más bajo "
             f"el {_v(es['percentil'], 0)} % de las sesiones: un nivel {es['tramo']} en términos históricos.")
    if es["ultima_vez_igual_o_mayor"]:
        frase += f" La última vez que estuvo igual o más alto, sin contar los últimos seis meses, fue el {_f(es['ultima_vez_igual_o_mayor'])}."
    frase += (f" Su máximo histórico es {_v(es['maximo'])}, el {_f(es['fecha_maximo'])}. En las últimas cuatro semanas ha variado "
              f"{_dif(es['variacion_4s'])} puntos; en trece, {_dif(es['variacion_13s'])}.</p>")
    partes.append(frase)
    orden = ["es", "ea", "de", "fr", "it"]
    partes += ["<h2>España frente a la zona euro y las grandes economías</h2>",
               _tabla(["Zona", "CISS", "Percentil histórico", "Desde", "1 semana", "4 semanas", "13 semanas", "Dato del"],
                      [[v["zona"], _v(v["valor"]), _v(v["percentil"], 0), v["desde"][:4], _dif(v["variacion_1s"]),
                        _dif(v["variacion_4s"]), _dif(v["variacion_13s"]), _f(v["fecha"])]
                       for n in orden if (v := res["series"].get(n))])]
    sob = [n for n in ("es_sob", "it_sob", "fr_sob", "de_sob") if n in res["series"]]
    if sob:
        partes += ["<h2>Estrés soberano: la deuda pública</h2>",
                   "<p>El CISS soberano mide la tensión en el mercado de deuda pública de cada país (rendimientos, volatilidad, liquidez). "
                   "Es el componente que más se mira en España desde 2010.</p>",
                   _tabla(["Zona", "CISS soberano", "Percentil histórico", "Desde", "4 semanas", "Máximo", "Fecha del máximo", "Dato del"],
                          [[v["zona"], _v(v["valor"]), _v(v["percentil"], 0), v["desde"][:4], _dif(v["variacion_4s"]),
                            _v(v["maximo"]), _f(v["fecha_maximo"]), _f(v["fecha"])] for n in sob if (v := res["series"][n])])]
    if res["episodios"]:
        partes += ["<h2>Los episodios de referencia</h2>",
                   "<p>Máximo que marcó el CISS de España dentro de cada episodio, con su fecha. Las ventanas están fijadas de antemano; "
                   "el valor es el que da el dato.</p>",
                   _tabla(["Episodio", "Máximo del CISS", "Fecha", "Dato actual como parte de ese máximo"],
                          [[e["episodio"], _v(e["maximo"]), _f(e["fecha_maximo"]),
                            f"{es['valor'] / e['maximo'] * 100:.0f} %" if e["maximo"] else "—"] for e in res["episodios"]])]
    svg = grafico_svg(res["grafico"])
    if svg:
        partes += ["<h2>Los últimos tres años</h2>", f'<figure class="wp-block-image">{svg}</figure>']
    partes += ['<h2 id="metodo">Cómo se hace</h2>',
               "<p>El CISS (indicador compuesto de estrés sistémico) lo calcula y publica el Banco Central Europeo. Resume en una cifra "
               "de 0 a 1 la tensión en cinco segmentos del sistema financiero (mercado monetario, deuda, bolsa, intermediarios financieros "
               "y divisas) y da más peso a la tensión cuando aparece en varios segmentos a la vez. El Especulador no modifica las series: "
               "toma los valores diarios del portal de datos del BCE y calcula sobre ellos el percentil histórico (porcentaje de sesiones "
               "con un valor igual o inferior al actual, sobre toda la serie disponible), las variaciones a una, cuatro y trece semanas "
               "(diferencia en puntos del índice) y el máximo dentro de cada episodio de referencia. Los tramos («bajo», «habitual», "
               "«por encima de lo habitual», «alto», «muy alto») corresponden a los percentiles 25, 50, 75 y 90 de cada serie. "
               "Lectura histórica, sin predicción: un percentil alto describe el presente frente al pasado, no lo que viene.</p>",
               f'<p class="has-small-font-size">Fuente: BCE, <a href="{PORTAL}">portal de datos, conjunto CISS</a>. Elaboración propia de El Especulador; '
               f"los cálculos (percentiles, variaciones, episodios) son de El Especulador y se publican con licencia CC BY 4.0. "
               f"Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>",
               "<!-- estres:fin -->"]
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Estrés financiero de España: CISS del BCE con percentil histórico y episodios (El Especulador)",
        "description": "Indicador compuesto de estrés sistémico (CISS) del BCE para España, la zona euro, Alemania, Francia e Italia, y "
                       "CISS soberano, con percentil histórico, variaciones y máximos de cada episodio de referencia, actualizado cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos del BCE (CISS)", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": PORTAL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(df: pd.DataFrame, res: dict, hoy: date, salida: Path) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(res)
    cambia = antes.get("huella") != nueva
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    with (dd / "serie.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "serie", "zona", "indicador", "valor"])
        for r in df.itertuples(index=False):
            w.writerow([r.fecha.date().isoformat(), r.serie, SERIES[r.serie][0], SERIES[r.serie][1], f"{r.valor:.6g}"])
    previo.write_text(json.dumps({
        "version": VERSION, "fecha_publicacion": fecha_pub, "fecha_dato": res["fecha"], "desfase_dias": res["desfase_dias"],
        "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "series": res["series"], "episodios": res["episodios"],
        "fuente": "BCE, portal de datos, conjunto CISS (" + PORTAL + ")",
        "condiciones": "Estadísticas del SEBC reutilizadas sin modificar, citando la fuente; percentiles, variaciones y episodios son "
                       "cálculos de El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, fecha_pub)
    marca = "\n<!-- estres:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estrés financiero de España: el CISS del BCE, día a día | El Especulador</title>
<meta name="description" content="Indicador de estrés financiero de España (CISS del BCE) con su percentil histórico, la comparación con la zona euro, Alemania, Francia e Italia, el estrés soberano y los máximos de 2008, 2012 y 2020.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Estrés financiero de España: el CISS del BCE, día a día</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/serie.csv">todas las series diarias</a> · <a href="datos/ultima.json">JSON</a>. Las series son del BCE y se reutilizan sin modificar, citando «Fuente: BCE (CISS)»; los percentiles, variaciones y episodios son cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="CSV del portal del BCE ya descargado (pruebas)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en UTC)")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).date()
    texto = Path(a.local).read_text(encoding="utf-8") if a.local else descargar()
    df = leer(texto)
    res = calcular(df, hoy)
    cambia = escribir(df, res, hoy, Path(a.salida))
    for av in AVISOS:
        print(f"::warning::{av}")
    es = res["series"]["es"]
    print(f"CISS España {es['valor']} ({es['fecha']}), percentil {es['percentil']}, {es['tramo']}. "
          f"{len(res['series'])} series, {len(df)} observaciones. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
