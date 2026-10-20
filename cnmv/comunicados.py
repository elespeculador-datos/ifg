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
    for intento in range(4):
        if intento:
            time.sleep(20 * intento)
        try:
            r = requests.get(url, headers=CABECERAS, timeout=(15, 45))
        except requests.RequestException as e:
            ultimo = f"{type(e).__name__}: {e}"
            continue
        if r.status_code == 200:
            r.encoding = "utf-8"
            return r.text
        ultimo = f"HTTP {r.status_code}: {r.text[:200]!r}"
    raise DatosRaros(f"La CNMV no responde en el canal {canal} tras 4 intentos ({ultimo})")


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
    if _hay(todo, " resultados ", " cuentas ", " informe financiero ", " beneficio ") and re.search(
            r"\b(trimestre|trimestral|semestre|semestral|ejercicio|anual|anuales|nueve meses|9m|[1-4]t(\d\d)?|[12]s(\d\d)?|situacion financiera)\b", todo):
        return "resultados", "Resultados"
    return None


PERIODOS = [(r"\b(primer|1er) trimestre\b|\b1t(\d\d)?\b", "1T"), (r"\bsegundo trimestre\b|\b2t(\d\d)?\b", "2T"),
            (r"\b(tercer|3er) trimestre\b|\b3t(\d\d)?\b|\bnueve meses\b|\b9m\b", "3T"), (r"\bcuarto trimestre\b|\b4t(\d\d)?\b", "4T"),
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


def entradas(c: pd.DataFrame, caja: str, hoy: pd.Timestamp) -> list[dict]:
    x = c[(c["caja"] == caja) & (pd.to_datetime(c["fecha"]) >= hoy - pd.Timedelta(days=DIAS_CAJA))]
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


def cajas_html(c: pd.DataFrame, hoy: pd.Timestamp, sello: str) -> str:
    bloques = []
    for clave, titulo, desc in CAJAS:
        es = entradas(c, clave, hoy)[:POR_CAJA]
        cuerpo = "\n".join(articulo(r) for r in es) or \
            f'<p class="efsec-item-excerpt">Ninguna empresa del IBEX 35 ha comunicado a la CNMV {titulo.lower()} en los últimos {DIAS_CAJA} días.</p>'
        bloques.append(f'<div data-caja="{clave}" data-desc="{_e(desc)}">\n{cuerpo}\n</div>')
    return f"<!-- cnmv:inicio {sello} -->\n" + "\n".join(bloques) + "\n<!-- cnmv:fin -->\n"


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


def escribir(h: pd.DataFrame, c: pd.DataFrame, nuevos: int, forzar: bool) -> bool:
    if nuevos == 0 and not forzar and (SALIDA / "cajas.html").exists():
        return False
    ahora = ahora_madrid()
    hoy = pd.Timestamp(ahora.date())
    sello = ahora.strftime("%Y-%m-%dT%H:%M")
    DATOS.mkdir(parents=True, exist_ok=True)
    h.to_csv(HISTORICO, index=False)
    c.to_csv(DATOS / "ibex35.csv", index=False)
    cajas = cajas_html(c, hoy, sello)
    assert "$" not in cajas
    (SALIDA / "cajas.html").write_text(cajas, encoding="utf-8")
    (SALIDA / "index.html").write_text(pagina(c, hoy, sello), encoding="utf-8")
    (DATOS / "ultima.json").write_text(json.dumps({
        "actualizado": sello, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comunicados_leidos": int(len(h)), "comunicados_ibex35_clasificados": int(len(c)),
        "por_recuadro": {k: len(entradas(c, k, hoy)) for k, _, _ in CAJAS},
        "fuente": "CNMV, RSS de información privilegiada y otra información relevante", "licencia": "CC BY 4.0 · El Especulador",
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
    if escribir(h, c, nuevos, args.forzar):
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
