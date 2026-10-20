"""OPAs en la bolsa española de El Especulador.

Cada día hábil descarga de la API pública de BME el registro de ofertas públicas
de adquisición (OPA) sobre sociedades cotizadas y, solo si ha cambiado algo, publica:

  docs/opas/datos/opas.csv          todas las OPAs del registro (desde 2000)
  docs/opas/datos/por_anio.csv      número de OPAs por año y por resultado
  docs/opas/datos/ultima.json       resumen
  docs/opas/fragmento-wp.html       tablas en HTML para la página de elespeculador.com
  docs/opas/index.html              página propia del dato

Uso:
  python opas/opas.py                    descarga y publica si hay novedades
  python opas/opas.py --local F.json     usa una respuesta ya descargada (pruebas)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/TakeoverBids"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/",
             "Accept": "application/json, text/plain, */*"}
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "opas"
DATOS = SALIDA / "datos"
PILAR = "https://elespeculador.com/opa-que-pasa-con-mis-acciones/"
PAGINA_WP = "https://elespeculador.com/opas-bolsa-espanola/"
PAGES = "https://elespeculador-datos.github.io/ifg/opas/"
DESDE_TABLA = 2015          # la tabla detallada de la página empieza aquí; el CSV lo tiene todo
MINIMO_FILAS = 200          # el 20/10/2026 el registro tenía 220 OPAs desde 2000
RESULTADOS = {"P": "Positivo", "N": "Negativo"}
# BME corta los nombres de los oferentes a 35 caracteres; estos se completan a mano
OFERENTES = {
    "BANCO BILBAO VIZCAYA ARGENTARIA, S.": "BANCO BILBAO VIZCAYA ARGENTARIA, S.A.",
    "FOMENTO DE CONSTRUCCIONES Y CONTRAT": "FOMENTO DE CONSTRUCCIONES Y CONTRATAS, S.A.",
    "PROMOTORA BRAVO DESIGNATED ACTIVIT": "PROMOTORA BRAVO DESIGNATED ACTIVITY COMPANY",
}
COLUMNAS = ["inicio_aceptacion", "fin_aceptacion", "sociedad", "oferente", "precio_eur", "contraprestacion_texto",
            "acciones_a_las_que_se_dirige", "acciones_adquiridas", "aceptacion_pct", "resultado", "fecha_resultado",
            "fecha_retirada", "nota_bme", "codigo_bme"]


class DatosRaros(Exception):
    """La respuesta no tiene la forma esperada: mejor parar que publicar basura."""


def hoy_madrid() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(ZoneInfo("Europe/Madrid")).date())


# --------------------------------------------------------------------------- descarga y limpieza
def descargar() -> list[dict]:
    h = hoy_madrid()
    r = requests.get(API, params={"from": "20000101", "to": f"{h.year + 1}1231", "page": 0, "pageSize": 0},
                     headers=CABECERAS, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j.get("hasMoreResults"):
        raise DatosRaros("BME indica que hay más resultados de los devueltos")
    return j.get("data", [])


def _fecha(x: str) -> pd.Timestamp | None:
    x = (x or "").strip()
    return pd.to_datetime(x, format="%Y%m%d", errors="coerce") if x else None


def _alnum(x: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (x or "").upper())


def _oferente(oferente: str | None, sociedad: str | None) -> str:
    o = (oferente or "").strip()
    if not o:
        return ""
    if _alnum(o)[:9] == _alnum(sociedad)[:9]:
        return "La propia sociedad"
    o = OFERENTES.get(o, o)
    if o.upper() in ("OPA DE EXCLUSIÓN", "OPA DE EXCLUSION"):
        return ""
    o = re.sub(r"^OPA DE\s+", "", o)
    return re.sub(r"(,\s*S\.?|,\s*S\.A\. DE CAPITAL|\s+DE CAPITAL)$", "", o).strip()


def preparar(filas: list[dict]) -> pd.DataFrame:
    if len(filas) < MINIMO_FILAS:
        raise DatosRaros(f"Solo {len(filas)} OPAs en la respuesta de BME (se esperaban al menos {MINIMO_FILAS})")
    faltan = {"companyName", "offeringCompanyName", "price", "startingDate", "shares", "acquiredShares", "result"} - set(filas[0])
    if faltan:
        raise DatosRaros(f"Faltan campos en la respuesta de BME: {faltan}")
    h = hoy_madrid()
    out = []
    for x in filas:
        inicio, fin = _fecha(x.get("startingDate")), _fecha(x.get("finishDate"))
        retirada, res = _fecha(x.get("cancellationDate")), _fecha(x.get("acquiredDate"))
        dirigidas, adquiridas = int(x.get("shares") or 0), int(x.get("acquiredShares") or 0)
        codigo = (x.get("result") or "").strip()
        if codigo in RESULTADOS:
            resultado = RESULTADOS[codigo]
        elif retirada is not None and not pd.isna(retirada):
            resultado = "Retirada"
        elif fin is not None and not pd.isna(fin) and fin >= h:
            resultado = "En plazo"
        else:
            resultado = "Sin dato"
        out.append({
            "inicio_aceptacion": inicio, "fin_aceptacion": fin,
            "sociedad": (x.get("companyName") or "").strip(), "oferente": _oferente(x.get("offeringCompanyName"), x.get("companyName")),
            "precio_eur": float(x.get("price") or 0) or None, "contraprestacion_texto": (x.get("priceText") or "").strip(),
            "acciones_a_las_que_se_dirige": dirigidas or None, "acciones_adquiridas": adquiridas if codigo in RESULTADOS else None,
            # en una OPA negativa BME anota 0 acciones adquiridas: no es la aceptación, así que no se calcula
            "aceptacion_pct": round(100 * adquiridas / dirigidas, 2) if dirigidas and codigo == "P" else None,
            "resultado": resultado, "fecha_resultado": res, "fecha_retirada": retirada,
            "nota_bme": (x.get("cancellationText") or "").strip(), "codigo_bme": (x.get("companyKey") or "").strip(),
        })
    d = pd.DataFrame(out, columns=COLUMNAS)
    if d["inicio_aceptacion"].isna().mean() > 0.05:
        raise DatosRaros("Demasiadas fechas de inicio ilegibles")
    d = d.drop_duplicates().sort_values(["inicio_aceptacion", "sociedad"], ascending=[False, True]).reset_index(drop=True)
    return d


def por_anio(d: pd.DataFrame) -> pd.DataFrame:
    t = d.assign(anio=d["inicio_aceptacion"].dt.year).pivot_table(index="anio", columns="resultado", values="sociedad",
                                                                   aggfunc="count", fill_value=0)
    for c in ["Positivo", "Negativo", "Retirada", "En plazo", "Sin dato"]:
        if c not in t.columns:
            t[c] = 0
    t = t[["Positivo", "Negativo", "Retirada", "En plazo", "Sin dato"]]
    t.columns = ["positivas", "negativas", "retiradas", "en_plazo", "sin_dato"]
    t.insert(0, "total", t.sum(axis=1))
    return t.reset_index().sort_values("anio", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- formato
def _f(x) -> str:
    return "—" if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


def _num(x: float | int | None, dec: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    s = f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _precio(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    entero, _, dec = f"{x:.4f}".partition(".")
    dec = dec.rstrip("0").ljust(2, "0")
    return f"{int(entero):,}".replace(",", ".") + "," + dec + " €"


def _contraprestacion(r) -> str:
    partes = []
    if r.precio_eur and not pd.isna(r.precio_eur):
        partes.append(_precio(r.precio_eur))
    if r.contraprestacion_texto:
        partes.append(f"«{r.contraprestacion_texto}»")
    return " · ".join(partes) or "—"


def _aceptacion(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    if x > 100:
        return f"{_num(x, 2)} % (oferta parcial sobresuscrita: hubo prorrateo)"
    return f"{_num(x, 2)} %"


def frase(d: pd.DataFrame, t: pd.DataFrame) -> str:
    total, desde = len(d), int(d["inicio_aceptacion"].dt.year.min())
    ultima = d.iloc[0]
    recientes = d[d["inicio_aceptacion"].dt.year >= hoy_madrid().year - 4]
    texto = (f"El registro de BME recoge {total} OPAs sobre sociedades cotizadas en sus mercados desde {desde}; "
             f"{len(recientes)} desde {hoy_madrid().year - 4}. "
             f"La más reciente es la de {ultima.oferente} sobre {ultima.sociedad}, con plazo de aceptación desde el {_f(ultima.inicio_aceptacion)}")
    if ultima.resultado == "Positivo" and ultima.aceptacion_pct is not None and not pd.isna(ultima.aceptacion_pct):
        texto += f" y resultado positivo: acudió el {_num(ultima.aceptacion_pct, 2)} % de las acciones a las que se dirigía."
    elif ultima.resultado == "Negativo":
        texto += " y resultado negativo."
    elif ultima.resultado == "En plazo":
        texto += f", y sigue en plazo hasta el {_f(ultima.fin_aceptacion)}."
    else:
        texto += f" ({ultima.resultado.lower()})."
    return texto


def ld_wp(d: pd.DataFrame, fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "OPAs en la bolsa española desde 2000 (El Especulador)",
        "description": "Todas las ofertas públicas de adquisición sobre sociedades cotizadas en la bolsa española que registra BME desde 2000: sociedad, oferente, precio o canje, plazo de aceptación, acciones adquiridas y resultado.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "temporalCoverage": f"{d['inicio_aceptacion'].min().date().isoformat()}/{fecha}",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": "https://www.bolsasymercados.es/",
        "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ["opas", "por_anio"]],
    }, ensure_ascii=False) + "</script>"


def fragmento_wp(d: pd.DataFrame, t: pd.DataFrame, fecha: str) -> str:
    def e(x) -> str:
        return html.escape(str(x)).replace("$", "&#36;")
    filas_t = "\n".join(
        f"<tr><td>{int(x.anio)}</td><td>{int(x.total)}</td><td>{int(x.positivas)}</td><td>{int(x.negativas)}</td><td>{int(x.retiradas)}</td>"
        f"<td>{int(x.en_plazo + x.sin_dato)}</td></tr>" for x in t.itertuples())
    det = d[d["inicio_aceptacion"].dt.year >= DESDE_TABLA]
    filas_d = "\n".join(
        f"<tr><td>{e(x.sociedad)}</td><td>{e(x.oferente or '—')}</td><td>{e(_contraprestacion(x))}</td>"
        f"<td>{_f(x.inicio_aceptacion)} – {_f(x.fin_aceptacion)}</td><td>{_aceptacion(x.aceptacion_pct)}</td>"
        f"<td>{e(x.resultado)}</td></tr>" for x in det.itertuples())
    return f"""<!-- opas:inicio {fecha} -->
<p><strong>Datos de BME, comprobados cada día hábil; última novedad incorporada el {_f(fecha)}.</strong> {e(frase(d, t))}</p>
<h2>OPAs por año</h2>
<figure class="wp-block-table"><table><thead><tr><th>Año</th><th>OPAs</th><th>Positivas</th><th>Negativas</th><th>Retiradas</th><th>En plazo o sin dato</th></tr></thead><tbody>
{filas_t}
</tbody></table></figure>
<h2>Todas las OPAs desde {DESDE_TABLA}</h2>
<p>De la más reciente a la más antigua. La aceptación es la parte de las acciones a las que se dirigía la oferta que acudió a ella; en las OPAs con resultado negativo BME no la registra. En las ofertas con canje, el texto entre comillas es el que anota BME: la relación exacta está en el folleto aprobado por la CNMV.</p>
<figure class="wp-block-table"><table><thead><tr><th>Sociedad</th><th>Oferente</th><th>Precio o canje</th><th>Plazo de aceptación</th><th>Aceptación</th><th>Resultado</th></tr></thead><tbody>
{filas_d}
</tbody></table></figure>
{ld_wp(d, fecha)}
<!-- opas:fin -->"""


def pagina(cuerpo: str, ld: str = "") -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>OPAs en la bolsa española desde 2000 | El Especulador</title>
<meta name="description" content="Todas las OPAs sobre sociedades cotizadas en la bolsa española desde 2000, con oferente, precio o canje, plazo de aceptación, aceptación y resultado. Datos de BME.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1100px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.88rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;vertical-align:top}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style>
{ld}
</head><body>
<h1>OPAs en la bolsa española desde 2000</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/opas.csv">todas las OPAs desde 2000</a> · <a href="datos/por_anio.csv">OPAs por año</a> · <a href="datos/ultima.json">JSON</a>. Licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>, citando «El Especulador, a partir de datos de BME». Qué hacer como accionista: <a href="{PILAR}">qué pasa con mis acciones si hay una OPA</a>.</p>
<p class="pie">Fuente: BME, registro de ofertas públicas de adquisición. Las autoriza la CNMV, que es la fuente oficial de cada folleto. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
"""


# --------------------------------------------------------------------------- salida
def _csv(d: pd.DataFrame) -> str:
    x = d.copy()
    for c in ("inicio_aceptacion", "fin_aceptacion", "fecha_resultado", "fecha_retirada"):
        x[c] = x[c].dt.date
    for c in ("acciones_a_las_que_se_dirige", "acciones_adquiridas"):
        x[c] = x[c].astype("Int64")
    return x.to_csv(index=False)


def escribir(d: pd.DataFrame, forzar: bool = False) -> bool:
    """Escribe solo si el registro ha cambiado (o con forzar). Devuelve si ha escrito."""
    texto = _csv(d)
    previo = DATOS / "opas.csv"
    if previo.exists() and previo.read_text(encoding="utf-8") == texto and not forzar:
        return False
    fecha = hoy_madrid().date().isoformat()
    DATOS.mkdir(parents=True, exist_ok=True)
    previo.write_text(texto, encoding="utf-8")
    t = por_anio(d)
    t.to_csv(DATOS / "por_anio.csv", index=False)
    ultima = d.iloc[0]
    (DATOS / "ultima.json").write_text(json.dumps({
        "fecha": fecha, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "opas": int(len(d)), "desde": d["inicio_aceptacion"].min().date().isoformat(),
        "ultima": {"sociedad": ultima.sociedad, "oferente": ultima.oferente,
                   "inicio_aceptacion": _f(ultima.inicio_aceptacion), "resultado": ultima.resultado},
        "fuente": "BME, registro de OPAs (CorporateActions/TakeoverBids)", "licencia": "CC BY 4.0 · El Especulador",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento_wp(d, t, fecha)
    assert "$" not in frag
    (SALIDA / "fragmento-wp.html").write_text(frag, encoding="utf-8")
    cuerpo = "\n".join(l for l in frag.split("\n")[1:-1] if "application/ld+json" not in l)
    (SALIDA / "index.html").write_text(pagina(cuerpo, ld_wp(d, fecha)), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="JSON con la respuesta de BME (pruebas)")
    ap.add_argument("--forzar", action="store_true", help="reescribir aunque no haya cambios")
    args = ap.parse_args()
    if args.local:
        j = json.loads(Path(args.local).read_text(encoding="utf-8"))
        filas = j["data"] if isinstance(j, dict) else j
    else:
        filas = descargar()
    d = preparar(filas)
    if escribir(d, args.forzar):
        print(frase(d, por_anio(d)))
    else:
        print(f"Sin novedades en el registro de OPAs de BME ({len(d)} OPAs): no se toca nada.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
