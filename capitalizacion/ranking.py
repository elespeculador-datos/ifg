"""Las empresas más grandes de la bolsa española y las que más suben y bajan en el año.

Fuente: lista de cotizadas del mercado continuo (SIBE) de BME, con la
capitalización y la variación en el año de cada valor. Una fila por empresa:
si una empresa tuviera varias clases en la lista, se suma su capitalización.

PREPARADO, SIN PUBLICAR: espera a que BME confirme si su licencia de datos
cubre mostrarlo en una web gratuita. No tiene flujo de GitHub ni escribe en
docs/ (lo que hay en docs/ se publica en GitHub Pages).

Uso:
  python capitalizacion/ranking.py --salida DIR [--local cotizadas.json] [--fecha AAAA-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nombres import NOMBRES  # noqa: E402

COTIZADAS = "https://apiweb.bolsasymercados.es/Market/v1/EQ/ListedCompanies"
FICHA = "https://apiweb.bolsasymercados.es/Market/v1/EQ/ShareDetailsInfo"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/"}
PAGINA_WP = "https://elespeculador.com/empresas-mas-grandes-bolsa-espanola/"
METODOLOGIA = "https://elespeculador-datos.github.io/ifg/capitalizacion/"
TOP_VARIACION = 10
NOTAS_CLASE = {"ES0171996087": "solo la clase A", "ES0105777017": "solo la clase B, la que cotiza"}
NOTAS_SEDE = {"NL0015001FS8": "Ferrovial, con sede en Países Bajos desde 2023"}


class DatosRaros(Exception):
    pass


def _num(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + _num(abs(x), 1) + " %"


SIN_NOMBRE: list[str] = []


def nombre(c: dict) -> str:
    if c.get("isin") in NOMBRES:
        return NOMBRES[c["isin"]]
    n = c.get("shareName") or c.get("name") or ""
    SIN_NOMBRE.append(f"{c.get('isin')} {n}")
    return " ".join(w if (len(w) <= 3 and w.isupper() and w not in {"DE", "DEL", "LA", "EL", "Y"}) else w.capitalize() for w in n.split())


# --------------------------------------------------------------------------- datos
def descargar() -> list[dict]:
    r = requests.get(COTIZADAS, params={"tradingSystem": "SIBE", "page": 0, "pageSize": 0}, headers=CABECERAS, timeout=90)
    r.raise_for_status()
    j = r.json()
    if j.get("hasMoreResults"):
        raise DatosRaros("BME pagina la lista de cotizadas")
    return j.get("data", [])


def fecha_cierre() -> str | None:
    """Fecha del último cierre, según la ficha de un valor muy líquido (Santander)."""
    try:
        r = requests.get(FICHA, params={"isin": "ES0113900J37"}, headers=CABECERAS, timeout=30)
        return r.json().get("lastClosePriceDate")
    except Exception:  # noqa: BLE001
        return None


def preparar(filas: list[dict]) -> list[dict]:
    if len(filas) < 100:
        raise DatosRaros(f"BME solo devuelve {len(filas)} cotizadas")
    empresas: dict[str, dict] = {}
    for f in filas:
        cap = f.get("capitalisation")
        if not cap or cap <= 0:
            continue
        e = empresas.setdefault(f["companyKey"], {"isin": f["isin"], "nombre": nombre(f), "capitalizacion": 0.0,
                                                  "variacion_anio_pct": None, "ibex35": False, "espanola": f["isin"].startswith("ES"),
                                                  "_mayor": 0.0})
        e["capitalizacion"] += float(cap)
        if float(cap) > e["_mayor"]:  # la variación del año, la de la clase con más capitalización
            e["_mayor"] = float(cap)
            e["isin"] = f["isin"]
            e["nombre"] = nombre(f)
            e["espanola"] = f["isin"].startswith("ES")
            if f.get("annualDifference") is not None:
                e["variacion_anio_pct"] = round(float(f["annualDifference"]) * 100, 2)
        e["ibex35"] = e["ibex35"] or "IBEX 35" in (f.get("indices") or "")
    lista = sorted(empresas.values(), key=lambda e: -e["capitalizacion"])
    total = sum(e["capitalizacion"] for e in lista)
    if total < 500e9 or sum(e["ibex35"] for e in lista) != 35:
        raise DatosRaros(f"Datos raros: capitalización total {total / 1e9:.0f} mil millones, {sum(e['ibex35'] for e in lista)} del IBEX")
    for i, e in enumerate(lista, 1):
        e["puesto"] = i
        e.pop("_mayor")
    esp = [e for e in lista if e["espanola"]]
    for i, e in enumerate(esp, 1):
        e["puesto_espanolas"] = i
    return lista


# --------------------------------------------------------------------------- texto
def fragmento(lista: list[dict], fecha: str) -> str:
    esp = [e for e in lista if e["espanola"]]
    ext = [e for e in lista if not e["espanola"]]
    total = sum(e["capitalizacion"] for e in esp)
    top5 = sum(e["capitalizacion"] for e in esp[:5])
    mas_100 = [e for e in esp if e["capitalizacion"] >= 100e9]
    f = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    anio = fecha[:4]

    def fila(e: dict, puesto: int) -> str:
        v = "—" if e["variacion_anio_pct"] is None else _pct(e["variacion_anio_pct"])
        ibex = " <small>(IBEX 35)</small>" if e["ibex35"] else ""
        if e["isin"] in NOTAS_CLASE:
            ibex += f" <small>({NOTAS_CLASE[e['isin']]})</small>"
        return (f"<tr><td>{puesto}</td><td>{html.escape(e['nombre'])}{ibex}</td>"
                f"<td>{_num(e['capitalizacion'] / 1e6)}</td><td>{v}</td></tr>")

    cab = "<thead><tr><th>Puesto</th><th>Empresa</th><th>Capitalización (millones de €)</th><th>Variación en " + anio + "</th></tr></thead>"
    filas_esp = "\n".join(fila(e, e["puesto_espanolas"]) for e in esp)
    con_var = [e for e in esp if e["variacion_anio_pct"] is not None]
    suben = sorted(con_var, key=lambda e: -e["variacion_anio_pct"])[:TOP_VARIACION]
    bajan = sorted(con_var, key=lambda e: e["variacion_anio_pct"])[:TOP_VARIACION]

    def corta(es: list[dict]) -> str:
        return "\n".join(f"<tr><td>{html.escape(e['nombre'])}</td><td>{_pct(e['variacion_anio_pct'])}</td><td>{_num(e['capitalizacion'] / 1e6)}</td></tr>" for e in es)

    ibex = [e for e in lista if e["ibex35"] and e["variacion_anio_pct"] is not None]
    ib_suben = sorted(ibex, key=lambda e: -e["variacion_anio_pct"])[:5]
    ib_bajan = sorted(ibex, key=lambda e: e["variacion_anio_pct"])[:5]
    cab_corta = "<thead><tr><th>Empresa</th><th>Variación en " + anio + "</th><th>Capitalización (millones de €)</th></tr></thead>"
    filas_ext = "\n".join(
        f"<tr><td>{html.escape(e['nombre'])}</td><td>{_num(e['capitalizacion'] / 1e6)}</td><td>{html.escape(NOTAS_SEDE.get(e['isin'], 'Sede fuera de España'))}</td></tr>"
        for e in ext)
    resumen = (f"<p>Al cierre del {f}, las {len(esp)} empresas españolas del mercado continuo valen en bolsa "
               f"{_num(total / 1e12, 2)} billones de euros. Las cinco mayores ({', '.join(html.escape(e['nombre']) for e in esp[:5])}) "
               f"suman el {_num(top5 / total * 100, 1)} %")
    resumen += (f", y {len(mas_100)} superan los 100.000 millones." if mas_100 else ".") + "</p>"
    return (f"<!-- capitalizacion:inicio {fecha} -->\n"
            f"{resumen}\n"
            f"<h2>Las empresas españolas por capitalización</h2>\n"
            f'<figure class="wp-block-table"><table>{cab}<tbody>\n{filas_esp}\n</tbody></table></figure>\n'
            f"<h2>Las que más suben en {anio}</h2>\n"
            f'<figure class="wp-block-table"><table>{cab_corta}<tbody>\n{corta(suben)}\n</tbody></table></figure>\n'
            f"<h2>Las que más bajan en {anio}</h2>\n"
            f'<figure class="wp-block-table"><table>{cab_corta}<tbody>\n{corta(bajan)}\n</tbody></table></figure>\n'
            f"<h2>En el IBEX 35: las cinco que más suben y las cinco que más bajan en {anio}</h2>\n"
            f'<figure class="wp-block-table"><table>{cab_corta}<tbody>\n{corta(ib_suben)}\n{corta(ib_bajan)}\n</tbody></table></figure>\n'
            f"<h2>Empresas extranjeras que cotizan en el mercado continuo</h2>\n"
            f"<p>No entran en la clasificación porque su sede está fuera de España, aunque cotizan en las bolsas españolas.</p>\n"
            f'<figure class="wp-block-table"><table><thead><tr><th>Empresa</th><th>Capitalización (millones de €)</th><th>Nota</th></tr></thead><tbody>\n{filas_ext}\n</tbody></table></figure>\n'
            f'<p class="has-small-font-size">Datos al cierre del {f}. Fuente: BME, lista de cotizadas del mercado continuo. '
            f'Variación del año: solo precio, sin dividendos. <a href="{METODOLOGIA}">Cómo se calcula</a>.</p>\n'
            f"<!-- capitalizacion:fin -->")


def escribir(lista: list[dict], fecha: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    campos = ["puesto", "puesto_espanolas", "nombre", "isin", "capitalizacion", "variacion_anio_pct", "ibex35", "espanola"]
    with (salida / "empresas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for e in lista:
            w.writerow({k: e.get(k, "") for k in campos})
    frag = fragmento(lista, fecha)
    assert "$" not in frag
    (salida / "fragmento-wp.html").write_text(frag, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local")
    ap.add_argument("--fecha")
    a = ap.parse_args()
    filas = json.loads(Path(a.local).read_text(encoding="utf-8")) if a.local else descargar()
    fecha = a.fecha or (lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d else date.today().isoformat())(None if a.local else fecha_cierre())
    lista = preparar(filas)
    escribir(lista, fecha, Path(a.salida))
    esp = [e for e in lista if e["espanola"]]
    if SIN_NOMBRE:
        print(f"::warning::Cotizadas sin nombre corto en nombres.py: {SIN_NOMBRE}")
    print(f"{len(lista)} empresas ({len(esp)} españolas). La mayor: {esp[0]['nombre']}, {_num(esp[0]['capitalizacion'] / 1e6)} millones.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
