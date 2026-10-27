"""Comunicados a la CNMV de las empresas del IBEX 35, clasificados para la página del IBEX de El Especulador.

Cada hora de los días hábiles lee los dos canales RSS públicos de la CNMV (información privilegiada y otra
información relevante). Cada canal solo muestra lo comunicado desde el cierre de la sesión anterior, así que
el script va acumulando todo en un histórico y, a partir de él, publica:

  docs/cnmv/datos/comunicados.csv   todos los comunicados leídos, de cualquier emisor, sin clasificar
  docs/cnmv/datos/ibex35.csv        los del IBEX 35, con su tipo y el grupo (operación) al que pertenecen
  docs/cnmv/datos/ultima.json       resumen
  docs/cnmv/cajas.html              los cuatro recuadros de la página del IBEX 35 (resultados, dividendos,
                                    recompras, OPVs y ampliaciones), entre <!-- cnmv:inicio … --> y <!-- cnmv:fin -->
  docs/cnmv/index.html              página propia con los mismos datos

Regla de duplicados: dos comunicados distintos de la CNMV nunca se pisan (cada uno tiene su número de registro).
Lo que se agrupa es la operación: misma empresa, mismo tipo y misma operación (los informes semanales de un
programa de recompra, los dos comunicados de una misma ampliación, el anuncio de fecha y la publicación de unos
resultados) se muestran como una sola entrada con el último comunicado y el número de comunicados. Una ampliación
y un dividendo de la misma empresa son dos entradas distintas, cada una en su recuadro.

Uso:
  python cnmv/comunicados.py                         descarga y publica si hay novedades
  python cnmv/comunicados.py --local IP.xml OIR.xml  usa canales ya descargados (pruebas)
  python cnmv/comunicados.py --forzar                reescribe aunque no haya comunicados nuevos
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

CANALES = {
    "IP": "https://www.cnmv.es/portal/Informacion-Privilegiada/RSS.asmx/GetNoticiasCNMV",
    "OIR": "https://www.cnmv.es/portal/Otra-Informacion-Relevante/RSS.asmx/GetNoticiasCNMV",
}
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept": "application/rss+xml, application/xml, text/xml, */*"}
MADRID = ZoneInfo("Europe/Madrid")
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "cnmv"
DATOS = SALIDA / "datos"
HISTORICO = DATOS / "comunicados.csv"
EMPRESAS = Path(__file__).resolve().parent / "empresas.csv"
IBEX35 = RAIZ / "dividendos" / "ibex35.csv"      # la misma composición que usa el calendario de dividendos
IBEX35_VALIDA_HASTA = "2026-12-20"                 # mover junto con la de dividendos/calendario.py tras cada revisión
FICHAS = "https://elespeculador.com/ibex35/"
PAGES = "https://elespeculador-datos.github.io/ifg/cnmv/"
DIAS_CAJA = 60          # antigüedad máxima de lo que sale en los recuadros
POR_CAJA = 6            # entradas por recuadro
COLUMNAS = ["canal", "nreg", "fecha", "emisor", "categoria", "texto", "enlace"]

CAJAS = [  # clave (igual que el id del panel en la plantilla de la web), título, descripción del recuadro
    ("resultados", "Resultados", "Cuentas y fechas de publicación comunicadas a la CNMV."),
    ("dividendos", "Dividendos", "Anuncios de dividendo y dividendos flexibles."),
    ("recompras", "Recompras", "Programas de recompra en curso y su último informe."),
    ("opvs-ampliaciones", "OPVs y ampliaciones", "Ampliaciones de capital, colocaciones y salidas a bolsa."),
]
VENTANA = {"resultados": 30, "dividendos": 10, "recompras": 45, "opvs-ampliaciones": 10}  # días para seguir en la misma operación
DIAS_LISTADO = 365      # antigüedad máxima de lo que sale en las páginas de cada tipo
DIVIDENDOS_BME = RAIZ / "docs" / "dividendos" / "datos"   # datos del calendario de dividendos (fuente: BME)
# Páginas de elespeculador.com con el listado completo de cada tipo (shortcode espec_cnmv_listado) y texto del botón
# que lleva a ellas desde cada recuadro. Con BOTONES = False el botón no se publica (páginas aún en borrador).
BOTONES = True
LISTADOS = {
    "resultados": ("https://elespeculador.com/ibex-35/resultados/", "Ver todos los resultados"),
    "dividendos": ("https://elespeculador.com/ibex-35/dividendos/", "Ver todos los dividendos"),
    "recompras": ("https://elespeculador.com/ibex-35/recompras/", "Ver todas las recompras"),
    "opvs-ampliaciones": ("https://elespeculador.com/ibex-35/ampliaciones-y-opvs/", "Ver todas las ampliaciones y OPVs"),
}
INTRO = {
    "resultados": "Publicaciones de resultados y anuncios de la fecha en que se van a presentar, tal como las comunican a la CNMV las empresas del IBEX 35. Cuando una empresa anuncia la fecha y después publica las cuentas del mismo periodo, sale una sola línea con lo último.",
    "dividendos": "Anuncios de dividendo comunicados a la CNMV por las empresas del IBEX 35, incluidos los dividendos flexibles (ampliaciones liberadas).",
    "recompras": "Programas de recompra de acciones de las empresas del IBEX 35. Mientras dura un programa, la empresa informa cada semana de las compras que ha hecho: aquí sale una sola línea por programa, con el último informe y el número de comunicados.",
    "opvs-ampliaciones": "Ampliaciones de capital, colocaciones de acciones y salidas a bolsa comunicadas a la CNMV por las empresas del IBEX 35.",
}


class DatosRaros(Exception):
    """La respuesta no tiene la forma esperada: mejor parar que publicar basura."""


def ahora_madrid() -> datetime:
    return datetime.now(MADRID)


# --------------------------------------------------------------------------- lectura de los canales
def _plano(x: str) -> str:
    x = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", x or "", flags=re.S)
    x = re.sub(r"<br\s*/?>", "\n", x, flags=re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    x = html.unescape(x)
    return re.sub(r"[ \t\r\f\v]+", " ", x).strip()


def leer_canal(xml: str, canal: str) -> list[dict]:
    if "<rss" not in xml[:500].lower():
        raise DatosRaros(f"El canal {canal} no devuelve un RSS")
    filas = []
    for item in re.findall(r"<item>(.*?)</item>", xml, flags=re.S | re.I):
        def campo(nombre: str) -> str:
            m = re.search(rf"<{nombre}[^>]*>(.*?)</{nombre}>", item, flags=re.S | re.I)
            return m.group(1) if m else ""
        enlace = _plano(campo("link"))
        nreg = re.search(r"nreg=(\d+)", enlace)
        if not nreg:
            continue
        fecha = parsedate_to_datetime(_plano(campo("pubDate"))).astimezone(MADRID)
        lineas = [l.strip() for l in _plano(campo("description")).split("\n") if l.strip()]
        # primera línea: "17:54 19/10/2026 Programas de recompra de acciones, estabilización y autocartera"
        cabecera = re.sub(r"^\d{1,2}:\d{2}\s+\d{2}/\d{2}/\d{4}\s*", "", lineas[0]) if lineas else ""
        filas.append({"canal": canal, "nreg": int(nreg.group(1)), "fecha": fecha.strftime("%Y-%m-%dT%H:%M:%S"),
                      "emisor": _plano(campo("title")), "categoria": cabecera, "texto": " ".join(lineas[1:]),
                      "enlace": enlace})
    return filas


def _bajar(canal: str, url: str) -> str:
    ultimo = ""
    # Presupuesto acotado: 3 intentos de hasta 40 s más 30 s de espera por canal (unos 2,5 min), para que los dos
    # canales quepan con holgura en el tiempo máximo del flujo aunque la CNMV vaya lenta.
    for intento in range(3):
        if intento:
            time.sleep(10 * intento)
        try:
            r = requests.get(url, headers=CABECERAS, timeout=(10, 30))
        except requests.RequestException as e:
            ultimo = f"{type(e).__name__}: {e}"
            continue
        if r.status_code == 200:
            r.encoding = "utf-8"
            return r.text
        ultimo = f"HTTP {r.status_code}: {r.text[:200]!r}"
    raise DatosRaros(f"La CNMV no responde en el canal {canal} tras 3 intentos ({ultimo})")


def descargar() -> list[dict]:
    """Cada canal por separado: si uno falla se publica con el otro (la hora siguiente lo recupera, porque el
    canal guarda todo lo del día). Solo se para si fallan los dos."""
    filas, fallos = [], []
    for canal, url in CANALES.items():
        try:
            filas += leer_canal(_bajar(canal, url), canal)
        except DatosRaros as e:
            print(f"::warning::{e}")
            fallos.append(canal)
    if len(fallos) == len(CANALES):
        raise DatosRaros("No responde ningún canal de la CNMV")
    return filas


def acumular(nuevas: list[dict]) -> tuple[pd.DataFrame, int]:
    previo = pd.read_csv(HISTORICO, dtype=str, keep_default_na=False) if HISTORICO.exists() else pd.DataFrame(columns=COLUMNAS)
    n = pd.DataFrame(nuevas, columns=COLUMNAS).astype(str)
    d = pd.concat([previo, n], ignore_index=True).drop_duplicates(["canal", "nreg"], keep="first")
    d = d.sort_values(["fecha", "canal", "nreg"], ascending=False).reset_index(drop=True)
    return d[COLUMNAS], len(d) - len(previo)


# --------------------------------------------------------------------------- empresas del IBEX 35
def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", x)).strip()


def empresas_ibex(hoy: pd.Timestamp) -> pd.DataFrame:
    if hoy > pd.Timestamp(IBEX35_VALIDA_HASTA):
        raise DatosRaros(f"La composición del IBEX 35 venció el {IBEX35_VALIDA_HASTA}: actualiza dividendos/ibex35.csv y la fecha")
    miembros = set(pd.read_csv(IBEX35, dtype=str)["isin"])
    e = pd.read_csv(EMPRESAS, dtype=str)
    sin_alias = miembros - set(e["isin"])
    if sin_alias:
        print(f"::warning::Empresas del IBEX 35 sin alias en cnmv/empresas.csv: {sorted(sin_alias)}")
    return e[e["isin"].isin(miembros)].reset_index(drop=True)


def identificar(emisor: str, e: pd.DataFrame) -> pd.Series | None:
    n = _norm(emisor)
    for _, x in e.iterrows():
        if re.search(x["patron"], n):
            return x
    return None


# --------------------------------------------------------------------------- clasificación
def _t(x: str) -> str:
    return " " + _norm(x).lower() + " "


def _hay(texto: str, *frases: str) -> bool:
    return any(f in texto for f in frases)


def clasificar(categoria: str, texto: str) -> tuple[str, str] | None:
    """(caja, etiqueta) o None si no es de ninguno de los cuatro recuadros."""
    c, t = _t(categoria), _t(texto)
    todo = c + t
    if _hay(c, " contratos de liquidez "):
        return None
    if _hay(todo, " ampliacion de capital liberada ", " aumento de capital liberado ", " dividendo flexible ",
            " retribucion flexible ", " scrip ", " derechos de asignacion gratuita "):
        return "dividendos", "Dividendo flexible"
    if _hay(todo, " dividendo ", " dividendos ", " retribucion al accionista ", " pago a cuenta ",
            " devolucion de prima ", " distribucion de prima "):
        return "dividendos", "Dividendo"
    if _hay(todo, " estabilizacion ") and _hay(todo, " oferta ", " colocacion ", " opv "):
        return "opvs-ampliaciones", "Colocación"
    if _hay(todo, " recompra ", " autocartera ") or (_hay(t, " acciones propias ") and _hay(t, " adquisicion ", " compra ", " bloque ")):
        return "recompras", "Programa de recompra"
    valores_deuda = _hay(todo, " bonos ", " obligaciones ", " pagares ", " notas ", " warrants ", " turbos ",
                         " certificados ", " renta fija ", " cedulas ")
    if not valores_deuda:
        if _hay(todo, " oferta publica de venta ", " opv ", " salida a bolsa ", " oferta publica de suscripcion "):
            return "opvs-ampliaciones", "OPV"
        if _hay(todo, " ampliacion de capital ", " aumento de capital ", " nuevas acciones ", " emision de acciones "):
            return "opvs-ampliaciones", "Ampliación de capital"
        if _hay(todo, " colocacion acelerada ", " accelerated bookbuild ", " colocacion privada ", " colocacion de acciones "):
            return "opvs-ampliaciones", "Colocación"
    if _hay(todo, " junta ") and not _hay(todo, " resultados del ", " resultados de la sociedad "):
        return None
    if _hay(t, " resultados ", " resultado ") and _hay(t, " fecha ", " calendario ", " presentara ", " publicara ") \
            and _hay(t, " publicacion ", " presentacion ", " calendario ", " presentara ", " publicara "):
        return "resultados", "Fecha de resultados"
    # «Aena anuncia la celebración de la presentación de resultados…», «Anuncio webcast seguimiento de la actividad 9M»
    trimestral = r"\b(trimestre|trimestral|semestre|semestral|nueve meses|9m|[1-4]t(\d\d)?|q[1-4]|[12]s(\d\d)?|h[12])\b"
    if re.search(r"\b(anuncia|anuncio|convoca|convocatoria|celebracion|webcast)\b", t) and \
            (_hay(t, " resultados ") or re.search(trimestral, t)):
        return "resultados", "Fecha de resultados"
    if _hay(todo, " resultados ", " cuentas ", " informe financiero ", " informacion financiera ", " beneficio ") and re.search(
            r"\b(trimestre|trimestral|semestre|semestral|ejercicio|anual|anuales|nueve meses|9m|[1-4]t(\d\d)?|q[1-4]|[12]s(\d\d)?|h[12]|situacion financiera)\b", t):
        return "resultados", "Resultados"
    return None


PERIODOS = [(r"\b(primer|1er) trimestre\b|\b1t(\d\d)?\b|\bq1\b", "1T"), (r"\bsegundo trimestre\b|\b2t(\d\d)?\b|\bq2\b", "2T"),
            (r"\b(tercer|3er) trimestre\b|\b3t(\d\d)?\b|\bq3\b|\bnueve meses\b|\b9m\b", "3T"), (r"\bcuarto trimestre\b|\b4t(\d\d)?\b|\bq4\b", "4T"),
            (r"\b(primer )?semestre\b|\b1s(\d\d)?\b|\bh1\b", "1S"), (r"\b(ejercicio|anuales?|anual)\b", "año")]


def periodo(texto: str, fecha: str) -> str:
    t = _norm(texto).lower()
    anio = re.search(r"\b(20\d\d)\b", t)
    for patron, p in PERIODOS:
        m = re.search(patron, t)
        if m:
            corto = re.search(r"[1-4][ts](\d\d)\b", m.group(0))
            return f"{p} {anio.group(1) if anio else ('20' + corto.group(1) if corto else fecha[:4])}"
    return ""


def agrupar(d: pd.DataFrame) -> pd.DataFrame:
    """Asigna a cada comunicado del IBEX 35 su operación (grupo)."""
    d = d.sort_values(["fecha", "canal", "nreg"]).reset_index(drop=True)
    abiertos: dict[tuple, dict] = {}
    grupo = []
    for x in d.itertuples():
        f = pd.Timestamp(x.fecha)
        clave = (x.isin, x.caja, x.periodo if x.caja == "resultados" else "")
        g = abiertos.get(clave)
        if g is None or (f - g["ultima"]).days > VENTANA[x.caja]:
            g = {"id": f"{x.caja}-{x.isin}-{x.nreg}", "ultima": f}
            abiertos[clave] = g
        g["ultima"] = f
        grupo.append(g["id"])
    d["grupo"] = grupo
    return d.sort_values(["fecha", "canal", "nreg"], ascending=False).reset_index(drop=True)


def clasificados(h: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for x in h.itertuples():
        emp = identificar(x.emisor, e)
        if emp is None:
            continue
        c = clasificar(x.categoria, x.texto)
        if c is None:
            continue
        filas.append({**x._asdict(), "isin": emp["isin"], "empresa": emp["nombre"], "ficha": emp["ficha"], "caja": c[0],
                      "etiqueta": c[1], "periodo": periodo(x.texto, x.fecha) if c[0] == "resultados" else ""})
    cols = COLUMNAS + ["isin", "empresa", "ficha", "caja", "etiqueta", "periodo", "grupo"]
    if not filas:
        return pd.DataFrame(columns=cols)
    d = pd.DataFrame(filas).drop(columns=["Index"])
    return agrupar(d)[cols]


# --------------------------------------------------------------------------- salida
def _e(x) -> str:
    return html.escape(str(x)).replace("$", "&#36;")


def _f(fecha: str) -> str:
    return pd.Timestamp(fecha).strftime("%d/%m/%Y")


def _corto(t: str, n: int = 190) -> str:
    t = t.strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def entradas(c: pd.DataFrame, caja: str, hoy: pd.Timestamp, dias: int = DIAS_CAJA) -> list[dict]:
    x = c[(c["caja"] == caja) & (pd.to_datetime(c["fecha"]) >= hoy - pd.Timedelta(days=dias))]
    out = []
    for gid, g in x.groupby("grupo", sort=False):
        g = g.sort_values("fecha", ascending=False)
        ult = g.iloc[0]
        etiqueta = ult.etiqueta
        if caja == "resultados":
            publicado = g[g["etiqueta"] == "Resultados"]
            if not publicado.empty:
                ult, etiqueta = publicado.iloc[0], "Resultados"
            if ult.periodo:
                etiqueta += f" {ult.periodo}"
        out.append({"grupo": gid, "empresa": ult.empresa, "ficha": ult.ficha, "fecha": g.iloc[0].fecha,
                    "etiqueta": etiqueta, "texto": ult.texto or ult.categoria, "enlace": ult.enlace, "n": len(g)})
    out.sort(key=lambda r: r["fecha"], reverse=True)
    return out


def articulo(r: dict) -> str:
    meta = f"{_f(r['fecha'])} · {r['etiqueta']}" + (f" · {r['n']} comunicados" if r["n"] > 1 else "")
    return (f'<article class="efsec-item">'
            f'<h4 class="efsec-item-title"><a href="{FICHAS}{r["ficha"]}/">{_e(r["empresa"])}</a></h4>'
            f'<div class="efsec-item-meta">{_e(meta)}</div>'
            f'<p class="efsec-item-excerpt">{_e(_corto(r["texto"]))}</p>'
            f'<a class="efsec-item-link" href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">Ver el comunicado en la CNMV</a>'
            f'</article>')


def vacio(titulo: str, inicio: pd.Timestamp, hoy: pd.Timestamp) -> str:
    t = titulo if titulo.startswith("OPV") else titulo.lower()
    if hoy - inicio >= pd.Timedelta(days=DIAS_CAJA):
        return f"Ninguna empresa del IBEX 35 ha comunicado a la CNMV {t} en los últimos {DIAS_CAJA} días."
    return f"Sin comunicados de {t} de empresas del IBEX 35 desde el {inicio.strftime('%d/%m/%Y')}, cuando empieza este registro."


def cajas_html(c: pd.DataFrame, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> str:
    bloques = []
    for clave, titulo, desc in CAJAS:
        es = entradas(c, clave, hoy)[:POR_CAJA]
        cuerpo = "\n".join(articulo(r) for r in es) or f'<p class="efsec-item-excerpt">{_e(vacio(titulo, inicio, hoy))}</p>'
        if BOTONES:
            url, texto = LISTADOS[clave]
            cuerpo += f'\n<p class="espec-ver-todo"><a class="efsec-item-link" href="{url}">{_e(texto)}</a></p>'
        bloques.append(f'<div data-caja="{clave}" data-desc="{_e(desc)}">\n{cuerpo}\n</div>')
    return f"<!-- cnmv:inicio {sello} -->\n" + "\n".join(bloques) + "\n<!-- cnmv:fin -->\n"


def navegacion(actual: str) -> str:
    enlaces = []
    for clave, titulo, _ in CAJAS:
        if clave == actual:
            enlaces.append(f"<strong>{_e(titulo)}</strong>")
        else:
            enlaces.append(f'<a href="{LISTADOS[clave][0]}">{_e(titulo)}</a>')
    return ('<p class="espec-cnmv-nav">' + " · ".join(enlaces) +
            ' · <a href="https://elespeculador.com/ibex-35/">Volver al IBEX 35</a></p>')


def _euros(x: float, moneda: str) -> str:
    if x is None or pd.isna(x):
        return "—"
    t = f"{x:.4f}".rstrip("0")
    entero, _, dec = t.partition(".")
    return f"{entero},{dec.ljust(2, '0')} {'€' if moneda == 'EUR' else moneda}"


def _pct(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:.2f}".replace(".", ",") + " %"


def dividendos_bme(e: pd.DataFrame, hoy: pd.Timestamp) -> str:
    """Próximos dividendos y lo pagado en doce meses por las empresas del IBEX 35, con los datos de BME que ya
    publica el calendario de dividendos. Si esos ficheros no están, la página sale solo con los comunicados."""
    try:
        prox = pd.read_csv(DIVIDENDOS_BME / "proximos.csv", dtype={"isin": str})
        rent = pd.read_csv(DIVIDENDOS_BME / "rentabilidad.csv", dtype={"isin": str})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return ""
    emp = e.set_index("isin")
    prox = prox[prox["isin"].isin(emp.index) & (pd.to_datetime(prox["fecha_ex"]) >= hoy)].sort_values(["fecha_ex", "empresa"])
    rent = rent[rent["isin"].isin(emp.index)].sort_values("rentabilidad_ordinaria_pct", ascending=False)

    def celda_emp(isin: str) -> str:
        x = emp.loc[isin]
        return f'<a href="{FICHAS}{x["ficha"]}/">{_e(x["nombre"])}</a>'

    def tipo(r) -> str:
        t = "Flexible" if str(r.flexible) == "True" else ("Extraordinario" if str(r.extraordinario) == "True" else "Ordinario")
        return f"{t} ({r.concepto})" if isinstance(r.concepto, str) and r.concepto else t

    partes = []
    filas = "\n".join(
        f'<tr data-empresa="{_e(emp.loc[r.isin]["nombre"])}"><td>{_f(r.fecha_ex)}</td><td>{celda_emp(r.isin)}</td>'
        f'<td>{_euros(r.bruto, r.moneda)}</td><td>{_e(tipo(r))}</td><td>{_f(r.fecha_pago) if isinstance(r.fecha_pago, str) else "—"}</td></tr>'
        for r in prox.itertuples())
    partes.append('<h2>Próximos dividendos del IBEX 35</h2>\n'
                  '<figure class="wp-block-table espec-bme-tabla"><table><thead><tr><th>Fecha ex</th><th>Empresa</th>'
                  '<th>Importe bruto</th><th>Tipo</th><th>Fecha de pago</th></tr></thead><tbody>\n'
                  + (filas or '<tr><td colspan="5">Ninguna empresa del IBEX 35 tiene ahora mismo un dividendo anunciado con fecha ex por delante.</td></tr>')
                  + '\n</tbody></table></figure>')
    if not rent.empty:
        filas = "\n".join(
            f'<tr data-empresa="{_e(emp.loc[r.isin]["nombre"])}"><td>{celda_emp(r.isin)}</td><td>{int(r.pagos)}</td>'
            f'<td>{_euros(r.bruto_ordinario, r.moneda)}</td><td>{_pct(r.rentabilidad_ordinaria_pct)}</td></tr>'
            for r in rent.itertuples())
        partes.append('<h2>Lo que han pagado en los últimos doce meses</h2>\n'
                      '<p class="espec-cnmv-intro">Dividendo ordinario bruto por acción con fecha ex en los últimos doce meses y su rentabilidad sobre el último cierre. Ordenado de mayor a menor rentabilidad.</p>\n'
                      '<figure class="wp-block-table espec-bme-tabla"><table><thead><tr><th>Empresa</th><th>Pagos</th>'
                      '<th>Dividendo ordinario</th><th>Rentabilidad</th></tr></thead><tbody>\n' + filas + '\n</tbody></table></figure>')
    return "\n".join(partes) + '\n<p class="espec-cnmv-pie">Fechas, importes y rentabilidades: El Especulador, a partir de datos de BME.</p>\n'


def listado_html(c: pd.DataFrame, clave: str, titulo: str, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp,
                 e: pd.DataFrame | None = None) -> str:
    """Listado completo de un tipo para su página de elespeculador.com: tabla sin imágenes; cada fila lleva la
    empresa en data-empresa para que la página pueda filtrar por empresa."""
    es = entradas(c, clave, hoy, DIAS_LISTADO)
    filas = "\n".join(
        f'<tr data-empresa="{_e(r["empresa"])}"><td>{_f(r["fecha"])}</td>'
        f'<td><a href="{FICHAS}{r["ficha"]}/">{_e(r["empresa"])}</a></td><td>{_e(r["etiqueta"])}</td>'
        f'<td>{_e(_corto(r["texto"], 300))}</td>'
        f'<td><a href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">CNMV</a>'
        f'{" (" + str(r["n"]) + " comunicados)" if r["n"] > 1 else ""}</td></tr>' for r in es)
    if not filas:
        filas = f'<tr><td colspan="5">{_e(vacio(titulo, inicio, hoy))}</td></tr>'
    desde = max(inicio, hoy - pd.Timedelta(days=DIAS_LISTADO))
    bme = dividendos_bme(e, hoy) if clave == "dividendos" and e is not None else ""
    return (f"<!-- cnmv-listado:inicio {clave} {sello} -->\n"
            f"{navegacion(clave)}\n"
            f"{bme}"
            f'{"<h2>Anuncios de dividendo comunicados a la CNMV</h2>" if bme else ""}\n'
            f'<p class="espec-cnmv-intro">{_e(INTRO[clave])}</p>\n'
            f'<figure class="wp-block-table espec-cnmv-tabla"><table><thead><tr><th>Fecha</th><th>Empresa</th><th>Tipo</th>'
            f'<th>Comunicado</th><th>Fuente</th></tr></thead><tbody>\n{filas}\n</tbody></table></figure>\n'
            f'<p class="espec-cnmv-pie">Fuente: CNMV. Comunicados desde el {desde.strftime("%d/%m/%Y")}; se actualiza cada hora '
            f'en días hábiles (última actualización: {_e(sello[8:10] + "/" + sello[5:7] + "/" + sello[:4] + " a las " + sello[11:])}). '
            f'La clasificación es automática: el texto oficial de cada comunicado es el que publica la CNMV.</p>\n'
            f"<!-- cnmv-listado:fin -->\n")


# --------------------------------------------------------------------------- bloque de la ficha de cada empresa
NOMBRE_CAJA = {"resultados": "Resultados", "dividendos": "Dividendos", "recompras": "Recompra",
               "opvs-ampliaciones": "Ampliación u OPV"}
FICHA_COMUNICADOS = 8   # líneas de comunicados en cada ficha


def _comunicados_empresa(c: pd.DataFrame, isin: str, hoy: pd.Timestamp) -> list[dict]:
    x = c[c["isin"] == isin]
    out = []
    for clave, _, _ in CAJAS:
        for r in entradas(x, clave, hoy, DIAS_LISTADO):
            out.append({**r, "caja": clave})
    out.sort(key=lambda r: r["fecha"], reverse=True)
    return out


def ficha_html(c: pd.DataFrame, emp: pd.Series, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp,
               prox: pd.DataFrame | None, rent: pd.DataFrame | None, hist: pd.DataFrame | None) -> str:
    """Bloque para la ficha de una empresa en elespeculador.com/ibex35/<ficha>/: comunicados a la CNMV y
    dividendos, en listas sin imágenes con las mismas clases que el resto de la ficha (ef-card, ef-news, ef-note)."""
    nombre = emp["nombre"]
    lineas = []
    for r in _comunicados_empresa(c, emp["isin"], hoy)[:FICHA_COMUNICADOS]:
        tipo = r["etiqueta"] if r["caja"] == "resultados" else NOMBRE_CAJA[r["caja"]] if r["caja"] != "dividendos" else r["etiqueta"]
        extra = f" ({r['n']} comunicados)" if r["n"] > 1 else ""
        lineas.append(f'<li><time>{_f(r["fecha"])}</time><span><a href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">'
                      f'{_e(_corto(r["texto"], 150))}</a><br><small>{_e(tipo)}{_e(extra)}</small></span></li>')
    if lineas:
        lista = '<ul class="ef-news">\n' + "\n".join(lineas) + "\n</ul>"
    else:
        cuando = ("en los últimos doce meses" if hoy - inicio >= pd.Timedelta(days=DIAS_LISTADO)
                  else f'desde el {inicio.strftime("%d/%m/%Y")}, cuando empieza este registro')
        lista = f'<p>{_e(nombre)} no ha comunicado a la CNMV resultados, dividendos, recompras ni ampliaciones {cuando}.</p>'
    enlaces = " · ".join(f'<a href="{LISTADOS[k][0]}">{_e(t)}</a>' for k, t, _ in CAJAS)
    bloques = [f'<div class="ef-card">\n<h2>Comunicados de {_e(nombre)} a la CNMV</h2>\n{lista}\n'
               f'<p class="ef-note">Resultados, dividendos, recompras y ampliaciones de los últimos doce meses. '
               f'Los comunicados de una misma operación salen en una línea. Todas las empresas del IBEX 35: {enlaces}.</p>\n</div>']

    div = []
    if prox is not None:
        p = prox[(prox["isin"] == emp["isin"]) & (pd.to_datetime(prox["fecha_ex"]) >= hoy)].sort_values("fecha_ex")
        for r in p.itertuples():
            tipo = "dividendo flexible" if str(r.flexible) == "True" else ("dividendo extraordinario" if str(r.extraordinario) == "True" else "dividendo")
            pago = f", se paga el {_f(r.fecha_pago)}" if isinstance(r.fecha_pago, str) and r.fecha_pago else ""
            div.append(f'<li><time>{_f(r.fecha_ex)}</time><span><strong>Próximo:</strong> {_euros(r.bruto, r.moneda)} brutos por acción '
                       f'({_e(tipo)}{" " + _e(r.concepto) if isinstance(r.concepto, str) and r.concepto else ""}). '
                       f'Fecha ex el {_f(r.fecha_ex)}{pago}.</span></li>')
    if hist is not None:
        hh = hist[(hist["isin"] == emp["isin"]) & (pd.to_datetime(hist["fecha_ex"]) < hoy)].sort_values("fecha_ex", ascending=False).head(6)
        for r in hh.itertuples():
            tipo = "flexible" if str(r.flexible) == "True" else ("extraordinario" if str(r.extraordinario) == "True" else "")
            conc = " · ".join(x for x in [r.concepto if isinstance(r.concepto, str) else "", tipo] if x)
            div.append(f'<li><time>{_f(r.fecha_ex)}</time><span>{_euros(r.bruto, r.moneda)} brutos por acción'
                       f'{" (" + _e(conc) + ")" if conc else ""}</span></li>')
    resumen = ""
    if rent is not None:
        rr = rent[rent["isin"] == emp["isin"]]
        if not rr.empty:
            r = rr.iloc[0]
            veces = "un pago" if int(r.pagos) == 1 else f"{int(r.pagos)} pagos"
            resumen = (f"<p>En los últimos doce meses ha repartido {_euros(r.bruto_ordinario, r.moneda)} brutos por acción "
                       f"de dividendo ordinario en {veces}, un {_pct(r.rentabilidad_ordinaria_pct)} sobre el cierre del {_f(r.fecha_cierre)}.</p>")
    if div or resumen:
        bloques.append(f'<div class="ef-card">\n<h2>Dividendos de {_e(nombre)}</h2>\n{resumen}\n'
                       + ('<ul class="ef-news">\n' + "\n".join(div) + "\n</ul>\n" if div else "")
                       + f'<p class="ef-note">Fechas e importes: El Especulador, a partir de datos de BME. '
                         f'<a href="{LISTADOS["dividendos"][0]}">Dividendos de todo el IBEX 35</a>.</p>\n</div>')
    return (f"<!-- ficha-cnmv:inicio {emp['ficha']} {sello} -->\n" + "\n".join(bloques) + "\n<!-- ficha-cnmv:fin -->\n")


def fichas(c: pd.DataFrame, e: pd.DataFrame, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> int:
    def leer(n):
        try:
            return pd.read_csv(DIVIDENDOS_BME / n, dtype={"isin": str})
        except (FileNotFoundError, pd.errors.EmptyDataError):
            return None
    prox, rent, hist = leer("proximos.csv"), leer("rentabilidad.csv"), leer("dividendos.csv")
    carpeta = SALIDA / "empresas"
    carpeta.mkdir(parents=True, exist_ok=True)
    for emp in e.to_dict("records"):
        frag = ficha_html(c, pd.Series(emp), hoy, sello, inicio, prox, rent, hist)
        assert "$" not in frag
        (carpeta / f"{emp['ficha']}.html").write_text(frag, encoding="utf-8")
    return len(e)


def pagina(c: pd.DataFrame, hoy: pd.Timestamp, sello: str) -> str:
    secciones = []
    for clave, titulo, desc in CAJAS:
        es = entradas(c, clave, hoy)
        filas = "\n".join(
            f"<tr><td>{_f(r['fecha'])}</td><td><a href=\"{FICHAS}{r['ficha']}/\">{_e(r['empresa'])}</a></td><td>{_e(r['etiqueta'])}</td>"
            f"<td>{_e(_corto(r['texto'], 260))}</td><td><a href=\"{_e(r['enlace'])}\" rel=\"nofollow\">CNMV</a>"
            f"{' (' + str(r['n']) + ')' if r['n'] > 1 else ''}</td></tr>" for r in es) or \
            '<tr><td colspan="5">Sin comunicados en el periodo.</td></tr>'
        secciones.append(f"<h2>{titulo}</h2><p>{_e(desc)}</p><figure><table><thead><tr><th>Fecha</th><th>Empresa</th><th>Tipo</th>"
                         f"<th>Comunicado</th><th>Fuente</th></tr></thead><tbody>\n{filas}\n</tbody></table></figure>")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comunicados a la CNMV de las empresas del IBEX 35 | El Especulador</title>
<meta name="description" content="Resultados, dividendos, recompras y ampliaciones comunicados a la CNMV por las empresas del IBEX 35 en los últimos {DIAS_CAJA} días.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1100px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.88rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;vertical-align:top}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style>
</head><body>
<h1>Comunicados a la CNMV de las empresas del IBEX 35</h1>
<p><strong>Actualizado el {_e(sello.replace('T', ' a las '))}.</strong> Los comunicados de una misma operación (por ejemplo, los informes semanales de un programa de recompra) se agrupan en una sola fila, con el último comunicado y, entre paréntesis, cuántos hay.</p>
{"".join(secciones)}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/ibex35.csv">comunicados del IBEX 35 clasificados</a> · <a href="datos/comunicados.csv">todos los comunicados leídos</a> · <a href="datos/ultima.json">JSON</a>. Licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>, citando «El Especulador, a partir de datos de la CNMV».</p>
<p class="pie">Fuente: CNMV, canales de información privilegiada y de otra información relevante. La clasificación es automática; el texto oficial de cada comunicado es el de la CNMV. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
"""


def _huella_bme() -> str:
    h = hashlib.md5()
    for n in ("proximos.csv", "rentabilidad.csv"):
        f = DIVIDENDOS_BME / n
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()


def escribir(h: pd.DataFrame, c: pd.DataFrame, e: pd.DataFrame, nuevos: int, forzar: bool) -> bool:
    """Reescribe si hay comunicados nuevos, si ha cambiado el día (los recuadros y los próximos dividendos dependen
    de la fecha) o si el calendario de dividendos ha cambiado sus datos."""
    ahora = ahora_madrid()
    hoy = pd.Timestamp(ahora.date())
    sello = ahora.strftime("%Y-%m-%dT%H:%M")
    huella = _huella_bme()
    previo = json.loads((DATOS / "ultima.json").read_text(encoding="utf-8")) if (DATOS / "ultima.json").exists() else {}
    if (nuevos == 0 and not forzar and (SALIDA / "cajas.html").exists() and previo.get("bme") == huella
            and str(previo.get("actualizado", ""))[:10] == sello[:10]):
        return False
    DATOS.mkdir(parents=True, exist_ok=True)
    h.to_csv(HISTORICO, index=False)
    c.to_csv(DATOS / "ibex35.csv", index=False)
    inicio = pd.Timestamp(pd.Timestamp(h["fecha"].min()).date())
    cajas = cajas_html(c, hoy, sello, inicio)
    for clave, titulo, _ in CAJAS:
        lst = listado_html(c, clave, titulo, hoy, sello, inicio, e)
        assert "$" not in lst
        (SALIDA / f"listado-{clave}.html").write_text(lst, encoding="utf-8")
    assert "$" not in cajas
    (SALIDA / "cajas.html").write_text(cajas, encoding="utf-8")
    fichas(c, e, hoy, sello, inicio)
    (SALIDA / "index.html").write_text(pagina(c, hoy, sello), encoding="utf-8")
    (DATOS / "ultima.json").write_text(json.dumps({
        "actualizado": sello, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comunicados_leidos": int(len(h)), "comunicados_ibex35_clasificados": int(len(c)),
        "por_recuadro": {k: len(entradas(c, k, hoy)) for k, _, _ in CAJAS},
        "fuente": "CNMV, RSS de información privilegiada y otra información relevante", "licencia": "CC BY 4.0 · El Especulador",
        "bme": huella,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", nargs="+", help="ficheros RSS ya descargados (el nombre debe contener IP u OIR)")
    ap.add_argument("--forzar", action="store_true", help="reescribir aunque no haya comunicados nuevos")
    args = ap.parse_args()
    if args.local:
        filas = []
        for f in args.local:
            canal = "IP" if "IP" in Path(f).name.upper().replace("OIR", "") else "OIR"
            filas += leer_canal(Path(f).read_text(encoding="utf-8"), canal)
    else:
        filas = descargar()
    h, nuevos = acumular(filas)
    e = empresas_ibex(pd.Timestamp(ahora_madrid().date()))
    c = clasificados(h, e)
    if escribir(h, c, e, nuevos, args.forzar):
        print(f"{nuevos} comunicados nuevos; {len(c)} del IBEX 35 clasificados en el histórico.")
    else:
        print(f"Sin comunicados nuevos en la CNMV ({len(h)} en el histórico): no se toca nada.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
    except Exception as e:  # que el motivo quede en el resumen de la ejecución
        print(f"::error::{type(e).__name__}: {e}")
        raise
