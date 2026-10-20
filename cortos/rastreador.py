"""Rastreador de posiciones cortas de El Especulador.

Descarga cada día el fichero oficial de la CNMV con las posiciones cortas netas
publicadas sobre acciones españolas (las que alcanzan o superan el 0,5 % del
capital) y lo convierte en datos abiertos y en una página legible:

  docs/cortos/index.html                 página del rastreador
  docs/cortos/datos/vigentes.csv         posiciones publicadas hoy
  docs/cortos/datos/resumen_emisores.csv suma publicada y nº de tenedores por emisor
  docs/cortos/datos/serie.csv            evolución de las posiciones vigentes
  docs/cortos/datos/anteriores.csv       posiciones que ya bajaron del 0,5 %
  docs/cortos/datos/cambios.csv          altas, subidas, bajadas y salidas del día
  docs/cortos/datos/historial_cambios.csv  todos los cambios detectados, acumulados
  docs/cortos/datos/ultima.json          resumen para webs y widgets
  docs/cortos/fragmento-wp.html          tablas en HTML para la página de elespeculador.com

Fuente: CNMV, «Posiciones cortas netas», fichero NetShortPositions.xls.
Licencia de los datos derivados: CC BY 4.0, citando a El Especulador y a la CNMV.

Uso:
  python cortos/rastreador.py                 descarga y publica
  python cortos/rastreador.py --local F.xls   usa un fichero ya descargado (pruebas)
  python cortos/rastreador.py --solo-fragmento  rehace el fragmento con los CSV publicados
"""
from __future__ import annotations

import argparse
import html
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls"
FICHA_CNMV = "https://www.cnmv.es/portal/consultas/busqueda?id=29"
PILAR = "https://elespeculador.com/posiciones-cortas-bolsa-espanola/"
PAGINA_WP = "https://elespeculador.com/posiciones-cortas-hoy/"
PAGES = "https://elespeculador-datos.github.io/ifg/cortos/"
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "cortos"
DATOS = SALIDA / "datos"

COLUMNAS = ["lei", "isin", "emisor", "tenedor", "fecha_posicion", "posicion_pct"]
HOJAS = {"fecha": "Fecha", "vigentes": "Última", "serie": "Serie", "anteriores": "Anteriores"}


class DatosRaros(Exception):
    """El fichero no tiene la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga
def descargar() -> bytes:
    ultimo_error = None
    for intento in range(4):
        try:
            r = requests.get(URL, timeout=90, headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"})
            if r.status_code == 200 and r.content[:4] == b"\xd0\xcf\x11\xe0":
                return r.content
            ultimo_error = f"HTTP {r.status_code}, {len(r.content)} bytes, cabecera {r.content[:8]!r}"
        except requests.RequestException as e:
            ultimo_error = str(e)
        time.sleep(20 * (intento + 1))
    raise DatosRaros(f"No se pudo descargar el fichero de la CNMV: {ultimo_error}")


# --------------------------------------------------------------------------- lectura
def _hoja(libro: dict, clave: str) -> pd.DataFrame:
    nombre = next((n for n in libro if n.startswith(HOJAS[clave])), None)
    if nombre is None:
        raise DatosRaros(f"Falta la hoja «{HOJAS[clave]}…»; hojas: {list(libro)}")
    return libro[nombre]


def _tabla(df: pd.DataFrame, nombre: str) -> pd.DataFrame:
    fila = next((i for i in range(min(15, len(df))) if df.iloc[i].astype(str).str.contains("ISIN").any()), None)
    if fila is None:
        raise DatosRaros(f"No encuentro la cabecera en la hoja {nombre}")
    cab = [str(c) for c in df.iloc[fila].tolist()]
    if len(cab) < 6 or "LEI" not in cab[0] or "ISIN" not in cab[1] or "%" not in cab[5]:
        raise DatosRaros(f"Cabecera inesperada en {nombre}: {cab}")
    t = df.iloc[fila + 1:, :6].dropna(how="all").copy()
    t.columns = COLUMNAS
    t = t.dropna(subset=["isin", "tenedor"])
    for c in ["lei", "isin", "emisor", "tenedor"]:
        t[c] = t[c].astype(str).str.strip()
    t["fecha_posicion"] = pd.to_datetime(t["fecha_posicion"], errors="coerce").dt.date
    t["posicion_pct"] = pd.to_numeric(t["posicion_pct"], errors="coerce")
    if t["fecha_posicion"].isna().any() or t["posicion_pct"].isna().any():
        malas = t[t["fecha_posicion"].isna() | t["posicion_pct"].isna()].head(3).to_dict("records")
        raise DatosRaros(f"Fechas o porcentajes ilegibles en {nombre}: {malas}")
    return t.reset_index(drop=True)


def leer(contenido: bytes) -> tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None, engine="xlrd")
    except Exception:
        libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None)
    fecha_df = _hoja(libro, "fecha")
    texto = " ".join(str(v) for v in fecha_df.values.ravel() if pd.notna(v))
    fecha = pd.to_datetime(next((p for p in texto.split() if p[:2] == "20" and len(p) >= 10), ""), errors="coerce")
    if pd.isna(fecha):
        raise DatosRaros(f"No leo la fecha de publicación: {texto!r}")
    vig = _tabla(_hoja(libro, "vigentes"), "Última")
    serie = _tabla(_hoja(libro, "serie"), "Serie")
    ant = _tabla(_hoja(libro, "anteriores"), "Anteriores")
    if len(vig) < 5 or len(serie) < len(vig) or len(ant) < 1000:
        raise DatosRaros(f"Volumen anómalo: {len(vig)} vigentes, {len(serie)} serie, {len(ant)} anteriores")
    if (vig["posicion_pct"] < 0).any() or (vig["posicion_pct"] < 0.5 - 1e-9).mean() > 0.3:
        raise DatosRaros("Demasiadas posiciones vigentes por debajo del 0,5 %: el fichero ha cambiado de criterio")
    # La hoja «Última» incluye también la comunicación con la que un tenedor
    # baja del 0,5 %: se publica una vez y deja de mostrarse en la siguiente.
    vig["estado"] = vig["posicion_pct"].map(lambda x: "igual o superior al 0,5 %" if x >= 0.5 - 1e-9 else "bajó del 0,5 %")
    return fecha.date().isoformat(), vig, serie, ant


# --------------------------------------------------------------------------- cálculos
def resumen(vig: pd.DataFrame) -> pd.DataFrame:
    vig = vig[vig["posicion_pct"] >= 0.5 - 1e-9]
    g = vig.groupby(["isin", "emisor"], as_index=False).agg(
        tenedores=("tenedor", "nunique"),
        suma_publicada_pct=("posicion_pct", "sum"),
        mayor_posicion_pct=("posicion_pct", "max"),
        ultima_fecha_posicion=("fecha_posicion", "max"),
    )
    mayor = vig.sort_values("posicion_pct", ascending=False).drop_duplicates("isin")[["isin", "tenedor"]]
    g = g.merge(mayor.rename(columns={"tenedor": "mayor_tenedor"}), on="isin")
    g["suma_publicada_pct"] = g["suma_publicada_pct"].round(2)
    return g.sort_values(["suma_publicada_pct", "tenedores"], ascending=False).reset_index(drop=True)


def cambios(prev: pd.DataFrame | None, vig: pd.DataFrame, fecha: str) -> pd.DataFrame:
    clave = ["isin", "tenedor"]
    cols = ["fecha_publicacion", "isin", "emisor", "tenedor", "tipo", "antes_pct", "ahora_pct", "fecha_posicion"]
    if prev is None or prev.empty:
        return pd.DataFrame(columns=cols)
    a = prev.set_index(clave)
    b = vig.set_index(clave)
    filas = []
    for k in b.index.difference(a.index):
        r = b.loc[k]
        filas.append([fecha, k[0], r["emisor"], k[1], "nueva", None, r["posicion_pct"], r["fecha_posicion"]])
    for k in a.index.difference(b.index):
        r = a.loc[k]
        filas.append([fecha, k[0], r["emisor"], k[1], "deja de publicarse", r["posicion_pct"], None, None])
    for k in b.index.intersection(a.index):
        x, y = float(a.loc[k, "posicion_pct"]), float(b.loc[k, "posicion_pct"])
        if abs(x - y) > 1e-9:
            filas.append([fecha, k[0], b.loc[k, "emisor"], k[1], "sube" if y > x else "baja", x, y, b.loc[k, "fecha_posicion"]])
    return pd.DataFrame(filas, columns=cols).sort_values(["emisor", "tenedor"]).reset_index(drop=True)


# --------------------------------------------------------------------------- página
def _pct(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:,.2f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha(d) -> str:
    return "—" if d is None or pd.isna(d) else pd.Timestamp(d).strftime("%d/%m/%Y")


def pagina(fecha: str, vig: pd.DataFrame, res: pd.DataFrame, cam: pd.DataFrame, primera: bool = False, hist: dict | None = None) -> str:
    e = html.escape
    filas_res = "\n".join(
        f"<tr><td>{e(r.emisor)} <span class='isin'>{e(r.isin)}</span></td><td class='n'>{r.tenedores}</td><td class='n'>{_pct(r.suma_publicada_pct)}</td>"
        f"<td>{e(r.mayor_tenedor)} ({_pct(r.mayor_posicion_pct)})</td><td>{_fecha(r.ultima_fecha_posicion)}</td></tr>"
        for r in res.itertuples())
    filas_vig = "\n".join(
        f"<tr><td>{e(r.emisor)}</td><td>{e(r.tenedor)}</td><td class='n'>{_pct(r.posicion_pct)}{' · bajó del umbral' if r.posicion_pct < 0.5 - 1e-9 else ''}</td><td>{_fecha(r.fecha_posicion)}</td></tr>"
        for r in vig.sort_values(["emisor", "posicion_pct"], ascending=[True, False]).itertuples())
    if primera:
        bloque_cam = "<p>Es la primera publicación registrada por el rastreador: los cambios se mostrarán a partir de la próxima.</p>"
    elif cam.empty:
        bloque_cam = "<p>Sin cambios respecto a la publicación anterior.</p>"
    else:
        bloque_cam = "<div class='tabla'><table><thead><tr><th>Emisor</th><th>Tenedor</th><th>Cambio</th><th class='n'>Antes</th><th class='n'>Ahora</th></tr></thead><tbody>" + "\n".join(
            f"<tr><td>{e(r.emisor)}</td><td>{e(r.tenedor)}</td><td>{e(r.tipo)}</td><td class='n'>{_pct(r.antes_pct)}</td><td class='n'>{_pct(r.ahora_pct)}</td></tr>"
            for r in cam.itertuples()) + "</tbody></table></div>"
    top = res.iloc[0] if len(res) else None
    n_umbral = int((vig["posicion_pct"] >= 0.5 - 1e-9).sum())
    frase = (f"A {_fecha(fecha)}, la CNMV publica {n_umbral} posiciones cortas netas iguales o superiores al 0,5 % "
             f"sobre {vig.loc[vig['posicion_pct'] >= 0.5 - 1e-9, 'lei'].nunique()} emisores. La mayor suma publicada es la de {e(top.emisor)}: "
             f"{_pct(top.suma_publicada_pct)} del capital, repartido entre {top.tenedores} tenedores.") if top is not None else ""
    ahora = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Posiciones cortas en la bolsa española, día a día | El Especulador</title>
<meta name="description" content="Rastreador diario de las posiciones cortas netas que publica la CNMV sobre acciones españolas: quién está corto, cuánto y desde cuándo. Datos abiertos.">
<style>
:root{{--t:#1d2733;--s:#5b6675;--b:#d7dde5;--a:#1f4e8c;--f:#f6f8fb}}
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--t);max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem;margin:.2em 0}} h2{{font-size:1.15rem;margin-top:1.6em}}
.sub{{color:var(--s)}} table{{width:100%;border-collapse:collapse;font-size:.92rem;margin:.6em 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--b);vertical-align:top}} th{{background:var(--f)}}
.tabla{{overflow-x:auto}} .isin{{color:var(--s);font-size:.78rem;white-space:nowrap}}
.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}} .caja{{background:var(--f);padding:12px 14px;border-radius:8px}}
a{{color:var(--a)}} .pie{{color:var(--s);font-size:.85rem;margin-top:2em}}
@media(max-width:640px){{table{{font-size:.82rem}} th,td{{padding:5px}}}}
</style>
<script type="application/ld+json">{json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Posiciones cortas netas publicadas en España (rastreador de El Especulador)",
        "description": "Posiciones cortas netas iguales o superiores al 0,5 % del capital sobre acciones españolas, según la CNMV, actualizadas cada día hábil.",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": URL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"datos/{n}.csv"}
                         for n in ["vigentes", "resumen_emisores", "serie", "anteriores", "historial_cambios"]],
    }, ensure_ascii=False)}</script>
</head><body>
<h1>Posiciones cortas en la bolsa española</h1>
<p class="sub">Publicación de la CNMV del {_fecha(fecha)} · actualizado el {ahora} · <a href="https://elespeculador.com/">El Especulador</a></p>
<div class="caja"><p>{frase}</p>
<p>Solo se publican las posiciones de cada tenedor que alcanzan el 0,5 % del capital, y una última vez cuando bajan de ese nivel (aparecen marcadas como «bajó del umbral» y no cuentan en la suma); las menores se comunican a la CNMV pero no se hacen públicas. Por eso la suma publicada es un mínimo, no el total de posiciones cortas sobre cada valor. Cómo se leen estos datos: <a href="{PILAR}">guía de posiciones cortas</a>.</p></div>
<h2>Cambios respecto a la publicación anterior</h2>
{bloque_cam}
<h2>Suma publicada por emisor</h2>
<div class="tabla"><table><thead><tr><th>Emisor</th><th class="n">Tenedores</th><th class="n">Suma publicada</th><th>Mayor posición</th><th>Última fecha de posición</th></tr></thead><tbody>
{filas_res}
</tbody></table></div>
<h2>Quién está corto en más empresas</h2>
{_tabla_tenedores(vig, e).replace('<figure class="wp-block-table">', '<div class="tabla">').replace('</figure>', '</div>')}
{_bloque_historico(hist, e)}
<h2>Todas las posiciones publicadas</h2>
<div class="tabla"><table><thead><tr><th>Emisor</th><th>Tenedor</th><th class="n">Posición</th><th>Fecha de posición</th></tr></thead><tbody>
{filas_vig}
</tbody></table></div>
<h2>Datos abiertos</h2>
<p>Descarga en CSV: <a href="datos/vigentes.csv">posiciones vigentes</a> · <a href="datos/resumen_emisores.csv">resumen por emisor</a> · <a href="datos/serie.csv">evolución de las vigentes</a> · <a href="datos/anteriores.csv">posiciones anteriores desde 2010</a> · <a href="datos/historial_cambios.csv">historial de cambios</a> · <a href="datos/ultima.json">JSON</a>. Licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>: puedes reutilizarlos citando «El Especulador, a partir de datos de la CNMV».</p>
<p class="pie">Fuente: CNMV, <a href="{FICHA_CNMV}">posiciones cortas netas</a> (fichero <a href="{URL}">NetShortPositions.xls</a>). La fecha de posición es el día en que la posición alcanzó, cambió o bajó del umbral; la CNMV la publica al día hábil siguiente. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
"""


def historico(serie: pd.DataFrame, ant: pd.DataFrame) -> dict:
    """Récords del fichero histórico (posiciones vigentes y anteriores desde 2010)."""
    h = pd.concat([ant, serie], ignore_index=True)
    h["isin"] = h["isin"].astype(str).str.upper().str.strip()
    h = h.drop_duplicates(["isin", "tenedor", "fecha_posicion", "posicion_pct"])
    pub = h[h["posicion_pct"] >= 0.5 - 1e-9].sort_values("fecha_posicion")
    mx = pub[pub["posicion_pct"] == pub["posicion_pct"].max()].iloc[0]
    ten = pub.groupby("tenedor")["lei"].nunique().sort_values(ascending=False)
    return {"desde": str(pd.Timestamp(h["fecha_posicion"].min()).date()),
            "mayor_posicion": {"tenedor": mx["tenedor"], "emisor": mx["emisor"], "pct": float(mx["posicion_pct"]),
                               "fecha": str(pd.Timestamp(mx["fecha_posicion"]).date())},
            "mas_empresas": {"tenedor": ten.index[0], "empresas": int(ten.iloc[0])}}


def _bloque_historico(hist: dict | None, e) -> str:
    if not hist:
        return ""
    m, t = hist["mayor_posicion"], hist["mas_empresas"]
    return (f"<h2>Récords del histórico</h2>\n<p>Desde el {_fecha(hist['desde'])}, primera fecha del fichero histórico de la CNMV, "
            f"la mayor posición corta individual publicada es la de {e(m['tenedor'])} en {e(m['emisor'])}: un {_pct(m['pct'])} del capital, "
            f"el {_fecha(m['fecha'])}. La entidad que ha publicado posiciones cortas en más empresas es {e(t['tenedor'])}, en {t['empresas']} empresas distintas. "
            "El fichero no conserva todas las empresas que han dejado de cotizar, así que estos récords se refieren a las que sí recoge.</p>")


def por_tenedor(vig: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Entidades con más posiciones publicadas (tal como las identifica la CNMV)."""
    v = vig[vig["posicion_pct"] >= 0.5 - 1e-9]
    g = v.groupby("tenedor", as_index=False).agg(empresas=("isin", "nunique"))
    mayor = v.sort_values("posicion_pct", ascending=False).drop_duplicates("tenedor")[["tenedor", "emisor", "posicion_pct"]]
    g = g.merge(mayor.rename(columns={"emisor": "mayor_emisor", "posicion_pct": "mayor_pct"}), on="tenedor")
    return g.sort_values(["empresas", "mayor_pct"], ascending=False).head(n).reset_index(drop=True)


def _tabla_tenedores(vig: pd.DataFrame, e) -> str:
    t = por_tenedor(vig)
    filas = "\n".join(f"<tr><td>{e(r.tenedor)}</td><td>{int(r.empresas)}</td><td>{e(r.mayor_emisor)} ({_pct(r.mayor_pct)})</td></tr>"
                      for r in t.itertuples())
    return ("<p>Cada entidad aparece tal como la identifica la CNMV: un mismo grupo puede figurar con varias filiales.</p>\n"
            "<figure class=\"wp-block-table\"><table><thead><tr><th>Tenedor</th><th>Empresas en las que está corto</th><th>Su mayor posición</th></tr></thead><tbody>\n"
            + filas + "\n</tbody></table></figure>")


# --------------------------------------------------------------------------- fragmento para WordPress
def fragmento_wp(fecha: str, fecha_previa: str | None, vig: pd.DataFrame, res: pd.DataFrame, cam: pd.DataFrame, hist: dict | None = None) -> str:
    """HTML estático que Make copia cada día en la página de elespeculador.com.

    Va entre dos marcas: Make sustituye solo lo que hay entre ellas y deja intacto
    el resto de la página. Sin estilos ni el carácter «$», que la sustitución por
    expresión regular de Make interpretaría. El único script es el marcado Dataset
    (JSON-LD, en una línea), que se añade al escribir el fichero con con_ld().
    """
    def e(x) -> str:
        return html.escape(str(x)).replace("$", "&#36;")

    umbral = vig["posicion_pct"] >= 0.5 - 1e-9
    top = res.iloc[0] if len(res) else None
    frase = (f"La CNMV publica {int(umbral.sum())} posiciones cortas netas iguales o superiores al 0,5 % del capital, "
             f"sobre {vig.loc[umbral, 'lei'].nunique()} emisores.")
    if top is not None:
        frase += (f" La mayor suma publicada es la de {e(top.emisor)}: {_pct(top.suma_publicada_pct)} del capital, "
                  f"entre {int(top.tenedores)} tenedores; el mayor de ellos, {e(top.mayor_tenedor)}, con un {_pct(top.mayor_posicion_pct)}.")
    if cam.empty:
        bloque_cam = (f"<p>Sin cambios respecto a la publicación del {_fecha(fecha_previa)}.</p>" if fecha_previa
                      else "<p>Los cambios diarios se verán aquí a partir de la próxima publicación de la CNMV.</p>")
    else:
        bloque_cam = (f"<p>Respecto a la publicación del {_fecha(fecha_previa)}:</p>\n" if fecha_previa else "") + (
            "<figure class=\"wp-block-table\"><table><thead><tr><th>Emisor</th><th>Tenedor</th><th>Cambio</th><th>Antes</th><th>Ahora</th></tr></thead><tbody>\n"
            + "\n".join(f"<tr><td>{e(r.emisor)}</td><td>{e(r.tenedor)}</td><td>{e(r.tipo)}</td><td>{_pct(r.antes_pct)}</td><td>{_pct(r.ahora_pct)}</td></tr>"
                        for r in cam.itertuples())
            + "\n</tbody></table></figure>")
    por_nombre = vig.groupby("emisor")["isin"].nunique()
    repetidos = set(por_nombre[por_nombre > 1].index) | set(res.loc[res["emisor"].duplicated(keep=False), "emisor"])
    filas_res = "\n".join(
        f"<tr><td>{e(r.emisor)}{' (ISIN ' + e(r.isin) + ')' if r.emisor in repetidos else ''}</td><td>{int(r.tenedores)}</td><td>{_pct(r.suma_publicada_pct)}</td>"
        f"<td>{e(r.mayor_tenedor)} ({_pct(r.mayor_posicion_pct)})</td><td>{_fecha(r.ultima_fecha_posicion)}</td></tr>"
        for r in res.itertuples())
    filas_vig = "\n".join(
        f"<tr><td>{e(r.emisor)}{' (ISIN ' + e(r.isin) + ')' if r.emisor in repetidos else ''}</td><td>{e(r.tenedor)}</td><td>{_pct(r.posicion_pct)}{' (bajó del umbral)' if r.posicion_pct < 0.5 - 1e-9 else ''}</td><td>{_fecha(r.fecha_posicion)}</td></tr>"
        for r in vig.sort_values(["emisor", "posicion_pct"], ascending=[True, False]).itertuples())
    return f"""<!-- cortos:inicio {fecha} -->
<p><strong>Datos de la publicación de la CNMV del {_fecha(fecha)}.</strong> {frase}</p>
<h2>Cambios respecto a la publicación anterior</h2>
{bloque_cam}
<h2>Suma publicada por emisor</h2>
<figure class="wp-block-table"><table><thead><tr><th>Emisor</th><th>Tenedores</th><th>Suma publicada</th><th>Mayor posición</th><th>Última fecha de posición</th></tr></thead><tbody>
{filas_res}
</tbody></table></figure>
<h2>Quién está corto en más empresas</h2>
{_tabla_tenedores(vig, e)}
{_bloque_historico(hist, e)}
<h2>Todas las posiciones publicadas</h2>
<figure class="wp-block-table"><table><thead><tr><th>Emisor</th><th>Tenedor</th><th>Posición corta neta</th><th>Fecha de la posición</th></tr></thead><tbody>
{filas_vig}
</tbody></table></figure>
<!-- cortos:fin -->"""


def ld_wp(fecha: str, hist: dict | None) -> str:
    """Marcado Dataset (schema.org) en una sola línea, para la página de elespeculador.com."""
    d = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Posiciones cortas netas publicadas en España (rastreador de El Especulador)",
        "description": "Posiciones cortas netas iguales o superiores al 0,5 % del capital sobre acciones españolas, según la CNMV, con el resumen por empresa y el historial de cambios, actualizadas cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": URL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ["vigentes", "resumen_emisores", "serie", "anteriores", "historial_cambios"]],
    }
    if hist:
        d["temporalCoverage"] = f"{hist['desde']}/{fecha}"
    return '<script type="application/ld+json">' + json.dumps(d, ensure_ascii=False) + "</script>"


def con_ld(frag: str, ld: str) -> str:
    marca = "\n<!-- cortos:fin -->"
    assert frag.count(marca) == 1 and "$" not in ld
    return frag.replace(marca, "\n" + ld + marca)


def solo_fragmento() -> int:
    """Rehace el fragmento con los CSV ya publicados, sin descargar nada."""
    estado = json.loads((DATOS / "ultima.json").read_text(encoding="utf-8"))
    vig = pd.read_csv(DATOS / "vigentes.csv", dtype={"lei": str, "isin": str})
    res = pd.read_csv(DATOS / "resumen_emisores.csv", dtype={"isin": str})
    cam = pd.read_csv(DATOS / "cambios.csv", dtype={"isin": str})
    hist = historico(pd.read_csv(DATOS / "serie.csv", dtype={"lei": str, "isin": str}),
                     pd.read_csv(DATOS / "anteriores.csv", dtype={"lei": str, "isin": str}))
    (SALIDA / "fragmento-wp.html").write_text(con_ld(
        fragmento_wp(estado["fecha_publicacion"], estado.get("publicacion_anterior"), vig, res, cam, hist),
        ld_wp(estado["fecha_publicacion"], hist)), encoding="utf-8")
    print(f"Fragmento rehecho con la publicación del {estado['fecha_publicacion']}.")
    return 0


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="usar un fichero ya descargado")
    ap.add_argument("--solo-fragmento", action="store_true", help="rehacer solo el fragmento para WordPress")
    args = ap.parse_args()
    if args.solo_fragmento:
        return solo_fragmento()
    contenido = Path(args.local).read_bytes() if args.local else descargar()
    fecha, vig, serie, ant = leer(contenido)
    DATOS.mkdir(parents=True, exist_ok=True)

    previo = None
    estado = DATOS / "ultima.json"
    if (DATOS / "vigentes.csv").exists():
        previo = pd.read_csv(DATOS / "vigentes.csv", dtype=str)
        previo["posicion_pct"] = previo["posicion_pct"].astype(float)
    fecha_previa = json.loads(estado.read_text(encoding="utf-8")).get("fecha_publicacion") if estado.exists() else None
    if fecha_previa == fecha and not args.local:
        print(f"La CNMV no ha publicado nada nuevo desde el {fecha}: no se toca nada.")
        return 0

    res = resumen(vig)
    cam = cambios(previo, vig, fecha)
    hist = historico(serie, ant)
    vig.to_csv(DATOS / "vigentes.csv", index=False)
    res.to_csv(DATOS / "resumen_emisores.csv", index=False)
    serie.to_csv(DATOS / "serie.csv", index=False)
    ant.to_csv(DATOS / "anteriores.csv", index=False)
    cam.to_csv(DATOS / "cambios.csv", index=False)
    ruta_cambios = DATOS / "historial_cambios.csv"
    if not cam.empty:
        cam.to_csv(ruta_cambios, mode="a", index=False, header=not ruta_cambios.exists())
    elif not ruta_cambios.exists():
        cam.to_csv(ruta_cambios, index=False)
    estado.write_text(json.dumps({
        "fecha_publicacion": fecha,
        "publicacion_anterior": fecha_previa if fecha_previa != fecha else None,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "posiciones": int((vig["posicion_pct"] >= 0.5 - 1e-9).sum()), "emisores": int(vig.loc[vig["posicion_pct"] >= 0.5 - 1e-9, "lei"].nunique()),
        "cambios": int(len(cam)),
        "historico": hist,
        "top": res.head(10).assign(ultima_fecha_posicion=res.head(10)["ultima_fecha_posicion"].astype(str)).to_dict("records"),
        "fuente": URL, "licencia": "CC BY 4.0 · El Especulador a partir de datos de la CNMV",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (SALIDA / "index.html").write_text(pagina(fecha, vig, res, cam, primera=previo is None, hist=hist), encoding="utf-8")
    (SALIDA / "fragmento-wp.html").write_text(con_ld(
        fragmento_wp(fecha, fecha_previa if fecha_previa != fecha else None, vig, res, cam, hist),
        ld_wp(fecha, hist)), encoding="utf-8")
    print(f"Publicación del {fecha}: {len(vig)} filas vigentes, {vig['lei'].nunique()} emisores, {len(cam)} cambios.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
