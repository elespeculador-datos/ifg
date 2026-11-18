"""Salidas a bolsa en España desde 2000 (El Especulador).

Registro de todas las empresas que empezaron a cotizar en el Mercado Continuo
(SIBE) con una oferta pública de acciones desde el 1/1/2000, y qué ha sido de
cada una. Dos fuentes:

  salidas_bolsa/registro.csv     registro curado a mano: cada salida con su fecha,
                            precio, tipo de oferta, importe, y si ya no cotiza,
                            cuándo y por qué. Cada fila lleva su fuente.
  salidas_bolsa/descartadas.csv  admisiones que NO son salidas con oferta (traslados
                            desde BME Growth, escisiones, listados directos),
                            para no volver a avisar de ellas.
  API pública de BME        cada día hábil: qué empresas cotizan hoy en el SIBE,
                            admisiones del último año (para avisar de salidas
                            nuevas) y precios de las salidas de los últimos
                            cinco años (lo que guarda su histórico).

Publica en docs/salidas_bolsa/:
  datos/salidas.csv         el registro, con el estado de hoy
  datos/por_anio.csv        salidas, importe y supervivientes por año
  datos/recientes.csv       las de los últimos cinco años con su precio
  datos/descartadas.csv     copia de salidas_bolsa/descartadas.csv
  datos/ultima.json         resumen
  datos/avisos.json         lo que hay que revisar a mano (el flujo abre una incidencia)
  fragmento-wp.html         tablas para la página de elespeculador.com
  index.html                página propia del dato

Uso:
  python salidas_bolsa/salidas.py                  descarga de BME y publica si cambia algo
  python salidas_bolsa/salidas.py --local F.json   usa una respuesta ya descargada (pruebas)
  python salidas_bolsa/salidas.py --forzar         reescribe aunque no haya cambios
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/",
             "Accept": "application/json, text/plain, */*"}
RAIZ = Path(__file__).resolve().parent.parent
# Ni «salidas/» ni «docs/salidas/»: .gitignore ignora cualquier carpeta «salidas/» (gráficos locales).
REGISTRO = RAIZ / "salidas_bolsa" / "registro.csv"
DESCARTADAS = RAIZ / "salidas_bolsa" / "descartadas.csv"
SALIDA = RAIZ / "docs" / "salidas_bolsa"
DATOS = SALIDA / "datos"
PAGINA_WP = "https://elespeculador.com/salidas-a-bolsa-espana/"
PAGES = "https://elespeculador-datos.github.io/ifg/salidas_bolsa/"
OPAS_WP = "https://elespeculador.com/opas-bolsa-espanola/"
ANIOS_PRECIOS = 5            # el histórico de precios de BME llega a cinco años
MINIMO_COTIZADAS = 100       # el 22/10/2026 había 122 valores en el SIBE
TEXTOS = "2"                 # súbelo al cambiar un texto fijo, para que se republique
COLUMNAS = ["empresa", "nombre_hoy", "isin", "extranjera", "fecha_primera_sesion", "tipo_oferta", "precio_salida_eur",
            "importe_oferta_meur", "importe_con_green_shoe", "precio_fuente_unica", "estado_hoy", "nota_hoy",
            "fecha_exclusion", "motivo_exclusion", "detalle_exclusion", "fuente_salida", "fuente_exclusion", "confianza", "notas"]
SI = ["true", "1", "sí", "si"]
FORMATOS = {10: "%Y-%m-%d", 7: "%Y-%m", 4: "%Y"}  # día, mes o solo año, si la fuente no da más
MOTIVOS = ["OPA de exclusión", "OPA", "fusión o absorción", "concurso o liquidación",
           "exclusión a petición propia sin OPA", "otro"]


class DatosRaros(Exception):
    """La respuesta no tiene la forma esperada: mejor parar que publicar basura."""


def hoy_madrid() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(ZoneInfo("Europe/Madrid")).date())


# --------------------------------------------------------------------------- registro curado
def _fechas(s: pd.Series, col: str) -> pd.Series:
    """Admite el día (2006-05-17), solo el mes (2006-05) o solo el año (2005) cuando
    la fuente no da más. La fecha completa del mes o del año es su primer día, solo
    para ordenar: lo que se publica es lo que dice el registro."""
    def una(v: str):
        v = v.strip()
        if not v:
            return pd.NaT
        if len(v) not in FORMATOS:
            raise DatosRaros(f"Fecha con formato desconocido en {col}: «{v}»")
        return pd.to_datetime(v, format=FORMATOS[len(v)], errors="raise")
    return s.map(una)


def leer_registro() -> pd.DataFrame:
    d = pd.read_csv(REGISTRO, dtype=str, keep_default_na=False)
    faltan = set(COLUMNAS) - set(d.columns)
    if faltan:
        raise DatosRaros(f"Faltan columnas en salidas_bolsa/registro.csv: {sorted(faltan)}")
    d = d[COLUMNAS].copy()
    d["fecha_primera_sesion_txt"] = d["fecha_primera_sesion"].str.strip()
    d["fecha_exclusion_txt"] = d["fecha_exclusion"].str.strip()
    d["fecha_primera_sesion"] = _fechas(d["fecha_primera_sesion"], "fecha_primera_sesion")
    d["fecha_exclusion"] = _fechas(d["fecha_exclusion"], "fecha_exclusion")
    if d["fecha_primera_sesion"].isna().any():
        raise DatosRaros(f"Salidas sin fecha: {', '.join(d.loc[d['fecha_primera_sesion'].isna(), 'empresa'])}")
    for c in ("precio_salida_eur", "importe_oferta_meur"):
        d[c] = pd.to_numeric(d[c].replace("", None), errors="raise")
    for c in ("extranjera", "importe_con_green_shoe", "precio_fuente_unica"):
        d[c] = d[c].str.lower().isin(SI)
    malos = d[(d["estado_hoy"] == "excluida") & ~d["motivo_exclusion"].isin(MOTIVOS)]
    if len(malos):
        raise DatosRaros(f"Motivo de exclusión desconocido en: {', '.join(malos['empresa'])}")
    if d["fuente_salida"].str.strip().eq("").any():
        raise DatosRaros("Hay salidas sin fuente en el registro")
    if (d["estado_hoy"].eq("excluida") & d["fuente_exclusion"].str.strip().eq("")).any():
        raise DatosRaros("Hay exclusiones sin fuente en el registro")
    return d.sort_values("fecha_primera_sesion", ascending=False).reset_index(drop=True)


def leer_descartadas() -> set[str]:
    if not DESCARTADAS.exists():
        return set()
    return set(pd.read_csv(DESCARTADAS, dtype=str, keep_default_na=False)["isin"].str.strip()) - {""}


# --------------------------------------------------------------------------- BME
def _get(ruta: str, params: dict, intentos: int = 3) -> dict:
    ultimo = ""
    for i in range(intentos):
        try:
            r = requests.get(API + ruta, params=params, headers=CABECERAS, timeout=60)
            if r.status_code == 200:
                return r.json()
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo = str(e)[:120]
        time.sleep(3 * (i + 1))
    raise DatosRaros(f"BME no responde en {ruta}: {ultimo}")


def descargar(registro: pd.DataFrame) -> dict:
    h = hoy_madrid()
    res = {"listed": _get("ListedCompanies", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0}),
           "newlistings": _get("CorporateActions/NewListings", {"from": f"{h.year - 1}0101", "to": f"{h.year + 1}1231",
                                                                "page": 0, "pageSize": 0}),
           "cierre": _get("ShareDetailsInfo", {"isin": "ES0113900J37"}), "hist": {}}
    desde = h - pd.DateOffset(years=ANIOS_PRECIOS)
    for x in registro.itertuples():
        if x.isin and x.fecha_primera_sesion >= desde:
            res["hist"][x.isin] = _get("HistoricalSharesPrices", {"isin": x.isin, "from": x.fecha_primera_sesion.strftime("%Y%m%d"),
                                                                  "to": h.strftime("%Y%m%d"), "page": 0, "pageSize": 0})
            time.sleep(1)
    return res


def cotizadas(bme: dict) -> dict[str, dict]:
    filas = bme["listed"].get("data", []) if isinstance(bme.get("listed"), dict) else []
    if len(filas) < MINIMO_COTIZADAS:
        raise DatosRaros(f"Solo {len(filas)} valores en la lista de cotizadas de BME")
    return {f["isin"]: f for f in filas if f.get("isin")}


def fecha_cierre(bme: dict) -> pd.Timestamp:
    f = (bme.get("cierre") or {}).get("lastClosePriceDate") or ""
    t = pd.to_datetime(f, format="%Y%m%d", errors="coerce")
    if pd.isna(t):
        raise DatosRaros("BME no da la fecha del último cierre")
    return t


def evolucion(registro: pd.DataFrame, bme: dict, vivas: dict[str, dict]) -> pd.DataFrame:
    """Para las salidas de los últimos cinco años que siguen cotizando: precio del
    primer cierre y del último, y la variación desde el precio de salida. Solo
    precio (sin dividendos). Si BME marca un ajuste de capital (split, contrasplit,
    ampliación con derechos) después de la salida, no se calcula: la comparación
    directa saldría mal."""
    out = []
    desde = hoy_madrid() - pd.DateOffset(years=ANIOS_PRECIOS)
    for x in registro.itertuples():
        # Solo las de los últimos cinco años: de las anteriores, BME no guarda el primer día.
        if x.fecha_primera_sesion < desde or x.isin not in bme.get("hist", {}) or x.isin not in vivas:
            continue
        datos = sorted((bme["hist"][x.isin] or {}).get("data", []) or [], key=lambda r: r["date"])
        if not datos:
            continue
        primera, ultima = datos[0], datos[-1]
        ajuste = any((r.get("facMult") or 0) not in (0, 1) for r in datos[1:])
        cierre1, cierre = float(primera["close"]), float(ultima["close"])
        p = x.precio_salida_eur
        out.append({"empresa": x.nombre_hoy or x.empresa, "isin": x.isin, "fecha_primera_sesion": x.fecha_primera_sesion,
                    "precio_salida_eur": p, "cierre_primer_dia_eur": cierre1,
                    "estreno_pct": None if ajuste or not p else round(100 * (cierre1 / p - 1), 1),
                    "fecha_ultimo_cierre": pd.to_datetime(ultima["date"], format="%Y%m%d"), "ultimo_cierre_eur": cierre,
                    "variacion_desde_salida_pct": None if ajuste or not p else round(100 * (cierre / p - 1), 1),
                    "ajuste_capital": ajuste})
    return pd.DataFrame(out)


def estado(registro: pd.DataFrame, vivas: dict[str, dict], descartadas: set[str], bme: dict) -> tuple[pd.DataFrame, list[str]]:
    """El estado de hoy sale de la lista de BME, no del registro: si una empresa
    que el registro da por cotizada ya no está en el SIBE, la página no lo afirma
    y se avisa para completar el motivo."""
    avisos = []
    d = registro.copy()
    for i, x in d.iterrows():
        isin = x["isin"]  # x.isin sería el método de pandas, no la columna
        if x["estado_hoy"] == "excluida":
            if isin and isin in vivas:
                avisos.append(f"{x['empresa']} figura como excluida en el registro, pero su ISIN {isin} está en la lista del SIBE: revisa la fila.")
        elif isin and isin in vivas:
            d.at[i, "estado_hoy"] = "cotiza"
        elif x["estado_hoy"] == "cotiza":
            d.at[i, "estado_hoy"] = "por confirmar"
            avisos.append(f"{x['empresa']} ({isin or 'sin ISIN'}) figura como cotizada en el registro, pero no está en la lista del SIBE de BME: "
                          "comprueba si ha dejado de cotizar y completa fecha y motivo de exclusión.")
    conocidas = set(d["isin"]) | descartadas
    for a in (bme.get("newlistings") or {}).get("data", []) or []:
        if a.get("admissionType") == "NewListing" and a.get("isin") in vivas and a["isin"] not in conocidas:
            avisos.append(f"Admisión nueva en el SIBE sin registrar: {a.get('share')} ({a['isin']}), {a.get('admissionDate')}. "
                          "Si es una salida con oferta, añádela a salidas_bolsa/registro.csv con su fuente; si no, a salidas_bolsa/descartadas.csv.")
    return d, avisos


# --------------------------------------------------------------------------- tablas
def por_anio(d: pd.DataFrame) -> pd.DataFrame:
    x = d.assign(anio=d["fecha_primera_sesion"].dt.year, vive=d["estado_hoy"].eq("cotiza"))
    t = x.groupby("anio").agg(salidas=("empresa", "count"), importe_meur=("importe_oferta_meur", "sum"),
                              importe_sin_dato=("importe_oferta_meur", lambda s: int(s.isna().sum())),
                              siguen_cotizando=("vive", "sum"))
    anios = range(int(t.index.min()), hoy_madrid().year + 1)
    t = t.reindex(anios, fill_value=0)  # los años sin ninguna salida también cuentan
    t.index.name = "anio"
    return t.reset_index().sort_values("anio", ascending=False).reset_index(drop=True)


def destinos(d: pd.DataFrame) -> list[tuple[str, int]]:
    out = [("Siguen cotizando", int(d["estado_hoy"].eq("cotiza").sum()))]
    ex = d[d["estado_hoy"].eq("excluida")]
    for m in MOTIVOS:
        n = int(ex["motivo_exclusion"].eq(m).sum())
        if n:
            out.append((f"Excluidas: {m}", n))
    n = int(d["estado_hoy"].eq("por confirmar").sum())
    if n:
        out.append(("Ya no están en el SIBE (motivo por confirmar)", n))
    return out


# --------------------------------------------------------------------------- formato
def _f(x) -> str:
    return "—" if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fs(x, txt: str) -> str:
    """Fecha con la precisión que da el registro: día, mes o año."""
    if x is None or pd.isna(x):
        return "—"
    if len(txt) == 7:
        return f"{MESES[x.month - 1]} de {x.year}"
    if len(txt) == 4:
        return str(x.year)
    return _f(x)


def _num(x, dec: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    dec = 3 if round(x, 2) != round(x, 3) else 2
    return _num(x, dec) + " €"


def _pct(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return ("+" if x > 0 else "−" if x < 0 else "") + _num(abs(x), 1) + " %"


def _e(x) -> str:
    return html.escape(str(x)).replace("$", "&#36;")


def _estado(x) -> str:
    if x.estado_hoy == "cotiza":
        return ("Cotiza" + (f" (hoy {x.nombre_hoy})" if x.nombre_hoy and x.nombre_hoy != x.empresa else "")
                + (f"; {x.nota_hoy}" if x.nota_hoy else ""))
    if x.estado_hoy == "por confirmar":
        return "Ya no está en el SIBE (por confirmar)"
    t = f"Excluida en {x.fecha_exclusion.year}" if not pd.isna(x.fecha_exclusion) else "Excluida"
    return t + (f": {x.detalle_exclusion}" if x.detalle_exclusion else f" ({x.motivo_exclusion})")


def frase(d: pd.DataFrame) -> str:
    n, vivas = len(d), int(d["estado_hoy"].eq("cotiza").sum())
    desde = int(d["fecha_primera_sesion"].dt.year.min())
    ult = d.iloc[0]
    ex = d[d["estado_hoy"].eq("excluida")]
    partes = [f"{int(ex['motivo_exclusion'].isin(['OPA de exclusión', 'OPA']).sum())} tras una OPA",
              f"{int(ex['motivo_exclusion'].eq('fusión o absorción').sum())} por fusión o absorción",
              f"{int(ex['motivo_exclusion'].eq('concurso o liquidación').sum())} por concurso o liquidación"]
    otras = len(ex) - sum(int(p.split()[0]) for p in partes)
    texto = (f"Desde {desde}, {n} empresas han empezado a cotizar en el mercado continuo con una oferta pública de acciones. "
             f"Hoy siguen cotizando {vivas} ({_num(100 * vivas / n, 0)} %). De las {len(ex)} que ya no cotizan, "
             f"{partes[0]}, {partes[1]} y {partes[2]}" + (f"; {otras} por otros motivos" if otras else "") + ". "
             f"La salida más reciente es la de {ult.empresa}, el {_fs(ult.fecha_primera_sesion, ult.fecha_primera_sesion_txt)}, "
             f"a {_eur(ult.precio_salida_eur)} por acción.")
    return texto


def ld_wp(d: pd.DataFrame, fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Salidas a bolsa en España desde 2000 (El Especulador)",
        "description": "Todas las empresas que empezaron a cotizar en el mercado continuo español con una oferta pública de acciones desde 2000: fecha, precio de salida, tipo de oferta, importe y qué ha sido de cada una (si cotiza o cuándo y por qué dejó de cotizar).",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "temporalCoverage": f"{d['fecha_primera_sesion'].min().date().isoformat()}/{fecha}",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de BME, la CNMV y las propias empresas",
        "isBasedOn": ["https://www.bolsasymercados.es/", "https://www.cnmv.es/"], "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ["salidas", "por_anio", "recientes", "descartadas"]],
    }, ensure_ascii=False) + "</script>"


def fragmento_wp(d: pd.DataFrame, t: pd.DataFrame, rec: pd.DataFrame, fecha: str, huella: str) -> str:
    filas_t = "\n".join(
        f"<tr><td>{int(x.anio)}</td><td>{int(x.salidas)}</td><td>{_num(x.importe_meur, 0) if x.importe_meur else '—'}"
        f"{'*' if x.importe_sin_dato else ''}</td><td>{int(x.siguen_cotizando)}</td></tr>" for x in t.itertuples())
    filas_dest = "\n".join(f"<tr><td>{_e(k)}</td><td>{v}</td></tr>" for k, v in destinos(d))
    if len(rec):
        filas_r = "\n".join(
            f"<tr><td>{_e(x.empresa)}</td><td>{_f(x.fecha_primera_sesion)}</td><td>{_eur(x.precio_salida_eur)}</td>"
            f"<td>{_eur(x.cierre_primer_dia_eur)} ({_pct(x.estreno_pct)})</td><td>{_eur(x.ultimo_cierre_eur)}</td>"
            f"<td>{_pct(x.variacion_desde_salida_pct)}</td></tr>"
            for x in rec.sort_values("fecha_primera_sesion", ascending=False).itertuples())
        bloque_r = f"""<h2>Las salidas de los últimos cinco años: cuánto valen hoy</h2>
<p>Las que siguen cotizando, con el precio de salida, el cierre de su primer día y el último cierre (al {_f(fecha)}). La variación es solo de precio: no incluye dividendos.</p>
<figure class="wp-block-table"><table><thead><tr><th>Empresa</th><th>Primera sesión</th><th>Precio de salida</th><th>Cierre del primer día</th><th>Último cierre</th><th>Desde la salida</th></tr></thead><tbody>
{filas_r}
</tbody></table></figure>
"""
    else:
        bloque_r = ""
    filas_d = "\n".join(
        f"<tr><td>{_e(x.empresa)}{' (extranjera)' if x.extranjera else ''}</td><td>{_fs(x.fecha_primera_sesion, x.fecha_primera_sesion_txt)}</td>"
        f"<td>{_e(x.tipo_oferta) or '—'}</td><td>{_eur(x.precio_salida_eur)}{' ‡' if x.precio_fuente_unica and not pd.isna(x.precio_salida_eur) else ''}</td>"
        f"<td>{_num(x.importe_oferta_meur, 0)}{' †' if x.importe_con_green_shoe and not pd.isna(x.importe_oferta_meur) else ''}</td>"
        f"<td>{_e(_estado(x))}</td></tr>" for x in d.itertuples())
    return f"""<!-- salidas:inicio {fecha} {huella} -->
<p><strong>Registro de El Especulador, comprobado cada día hábil con los datos de BME; último cierre incorporado el {_f(fecha)}.</strong> {_e(frase(d))}</p>
<h2>Qué ha sido de ellas</h2>
<figure class="wp-block-table"><table><thead><tr><th>Destino</th><th>Empresas</th></tr></thead><tbody>
{filas_dest}
</tbody></table></figure>
{bloque_r}<h2>Salidas a bolsa por año</h2>
<p>El importe es la suma de lo colocado en las ofertas de cada año, en millones de euros, sin el <em>green shoe</em> salvo en las salidas en las que consta que se ejerció (las marcadas con † en la tabla de abajo).{' * Falta el importe de alguna salida de ese año.' if t['importe_sin_dato'].any() else ''}</p>
<figure class="wp-block-table"><table><thead><tr><th>Año</th><th>Salidas</th><th>Importe (millones de €)</th><th>Siguen cotizando</th></tr></thead><tbody>
{filas_t}
</tbody></table></figure>
<h2>Todas las salidas a bolsa desde 2000</h2>
<p>De la más reciente a la más antigua. OPV: venta de acciones existentes; OPS: acciones nuevas; mixta: las dos. El precio es el de salida por acción, y el importe, lo colocado en la oferta en millones de euros, sin el <em>green shoe</em> salvo donde se indica.</p>
<p>† Incluye el <em>green shoe</em>, porque consta que se ejerció. ‡ Precio con una sola fuente pública. — Dato que no hemos podido confirmar en una fuente pública. Las exclusiones por OPA están detalladas en el <a href="{OPAS_WP}">registro de OPAs</a>.</p>
<figure class="wp-block-table"><table><thead><tr><th>Empresa</th><th>Primera sesión</th><th>Oferta</th><th>Precio</th><th>Importe (millones de €)</th><th>Hoy</th></tr></thead><tbody>
{filas_d}
</tbody></table></figure>
{ld_wp(d, fecha)}
<!-- salidas:fin -->"""


def pagina(cuerpo: str, ld: str = "") -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Salidas a bolsa en España desde 2000 | El Especulador</title>
<meta name="description" content="Todas las salidas a bolsa con oferta pública en el mercado continuo español desde 2000: precio, importe y qué ha sido de cada empresa.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1100px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.88rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;vertical-align:top}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style>
{ld}
</head><body>
<h1>Salidas a bolsa en España desde 2000</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/salidas.csv">todas las salidas, con su fuente</a> · <a href="datos/por_anio.csv">por año</a> · <a href="datos/recientes.csv">las de los últimos cinco años</a> · <a href="datos/descartadas.csv">admisiones descartadas, con el motivo</a> · <a href="datos/ultima.json">JSON</a>. Puedes reutilizarlos citando «El Especulador». Los precios de cotización son de BME y se rigen por sus condiciones.</p>
<p class="pie">Fuentes: CNMV (folletos y comunicaciones de las empresas), BME (registro de ofertas públicas, lista de cotizadas y precios) y las propias empresas; cada fila del CSV lleva la suya. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
"""


# --------------------------------------------------------------------------- salida
def _csv_registro(d: pd.DataFrame) -> str:
    """El registro tal cual, con las fechas con la precisión que da la fuente."""
    x = d.drop(columns=["fecha_primera_sesion_txt", "fecha_exclusion_txt"])
    x["fecha_primera_sesion"], x["fecha_exclusion"] = d["fecha_primera_sesion_txt"], d["fecha_exclusion_txt"]
    return x.to_csv(index=False)


def _csv(d: pd.DataFrame, fechas: tuple[str, ...]) -> str:
    x = d.copy()
    for c in fechas:
        if c in x:
            x[c] = x[c].dt.date
    return x.to_csv(index=False)


def escribir(d: pd.DataFrame, rec: pd.DataFrame, avisos: list[str], fecha: pd.Timestamp, forzar: bool = False) -> bool:
    t = por_anio(d)
    salidas_csv = _csv_registro(d)
    rec_csv = _csv(rec, ("fecha_primera_sesion", "fecha_ultimo_cierre")) if len(rec) else ""
    desc_csv = DESCARTADAS.read_text(encoding="utf-8") if DESCARTADAS.exists() else ""
    huella = hashlib.sha1((salidas_csv + rec_csv + desc_csv + TEXTOS).encode()).hexdigest()[:12]
    frag_prev = SALIDA / "fragmento-wp.html"
    if not forzar and frag_prev.exists() and huella in frag_prev.read_text(encoding="utf-8").split("\n", 1)[0]:
        return False
    f = fecha.date().isoformat()
    DATOS.mkdir(parents=True, exist_ok=True)
    (DATOS / "salidas.csv").write_text(salidas_csv, encoding="utf-8")
    t.to_csv(DATOS / "por_anio.csv", index=False)
    (DATOS / "recientes.csv").write_text(rec_csv, encoding="utf-8")
    (DATOS / "descartadas.csv").write_text(desc_csv, encoding="utf-8")
    (DATOS / "avisos.json").write_text(json.dumps(avisos, ensure_ascii=False, indent=1), encoding="utf-8")
    ult = d.iloc[0]
    (DATOS / "ultima.json").write_text(json.dumps({
        "fecha": f, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "salidas": int(len(d)), "siguen_cotizando": int(d["estado_hoy"].eq("cotiza").sum()),
        "desde": d["fecha_primera_sesion"].min().date().isoformat(),
        "ultima": {"empresa": ult.empresa, "fecha_primera_sesion": ult.fecha_primera_sesion_txt, "precio_salida_eur": ult.precio_salida_eur},
        "fuente": "Registro curado de El Especulador (CNMV, BME, empresas); estado y precios diarios de la API de BME",
        "licencia": "Cita: El Especulador. Los precios de cotización son de BME y se rigen por sus condiciones",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento_wp(d, t, rec, f, huella)
    if "$" in frag:
        raise DatosRaros("El fragmento contiene «$»: el reemplazo de Make lo rompería")
    frag_prev.write_text(frag, encoding="utf-8")
    cuerpo = "\n".join(l for l in frag.split("\n")[1:-1] if "application/ld+json" not in l)
    (SALIDA / "index.html").write_text(pagina(cuerpo, ld_wp(d, f)), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="JSON con las respuestas de BME ya descargadas (pruebas)")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()
    registro = leer_registro()
    bme = json.loads(Path(args.local).read_text(encoding="utf-8")) if args.local else descargar(registro)
    vivas = cotizadas(bme)
    d, avisos = estado(registro, vivas, leer_descartadas(), bme)
    rec = evolucion(d, bme, vivas)
    if escribir(d, rec, avisos, fecha_cierre(bme), args.forzar):
        print(frase(d))
    else:
        print("Sin cambios en el registro ni en los precios: no se toca nada.")
    for a in avisos:
        print(f"::warning::{a}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
