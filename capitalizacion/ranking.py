"""Las empresas más grandes de la bolsa española y las que más suben y bajan en el año.

Fuente: lista de cotizadas del mercado continuo (SIBE) de BME, con la capitalización
y la variación en el año de cada valor, más la ficha y el histórico de precios de cada
uno. Una fila por empresa: si tiene varias clases de acciones en bolsa, se suman
(Grifols: la clase B no viene en la lista de cotizadas y se toma de su ficha).

Comprobaciones antes de publicar, porque una tabla de «las que más bajan» no puede
llevar un valor suspendido ni una salida a bolsa de este año comparada con nada:
- valores sin cotizaciones en las dos últimas semanas: se marcan y no entran en las
  listas de las que más suben y bajan;
- valores que salieron a bolsa este año: se marcan y tampoco entran;
- la variación del año de BME se contrasta con la que sale del histórico de precios
  ajustados; si se apartan más de 2 puntos, el valor sale de esas listas y el flujo avisa;
- las listas de las que más suben y bajan solo incluyen empresas de más de 100 millones,
  para que no las copen valores minúsculos con muy poca negociación.

PREPARADO, SIN PUBLICAR: espera a que BME confirme si su licencia de datos cubre
mostrarlo en una web gratuita. Sin flujo de GitHub hasta entonces.

Uso:
  python capitalizacion/ranking.py --salida DIR
  python capitalizacion/ranking.py --salida DIR --local cotizadas.json --historial historial.json --fecha AAAA-MM-DD
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nombres import NOMBRES  # noqa: E402

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/",
             "Origin": "https://www.bolsasymercados.es"}
PAGINA_WP = "https://elespeculador.com/empresas-mas-grandes-bolsa-espanola/"
METODOLOGIA = PAGINA_WP + "#como-se-calcula"
PAGES = "https://elespeculador-datos.github.io/ifg/capitalizacion/"
TOP_VARIACION = 10
MIN_CAP_LISTAS = 100e6        # euros: mínimo para entrar en las listas de las que más suben y bajan
DIAS_SIN_COTIZAR = 14         # días naturales sin cotizaciones para marcar un valor como «sin cotizar»
TOLERANCIA_VARIACION = 0.02   # diferencia máxima entre la variación de BME y la calculada con precios ajustados
# Clases que cotizan en el mercado continuo pero no vienen en la lista de cotizadas de BME: ISIN -> companyKey de la empresa
CLASES_FUERA_DE_LISTA = {"ES0171996095": "71996"}  # Grifols, clase B
NOTAS_CLASE = {"ES0171996087": "clases A y B", "ES0105777017": "solo la clase B, la única que cotiza"}
NOTAS_SEDE = {"NL0015001FS8": "Sede en Países Bajos desde 2023"}


class DatosRaros(Exception):
    pass


def _num(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + _num(abs(x), 1) + " %"


def _f(d: str) -> str:
    """AAAAMMDD o AAAA-MM-DD -> DD/MM/AAAA."""
    d = d.replace("-", "")
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}"


SIN_NOMBRE: list[str] = []
AVISOS: list[str] = []


def nombre(isin: str, nombre_bme: str) -> str:
    if isin in NOMBRES:
        return NOMBRES[isin]
    SIN_NOMBRE.append(f"{isin} {nombre_bme}")
    return " ".join(w if (len(w) <= 3 and w.isupper() and w not in {"DE", "DEL", "LA", "EL", "Y"}) else w.capitalize()
                    for w in nombre_bme.split())


# --------------------------------------------------------------------------- descargas
def _get(ruta: str, params: dict, intentos: int = 3) -> dict | None:
    for i in range(intentos):
        try:
            r = requests.get(API + ruta, params=params, headers=CABECERAS, timeout=60)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (i + 1))
    return None


def descargar() -> list[dict]:
    j = _get("ListedCompanies", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0})
    if j is None:
        raise DatosRaros("BME no devuelve la lista de cotizadas")
    if j.get("hasMoreResults"):
        raise DatosRaros("BME pagina la lista de cotizadas")
    return j.get("data", [])


def fichas_fuera_de_lista() -> dict[str, dict]:
    out = {}
    for isin in CLASES_FUERA_DE_LISTA:
        j = _get("ShareDetailsInfo", {"isin": isin})
        if not j or not j.get("capitalisation"):
            raise DatosRaros(f"BME no devuelve la ficha de {isin}")
        out[isin] = j
    return out


def fecha_cierre() -> str | None:
    """Fecha del último cierre (AAAA-MM-DD), según la ficha de un valor muy líquido (Santander)."""
    j = _get("ShareDetailsInfo", {"isin": "ES0113900J37"})
    d = (j or {}).get("lastClosePriceDate")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d else None


def historiales(isins: list[str], anio: int) -> dict[str, list | None]:
    """Cierres desde diciembre del año anterior de cada valor ({isin: [[fecha, cierre], ...]} o None si falla)."""
    out = {}
    for isin in isins:
        j = _get("HistoricalSharesPrices", {"isin": isin, "from": f"{anio - 1}1201", "to": f"{anio}1231", "page": 0, "pageSize": 0})
        out[isin] = None if j is None else [[f["date"], f["close"]] for f in j.get("data", []) if f.get("close")]
        time.sleep(0.3)
    return out


# --------------------------------------------------------------------------- cálculo
def preparar(filas: list[dict], extra: dict[str, dict]) -> list[dict]:
    if len(filas) < 100:
        raise DatosRaros(f"BME solo devuelve {len(filas)} cotizadas")
    clases = [(f["companyKey"], f["isin"], f.get("shareName") or f.get("name") or "", f.get("capitalisation"),
               f.get("annualDifference"), "IBEX 35" in (f.get("indices") or "")) for f in filas]
    for isin, j in extra.items():
        clases.append((CLASES_FUERA_DE_LISTA[isin], isin, j.get("name") or isin, j.get("capitalisation"), None, False))
    empresas: dict[str, dict] = {}
    for clave, isin, nom, cap, var, ibex in clases:
        if not cap or cap <= 0:
            continue
        e = empresas.setdefault(clave, {"isin": isin, "nombre": nombre(isin, nom), "capitalizacion": 0.0, "variacion_anio_pct": None,
                                        "ibex35": False, "espanola": isin.startswith("ES"), "clases": [], "_mayor": 0.0})
        e["capitalizacion"] += float(cap)
        e["clases"].append(isin)
        if float(cap) > e["_mayor"]:  # la variación del año y el nombre, los de la clase con más capitalización
            e["_mayor"] = float(cap)
            e.update(isin=isin, nombre=nombre(isin, nom), espanola=isin.startswith("ES"),
                     variacion_anio_pct=None if var is None else round(float(var) * 100, 2))
        e["ibex35"] = e["ibex35"] or ibex
    lista = sorted(empresas.values(), key=lambda e: -e["capitalizacion"])
    total = sum(e["capitalizacion"] for e in lista)
    n_ibex = sum(e["ibex35"] for e in lista)
    if total < 500e9 or n_ibex != 35:
        raise DatosRaros(f"Datos raros: capitalización total {total / 1e9:.0f} mil millones, {n_ibex} del IBEX")
    for i, e in enumerate(lista, 1):
        e["puesto"] = i
        e.pop("_mayor")
    for i, e in enumerate([e for e in lista if e["espanola"]], 1):
        e["puesto_espanolas"] = i
    return lista


def revisar(lista: list[dict], hist: dict[str, list | None], fecha: str) -> None:
    """Marca valores sin cotizar, salidas a bolsa del año y variaciones que no cuadran con el histórico."""
    anio = int(fecha[:4])
    limite = (date.fromisoformat(fecha) - timedelta(days=DIAS_SIN_COTIZAR)).strftime("%Y%m%d")
    fallos = [e["nombre"] for e in lista if hist.get(e["isin"]) is None]
    if len(fallos) > 10:
        raise DatosRaros(f"BME no devuelve el histórico de {len(fallos)} valores")
    for e in lista:
        e.update(ultima_sesion=None, sin_cotizar=False, en_bolsa_desde=None, variacion_ajustada_pct=None, en_listas=False)
        h = hist.get(e["isin"])
        if h is None:  # sin histórico: se muestra el dato de BME, pero no entra en las listas
            AVISOS.append(f"sin histórico de {e['nombre']}")
            continue
        previo = [c for d, c in h if d.startswith(str(anio - 1))]
        este = [(d, c) for d, c in h if d.startswith(str(anio))]
        e["ultima_sesion"] = este[-1][0] if este else None
        e["sin_cotizar"] = not este or este[-1][0] < limite
        if este and not previo:
            e["en_bolsa_desde"] = este[0][0]
        if previo and este:
            e["variacion_ajustada_pct"] = round((este[-1][1] / previo[-1] - 1) * 100, 2)
        v, va = e["variacion_anio_pct"], e["variacion_ajustada_pct"]
        cuadra = v is not None and va is not None and abs(v - va) <= TOLERANCIA_VARIACION * 100
        if v is not None and va is not None and not cuadra:
            AVISOS.append(f"{e['nombre']}: variación de BME {v} % y con precios ajustados {va} %")
        e["en_listas"] = cuadra and not e["sin_cotizar"] and not e["en_bolsa_desde"] and e["capitalizacion"] >= MIN_CAP_LISTAS


# --------------------------------------------------------------------------- texto
def nota(e: dict) -> str:
    partes = []
    if e["ibex35"]:
        partes.append("IBEX 35")
    if e["isin"] in NOTAS_CLASE:
        partes.append(NOTAS_CLASE[e["isin"]])
    if e["en_bolsa_desde"]:
        partes.append(f"en bolsa desde el {_f(e['en_bolsa_desde'])}")
    if e["sin_cotizar"]:
        partes.append(f"sin cotizar desde el {_f(e['ultima_sesion'])}" if e["ultima_sesion"] else "sin cotizaciones este año")
    return f" <small>({html.escape('; '.join(partes))})</small>" if partes else ""


def variacion(e: dict) -> str:
    if e["variacion_anio_pct"] is None or e["en_bolsa_desde"] or (e["sin_cotizar"] and not e["ultima_sesion"]):
        return "—"
    return _pct(e["variacion_anio_pct"])


def resumen(lista: list[dict], fecha: str) -> str:
    esp = [e for e in lista if e["espanola"]]
    ext = [e for e in lista if not e["espanola"]]
    total = sum(e["capitalizacion"] for e in esp)
    top5 = sum(e["capitalizacion"] for e in esp[:5])
    mas_100 = sum(1 for e in esp if e["capitalizacion"] >= 100e9)
    m = lambda e: _num(e["capitalizacion"] / 1e6)  # noqa: E731
    t = (f"Al cierre del {_f(fecha)}, la empresa española más grande de la bolsa es {html.escape(esp[0]['nombre'])}, que vale "
         f"{m(esp[0])} millones de euros, seguida de {html.escape(esp[1]['nombre'])} ({m(esp[1])} millones) y "
         f"{html.escape(esp[2]['nombre'])} ({m(esp[2])} millones). Las {len(esp)} empresas españolas de la lista de cotizadas del "
         f"mercado continuo suman {_num(total / 1e12, 2)} billones de euros; las cinco mayores, el {_num(top5 / total * 100, 1)} %")
    t += f", y {mas_100} superan los 100.000 millones." if mas_100 > 1 else "."
    if ext:
        x = ext[0]
        t += (f" De las extranjeras que cotizan aquí, la mayor es {html.escape(x['nombre'])} ({m(x)} millones), "
              f"que en una clasificación conjunta sería la {x['puesto']}.ª.")
    return f"<p>{t}</p>"


def fragmento(lista: list[dict], fecha: str) -> str:
    esp = [e for e in lista if e["espanola"]]
    ext = [e for e in lista if not e["espanola"]]
    anio = fecha[:4]
    millones = "Capitalización (millones de €)"

    def fila(e: dict) -> str:
        return (f"<tr><td>{e['puesto_espanolas']}</td><td>{html.escape(e['nombre'])}{nota(e)}</td>"
                f"<td>{_num(e['capitalizacion'] / 1e6)}</td><td>{variacion(e)}</td></tr>")

    def corta(es: list[dict]) -> str:
        return "\n".join(f"<tr><td>{html.escape(e['nombre'])}</td><td>{_pct(e['variacion_anio_pct'])}</td>"
                         f"<td>{_num(e['capitalizacion'] / 1e6)}</td></tr>" for e in es)

    def tabla(cab: list[str], cuerpo: str) -> str:
        return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab)
                + f"</tr></thead><tbody>\n{cuerpo}\n</tbody></table></figure>")

    validas = [e for e in esp if e["en_listas"]]
    suben = sorted(validas, key=lambda e: -e["variacion_anio_pct"])[:TOP_VARIACION]
    bajan = sorted(validas, key=lambda e: e["variacion_anio_pct"])[:TOP_VARIACION]
    ibex = [e for e in lista if e["ibex35"] and e["en_listas"]]
    ib_suben = sorted(ibex, key=lambda e: -e["variacion_anio_pct"])[:5]
    ib_bajan = sorted(ibex, key=lambda e: e["variacion_anio_pct"])[:5]
    cab_corta = ["Empresa", f"Variación en {anio}", millones]
    filtro = (f"<p>Empresas españolas de más de {_num(MIN_CAP_LISTAS / 1e6)} millones de euros, sin contar las que salieron a bolsa "
              f"en {anio} ni las que llevan más de dos semanas sin cotizar. Variación desde el último cierre de {int(anio) - 1}, "
              f"solo por precio.</p>")
    filas_ext = "\n".join(f"<tr><td>{html.escape(e['nombre'])}{' <small>(IBEX 35)</small>' if e['ibex35'] else ''}</td>"
                          f"<td>{_num(e['capitalizacion'] / 1e6)}</td><td>{html.escape(NOTAS_SEDE.get(e['isin'], 'Sede fuera de España'))}</td></tr>"
                          for e in ext)
    return (f"<!-- capitalizacion:inicio {fecha} -->\n"
            f"{resumen(lista, fecha)}\n"
            f"<h2>Las empresas españolas por capitalización</h2>\n"
            + tabla(["Puesto", "Empresa", millones, f"Variación en {anio}"], "\n".join(fila(e) for e in esp)) + "\n"
            f"<h2>Las que más suben en {anio}</h2>\n{filtro}\n" + tabla(cab_corta, corta(suben)) + "\n"
            f"<h2>Las que más bajan en {anio}</h2>\n" + tabla(cab_corta, corta(bajan)) + "\n"
            f"<h2>En el IBEX 35, las cinco que más suben y las cinco que más bajan en {anio}</h2>\n"
            + tabla(cab_corta, corta(ib_suben) + "\n" + corta(ib_bajan)) + "\n"
            f"<h2>Empresas extranjeras que cotizan en el mercado continuo</h2>\n"
            f"<p>No entran en la clasificación porque tienen la sede fuera de España, aunque cotizan en las bolsas españolas.</p>\n"
            + tabla(["Empresa", millones, "Nota"], filas_ext) + "\n"
            f'<p class="has-small-font-size">Datos al cierre del {_f(fecha)}. Fuente: BME, lista de cotizadas del mercado continuo, '
            f'ficha e histórico de precios de cada valor. Variación del año: solo precio, sin dividendos. '
            f'<a href="{METODOLOGIA}">Cómo se calcula</a>.</p>\n'
            f"<!-- capitalizacion:fin -->")


def ld_wp(fecha: str, anio: str) -> str:
    """Marcado Dataset (schema.org) en una sola línea, para la página de elespeculador.com."""
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Las empresas más grandes de la bolsa española por capitalización (El Especulador)",
        "description": "Clasificación diaria de las empresas españolas del mercado continuo por su valor en bolsa al cierre, con la variación "
                       "de cada una en el año, las que más suben y más bajan y las empresas extranjeras que cotizan en España, con datos de BME.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de BME", "isBasedOn": "https://www.bolsasymercados.es/",
        "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ("empresas", anio)],
    }, ensure_ascii=False) + "</script>"


def escribir(lista: list[dict], fecha: str, salida: Path) -> None:
    datos = salida / "datos"
    datos.mkdir(parents=True, exist_ok=True)
    campos = ["fecha", "puesto", "puesto_espanolas", "nombre", "isin", "clases", "capitalizacion", "variacion_anio_pct",
              "variacion_ajustada_pct", "ibex35", "espanola", "ultima_sesion", "sin_cotizar", "en_bolsa_desde"]
    for nombre_csv in ("empresas", fecha[:4]):  # el del año se reescribe cada día y queda como archivo al acabar el año
        with (datos / f"{nombre_csv}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            for e in lista:
                w.writerow({**{k: e.get(k, "") for k in campos}, "fecha": fecha, "clases": " ".join(e["clases"]),
                            "capitalizacion": round(e["capitalizacion"], 2)})
    esp = [e for e in lista if e["espanola"]]
    (datos / "ultima.json").write_text(json.dumps({
        "fecha": fecha, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "empresas": len(lista), "espanolas": len(esp),
        "capitalizacion_espanolas": round(sum(e["capitalizacion"] for e in esp), 2),
        "mayores": [{k: e[k] for k in ("nombre", "isin", "capitalizacion")} for e in esp[:5]],
        "fuente": "BME, lista de cotizadas del mercado continuo, ficha e histórico de precios de cada valor",
        "licencia": "Sin licencia abierta: datos de origen de BME, sujetos a sus condiciones. Cita: El Especulador, a partir de datos de BME",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(lista, fecha)
    ld = ld_wp(fecha, fecha[:4])
    marca = "\n<!-- capitalizacion:fin -->"
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Las empresas más grandes de la bolsa española | El Especulador</title>
<meta name="description" content="Las empresas españolas del mercado continuo ordenadas por capitalización al cierre, con la variación de cada una en el año. Datos de BME actualizados cada día hábil.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Las empresas más grandes de la bolsa española</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/empresas.csv">la última clasificación</a> · <a href="datos/{fecha[:4]}.csv">la del año {fecha[:4]}</a> (al acabar el año queda con el último cierre) · <a href="datos/ultima.json">JSON</a>. Puedes reutilizarlos citando «El Especulador, a partir de datos de BME»; los datos de origen son de BME y se rigen por sus condiciones. Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Fuente: BME. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="JSON con la lista de cotizadas de BME (para probar sin red)")
    ap.add_argument("--historial", help="JSON {isin: [[fecha, cierre], ...]} (para probar sin red)")
    ap.add_argument("--extra", help="JSON {isin: ficha} de las clases fuera de lista (para probar sin red)")
    ap.add_argument("--fecha")
    a = ap.parse_args()
    filas = json.loads(Path(a.local).read_text(encoding="utf-8")) if a.local else descargar()
    extra = json.loads(Path(a.extra).read_text(encoding="utf-8")) if a.extra else ({} if a.local else fichas_fuera_de_lista())
    fecha = a.fecha or fecha_cierre() or date.today().isoformat()
    lista = preparar(filas, extra)
    hist = json.loads(Path(a.historial).read_text(encoding="utf-8")) if a.historial else historiales([e["isin"] for e in lista], int(fecha[:4]))
    revisar(lista, hist, fecha)
    escribir(lista, fecha, Path(a.salida))
    esp = [e for e in lista if e["espanola"]]
    if SIN_NOMBRE:
        print(f"::warning::Cotizadas sin nombre corto en nombres.py: {SIN_NOMBRE}")
    for av in AVISOS:
        print(f"::warning::{av}")
    marcadas = [f"{e['nombre']} ({'sin cotizar' if e['sin_cotizar'] else 'en bolsa desde ' + _f(e['en_bolsa_desde'])})"
                for e in lista if e["sin_cotizar"] or e["en_bolsa_desde"]]
    print(f"{len(lista)} empresas ({len(esp)} españolas), datos al {fecha}. La mayor: {esp[0]['nombre']}, "
          f"{_num(esp[0]['capitalizacion'] / 1e6)} millones. Marcadas: {', '.join(marcadas) or 'ninguna'}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
