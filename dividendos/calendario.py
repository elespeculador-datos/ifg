"""Calendario de dividendos de la bolsa española de El Especulador.

Cada día hábil descarga de la API pública de BME los dividendos del mercado
continuo (SIBE) y publica:

  docs/dividendos/datos/dividendos.csv   todos los dividendos de los últimos tres años y los anunciados
  docs/dividendos/datos/proximos.csv     los que aún no han descontado (fecha ex de hoy en adelante)
  docs/dividendos/datos/ultimos_12m.csv  lo pagado por acción en los últimos doce meses, por empresa
  docs/dividendos/datos/ultima.json      resumen
  docs/dividendos/fragmento-wp.html      tablas en HTML para la página de elespeculador.com
  docs/dividendos/index.html             página propia del dato

Uso:
  python dividendos/calendario.py                    descarga y publica
  python dividendos/calendario.py --local F.json     usa una respuesta ya descargada (pruebas)
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/Dividends"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/"}
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "dividendos"
DATOS = SALIDA / "datos"
PILAR = "https://elespeculador.com/dividendos-fecha-ex-dividendo/"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
CONCEPTOS = {"A": "a cuenta", "C": "complementario", "E": "especial", "R": "con cargo a reservas", "P": "prima de emisión",
             "D": "devolución de aportaciones", "U": "único"}


class DatosRaros(Exception):
    """La respuesta no tiene la forma esperada: mejor parar que publicar basura."""


def hoy_madrid() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(ZoneInfo("Europe/Madrid")).date())


# --------------------------------------------------------------------------- descarga
def _tramo(desde: str, hasta: str) -> list[dict]:
    ultimo = None
    for intento in range(4):
        try:
            r = requests.get(API, params={"companyKey": "", "from": desde, "to": hasta, "page": 0, "pageSize": 0,
                                          "tradingSystem": "SIBE", "listingType": "All"}, headers=CABECERAS, timeout=90)
            if r.status_code == 200:
                j = r.json()
                if j.get("hasMoreResults"):
                    raise DatosRaros(f"La API pagina el tramo {desde}-{hasta}")
                return j.get("data", [])
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo = str(e)
        time.sleep(15 * (intento + 1))
    raise DatosRaros(f"No se pudo descargar {desde}-{hasta}: {ultimo}")


def descargar() -> list[dict]:
    h = hoy_madrid()
    filas = []
    for a in range(h.year - 3, h.year + 2):
        filas += _tramo(f"{a}0101", f"{a}1231")
    return filas


# --------------------------------------------------------------------------- limpieza
def preparar(filas: list[dict]) -> pd.DataFrame:
    if not filas:
        raise DatosRaros("BME no ha devuelto ningún dividendo")
    d = pd.DataFrame(filas)
    faltan = {"exDate", "paymentDate", "company", "isin", "grossAmount", "currency"} - set(d.columns)
    if faltan:
        raise DatosRaros(f"Faltan columnas en la respuesta de BME: {faltan}")
    d = d.drop_duplicates()
    d["fecha_ex"] = pd.to_datetime(d["exDate"], format="%Y%m%d", errors="coerce")
    d["fecha_pago"] = pd.to_datetime(d["paymentDate"], format="%Y%m%d", errors="coerce")
    d["bruto"] = pd.to_numeric(d["grossAmount"], errors="coerce")
    if d["fecha_ex"].isna().mean() > 0.05 or d["bruto"].isna().mean() > 0.05:
        raise DatosRaros("Demasiadas fechas o importes ilegibles")
    d = d.dropna(subset=["fecha_ex", "bruto"])
    d = d[d["bruto"] > 0]
    d["empresa"] = d.get("share", d["company"]).fillna(d["company"]).str.strip()
    d["concepto"] = d.get("concept", pd.Series([""] * len(d))).map(CONCEPTOS).fillna(d.get("conceptText", "").str.lower())
    d["extraordinario"] = d.get("type", pd.Series([""] * len(d))).eq("E")
    d["flexible"] = d.get("type", pd.Series([""] * len(d))).eq("B")
    d["moneda"] = d["currency"].fillna("EUR")
    d["ejercicio"] = d.get("year", "")
    d = d.sort_values(["fecha_ex", "empresa"]).reset_index(drop=True)
    h = hoy_madrid()
    ult12 = d[(d["fecha_ex"] > h - pd.DateOffset(years=1)) & (d["fecha_ex"] <= h)]
    if len(ult12) < 50:
        raise DatosRaros(f"Solo {len(ult12)} dividendos en los últimos doce meses: la respuesta parece incompleta")
    return d[["fecha_ex", "fecha_pago", "empresa", "company", "isin", "bruto", "moneda", "concepto", "extraordinario", "flexible", "ejercicio"]]


def acumular(d: pd.DataFrame) -> pd.DataFrame:
    """BME solo da el último año: se va guardando el histórico en el propio repositorio."""
    previo = DATOS / "dividendos.csv"
    if previo.exists():
        p = pd.read_csv(previo, dtype={"isin": str, "ejercicio": str}, parse_dates=["fecha_ex", "fecha_pago"])
        d = pd.concat([p, d], ignore_index=True)
    clave = ["isin", "fecha_ex", "concepto", "extraordinario", "flexible"]
    return d.drop_duplicates(clave, keep="last").sort_values(["fecha_ex", "empresa"]).reset_index(drop=True)


# --------------------------------------------------------------------------- formato
def _fecha(x) -> str:
    return "—" if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


def _importe(x: float, moneda: str) -> str:
    entero, _, dec = f"{x:.6f}".partition(".")
    dec = dec.rstrip("0").ljust(2, "0")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{entero},{dec} {'€' if moneda == 'EUR' else moneda}"


def _lista(nombres: list[str]) -> str:
    nombres = sorted(nombres)
    if len(nombres) == 1:
        return nombres[0]
    ultimo = nombres[-1]
    y = "e" if ultimo.lower().startswith(("i", "hi")) and not ultimo.lower().startswith(("ie", "hie")) else "y"
    return ", ".join(nombres[:-1]) + f" {y} " + ultimo


def _tipo(r) -> str:
    t = r.concepto if isinstance(r.concepto, str) else ""
    if r.flexible:
        t += " (flexible: importe para quien elige efectivo)"
    elif r.extraordinario and "especial" not in t:
        t += " (extraordinario)"
    return t.strip() or "—"


# --------------------------------------------------------------------------- salidas
def calcular(d: pd.DataFrame) -> dict:
    h = hoy_madrid()
    prox = d[d["fecha_ex"] >= h].copy()
    pasados = d[(d["fecha_ex"] > h - pd.DateOffset(years=1)) & (d["fecha_ex"] < h)]
    ult = (pasados.groupby(["isin", "empresa", "moneda"], as_index=False)
           .agg(pagos=("bruto", "size"), bruto_total=("bruto", "sum"), ultima_fecha_ex=("fecha_ex", "max"))
           .sort_values("empresa"))
    ult["bruto_total"] = ult["bruto_total"].round(6)
    return {"hoy": h, "proximos": prox, "ultimos_12m": ult, "todos": d}


def frase(r: dict) -> str:
    prox = r["proximos"]
    h = r["hoy"]
    if prox.empty:
        return "BME no tiene anunciado ningún dividendo con fecha ex de hoy en adelante."
    siguiente = prox["fecha_ex"].min()
    del_dia = prox.loc[prox["fecha_ex"] == siguiente, "empresa"].unique().tolist()
    n_emp = prox["empresa"].nunique()
    texto = (f"Hay {len(prox)} {'dividendo anunciado' if len(prox) == 1 else 'dividendos anunciados'} con fecha ex de hoy en adelante, "
             f"de {n_emp} {'empresa' if n_emp == 1 else 'empresas'}. "
             f"El próximo es el {_fecha(siguiente)}: {'descuenta' if len(del_dia) == 1 else 'descuentan'} {_lista(del_dia)}.")
    return texto


def fragmento_wp(r: dict) -> str:
    def e(x) -> str:
        return html.escape(str(x)).replace("$", "&#36;")
    prox, ult = r["proximos"], r["ultimos_12m"]
    if prox.empty:
        t_prox = "<p>Ahora mismo no hay dividendos anunciados con fecha ex posterior a hoy.</p>"
    else:
        filas = "\n".join(
            f"<tr><td>{_fecha(x.fecha_ex)}</td><td>{e(x.empresa)}</td><td>{_importe(x.bruto, x.moneda)}</td><td>{e(_tipo(x))}</td><td>{_fecha(x.fecha_pago)}</td></tr>"
            for x in prox.itertuples())
        t_prox = ("<figure class=\"wp-block-table\"><table><thead><tr><th>Fecha ex</th><th>Empresa</th><th>Bruto por acción</th><th>Tipo</th><th>Fecha de pago</th></tr></thead><tbody>\n"
                  + filas + "\n</tbody></table></figure>")
    filas_u = "\n".join(
        f"<tr><td>{e(x.empresa)}</td><td>{int(x.pagos)}</td><td>{_importe(x.bruto_total, x.moneda)}</td><td>{_fecha(x.ultima_fecha_ex)}</td></tr>"
        for x in ult.itertuples())
    t_ult = ("<figure class=\"wp-block-table\"><table><thead><tr><th>Empresa</th><th>Pagos</th><th>Bruto por acción, en total</th><th>Último, con fecha ex</th></tr></thead><tbody>\n"
             + filas_u + "\n</tbody></table></figure>")
    return f"""<!-- dividendos:inicio {r['hoy'].date().isoformat()} -->
<p><strong>Datos a {_fecha(r['hoy'])}.</strong> {e(frase(r))}</p>
<h2>Próximos dividendos</h2>
<p>Para cobrar hay que tener las acciones compradas al cierre de la sesión anterior a la fecha ex.</p>
{t_prox}
<h2>Dividendos de los últimos doce meses</h2>
<p>Lo que ha repartido cada empresa por acción, sumando todos los pagos con fecha ex en el último año.</p>
{t_ult}
<!-- dividendos:fin -->"""


def escribir(r: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    def fechas(df):
        df = df.copy()
        for c in ("fecha_ex", "fecha_pago", "ultima_fecha_ex"):
            if c in df.columns:
                df[c] = df[c].dt.date
        return df
    fechas(r["todos"]).to_csv(DATOS / "dividendos.csv", index=False)
    fechas(r["proximos"]).to_csv(DATOS / "proximos.csv", index=False)
    fechas(r["ultimos_12m"]).to_csv(DATOS / "ultimos_12m.csv", index=False)
    prox = r["proximos"]
    (DATOS / "ultima.json").write_text(json.dumps({
        "fecha": r["hoy"].date().isoformat(),
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proximos": int(len(prox)),
        "siguiente": None if prox.empty else {"fecha_ex": prox["fecha_ex"].min().date().isoformat(),
                                              "empresas": sorted(prox.loc[prox["fecha_ex"] == prox["fecha_ex"].min(), "empresa"].unique().tolist())},
        "fuente": "BME, operaciones financieras: dividendos", "licencia": "CC BY 4.0 · El Especulador",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento_wp(r)
    (SALIDA / "fragmento-wp.html").write_text(frag, encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (SALIDA / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendario de dividendos de la bolsa española | El Especulador</title>
<meta name="description" content="Próximos dividendos del mercado continuo con su fecha ex, importe y fecha de pago, y lo repartido por cada empresa en los últimos doce meses. Datos de BME actualizados cada día hábil.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Calendario de dividendos de la bolsa española</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/proximos.csv">próximos dividendos</a> · <a href="datos/ultimos_12m.csv">últimos doce meses</a> · <a href="datos/dividendos.csv">todos desde hace tres años</a> · <a href="datos/ultima.json">JSON</a>. Licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>, citando «El Especulador, a partir de datos de BME». Cómo funcionan las fechas: <a href="{PILAR}">qué día hay que tener las acciones para cobrar el dividendo</a>.</p>
<p class="pie">Fuente: BME, operaciones financieras del mercado continuo. Importes brutos por acción, antes de retenciones. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="JSON con la lista de dividendos de BME")
    args = ap.parse_args()
    filas = json.loads(Path(args.local).read_text(encoding="utf-8")) if args.local else descargar()
    r = calcular(acumular(preparar(filas)))
    escribir(r)
    print(frase(r))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
