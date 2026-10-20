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
FICHA = "https://apiweb.bolsasymercados.es/Market/v1/EQ/ShareDetailsInfo"
CABECERAS = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/"}
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "dividendos"
DATOS = SALIDA / "datos"
PILAR = "https://elespeculador.com/dividendos-fecha-ex-dividendo/"
PAGINA_WP = "https://elespeculador.com/calendario-dividendos/"
TOP_RENTABILIDAD = 15
# Nombres cortos de BME que no se entienden fuera de su web
NOMBRES = {"CASH": "PROSEGUR CASH"}
# Composición del IBEX 35 (sin cambios desde el 22/07/2024, cuando Puig sustituyó a Meliá). Se revisa cada trimestre:
# pasada esta fecha, la tabla del IBEX deja de publicarse hasta que se actualicen ibex35.csv y la fecha.
IBEX35 = Path(__file__).resolve().parent / "ibex35.csv"
IBEX35_VALIDA_HASTA = "2026-12-20"
PAGES = "https://elespeculador-datos.github.io/ifg/dividendos/"
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


def cotizaciones(isins: list[str]) -> list[dict]:
    """Último cierre y capitalización de cada acción (ficha de BME). Nunca hace fallar el calendario."""
    filas = []
    for isin in isins:
        try:
            r = requests.get(FICHA, params={"isin": isin}, headers=CABECERAS, timeout=30)
            if r.status_code == 200:
                j = r.json()
                filas.append({k: j.get(k) for k in ("isin", "lastClosePrice", "lastClosePriceDate", "capitalisation", "currency")})
        except Exception as e:  # noqa: BLE001 - una ficha caída no debe parar el resto
            print(f"Sin ficha de {isin}: {e}")
        time.sleep(0.2)
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
    d["empresa"] = d.get("share", d["company"]).fillna(d["company"]).str.strip().replace(NOMBRES)
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
    # Una fila por acción y moneda; si BME cambió el nombre (Ferrovial SE / N.V.), se queda el del último pago.
    pasados = pasados.sort_values("fecha_ex")
    ult = (pasados.groupby(["isin", "moneda"], as_index=False)
           .agg(empresa=("empresa", "last"), pagos=("bruto", "size"), bruto_total=("bruto", "sum"), ultima_fecha_ex=("fecha_ex", "max"))
           .sort_values(["empresa", "moneda"]))[["isin", "empresa", "moneda", "pagos", "bruto_total", "ultima_fecha_ex"]]
    ult["bruto_total"] = ult["bruto_total"].round(6)
    ordinario = (pasados[~pasados["extraordinario"].astype(bool)].groupby(["isin", "moneda"])["bruto"].sum().round(6)
                 .rename("bruto_ordinario").reset_index())
    ult = ult.merge(ordinario, on=["isin", "moneda"], how="left").fillna({"bruto_ordinario": 0.0}).reset_index(drop=True)
    return {"hoy": h, "proximos": prox, "ultimos_12m": ult, "todos": d}


def rentabilidad(r: dict, cot: list[dict]) -> pd.DataFrame:
    """Rentabilidad por dividendo de los últimos doce meses sobre el último cierre.

    Solo se calcula si la ficha de BME tiene un cierre de los últimos diez días, en la
    misma moneda que el dividendo. La ordinaria excluye los dividendos extraordinarios;
    los flexibles cuentan por el importe para quien elige efectivo.
    """
    columnas = ["isin", "empresa", "moneda", "pagos", "bruto_total", "bruto_ordinario", "cierre", "fecha_cierre",
                "capitalizacion", "rentabilidad_pct", "rentabilidad_ordinaria_pct"]
    if not cot:
        return pd.DataFrame(columns=columnas)
    c = pd.DataFrame(cot).rename(columns={"lastClosePrice": "cierre", "capitalisation": "capitalizacion", "currency": "moneda_cot"})
    c["fecha_cierre"] = pd.to_datetime(c["lastClosePriceDate"], format="%Y%m%d", errors="coerce")
    c["cierre"] = pd.to_numeric(c["cierre"], errors="coerce")
    u = r["ultimos_12m"].merge(c[["isin", "cierre", "fecha_cierre", "capitalizacion", "moneda_cot"]], on="isin", how="inner")
    una_moneda = u.groupby("isin")["moneda"].transform("nunique") == 1
    valida = (u["cierre"] > 0) & una_moneda & (u["moneda"] == u["moneda_cot"].fillna("EUR")) & (u["fecha_cierre"] >= r["hoy"] - pd.Timedelta(days=10))
    u = u[valida].copy()
    u["rentabilidad_pct"] = (100 * u["bruto_total"] / u["cierre"]).round(2)
    u["rentabilidad_ordinaria_pct"] = (100 * u["bruto_ordinario"] / u["cierre"]).round(2)
    return u.sort_values(["rentabilidad_ordinaria_pct", "empresa"], ascending=[False, True])[columnas].reset_index(drop=True)


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


def ibex35(hoy: pd.Timestamp) -> set[str]:
    """ISIN del IBEX 35 si la composición guardada sigue vigente; si no, vacío (y aviso)."""
    if hoy > pd.Timestamp(IBEX35_VALIDA_HASTA) or not IBEX35.exists():
        print(f"::warning::La composición del IBEX 35 de {IBEX35.name} venció el {IBEX35_VALIDA_HASTA}: no se publica la tabla del IBEX.")
        return set()
    return set(pd.read_csv(IBEX35, dtype=str)["isin"])


def frase_rentabilidad(rent: pd.DataFrame, ibex: set[str] | None = None) -> str:
    if rent.empty:
        return ""
    t = rent.iloc[0]
    texto = (f"La mayor rentabilidad por dividendo ordinaria de los últimos doce meses es la de {t.empresa}: "
             f"{_pct(t.rentabilidad_ordinaria_pct)} sobre su cierre del {_fecha(t.fecha_cierre)}.")
    i = rent[rent["isin"].isin(ibex or set())]
    if not i.empty and i.iloc[0]["isin"] != t.isin:
        texto += f" En el IBEX 35, la de {i.iloc[0]['empresa']}, con un {_pct(i.iloc[0]['rentabilidad_ordinaria_pct'])}."
    return texto


def _pct(x: float) -> str:
    return f"{x:.2f}".replace(".", ",") + " %"


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
    rent = r.get("rentabilidad", pd.DataFrame())
    por_isin = {} if rent.empty else {(q["isin"], q["moneda"]): q for q in rent.to_dict("records")}

    def celda_rent(x) -> str:
        q = por_isin.get((x.isin, x.moneda))
        if not q:
            return "—"
        nota = " (con extraordinario)" if q["bruto_total"] - q["bruto_ordinario"] > 1e-9 else ""
        return _pct(q["rentabilidad_pct"]) + nota
    extra = (lambda x: f"<td>{celda_rent(x)}</td>") if por_isin else (lambda x: "")
    filas_u = "\n".join(
        f"<tr><td>{e(x.empresa)}</td><td>{int(x.pagos)}</td><td>{_importe(x.bruto_total, x.moneda)}</td><td>{_fecha(x.ultima_fecha_ex)}</td>{extra(x)}</tr>"
        for x in ult.itertuples())
    t_ult = ("<figure class=\"wp-block-table\"><table><thead><tr><th>Empresa</th><th>Pagos</th><th>Bruto por acción, en total</th><th>Último, con fecha ex</th>"
             + ("<th>Rentabilidad sobre el último cierre</th>" if por_isin else "") + "</tr></thead><tbody>\n"
             + filas_u + "\n</tbody></table></figure>")
    if rent.empty:
        b_rent = ""
    else:
        top = rent[rent["rentabilidad_ordinaria_pct"] > 0].head(TOP_RENTABILIDAD)
        filas_r = "\n".join(
            f"<tr><td>{i}</td><td>{e(x.empresa)}</td><td>{_importe(x.bruto_ordinario, x.moneda)}</td><td>{_importe(x.cierre, x.moneda)} ({_fecha(x.fecha_cierre)})</td><td>{_pct(x.rentabilidad_ordinaria_pct)}</td></tr>"
            for i, x in enumerate(top.itertuples(), 1))
        ib = rent[rent["isin"].isin(r.get("ibex", set())) & (rent["rentabilidad_ordinaria_pct"] > 0)].head(10)
        b_ibex = "" if ib.empty else (
            "<h3>Las diez del IBEX 35 con más rentabilidad por dividendo</h3>\n"
            "<figure class=\"wp-block-table\"><table><thead><tr><th>Puesto</th><th>Empresa</th><th>Dividendo ordinario, últimos 12 meses</th><th>Último cierre</th><th>Rentabilidad</th></tr></thead><tbody>\n"
            + "\n".join(f"<tr><td>{i}</td><td>{e(x.empresa)}</td><td>{_importe(x.bruto_ordinario, x.moneda)}</td><td>{_importe(x.cierre, x.moneda)} ({_fecha(x.fecha_cierre)})</td><td>{_pct(x.rentabilidad_ordinaria_pct)}</td></tr>"
                        for i, x in enumerate(ib.itertuples(), 1))
            + "\n</tbody></table></figure>\n")
        b_rent = ("<h2>Rentabilidad por dividendo</h2>\n"
                  f"<p>Las {len(top)} empresas con mayor rentabilidad por dividendo ordinaria de los últimos doce meses: lo que han pagado por acción con fecha ex en el último año, "
                  "sin contar los dividendos extraordinarios, dividido entre su último cierre. Los dividendos flexibles cuentan por el importe para quien elige efectivo. "
                  "Es la rentabilidad del último año, no una previsión.</p>\n"
                  "<figure class=\"wp-block-table\"><table><thead><tr><th>Puesto</th><th>Empresa</th><th>Dividendo ordinario, últimos 12 meses</th><th>Último cierre</th><th>Rentabilidad</th></tr></thead><tbody>\n"
                  + filas_r + "\n</tbody></table></figure>\n" + b_ibex)
    return f"""<!-- dividendos:inicio {r['hoy'].date().isoformat()} -->
<p><strong>Datos a {_fecha(r['hoy'])}.</strong> {e((frase(r) + " " + frase_rentabilidad(rent, r.get("ibex"))).strip())}</p>
<h2>Próximos dividendos</h2>
<p>Para cobrar hay que tener las acciones compradas al cierre de la sesión anterior a la fecha ex.</p>
{t_prox}
{b_rent}<h2>Dividendos de los últimos doce meses</h2>
<p>Lo que ha repartido cada empresa por acción, sumando todos los pagos con fecha ex en el último año{", y lo que supone sobre su último cierre" if por_isin else ""}.</p>
{t_ult}
<!-- dividendos:fin -->"""


def ld_wp(r: dict) -> str:
    """Marcado Dataset (schema.org) en una sola línea, para la página de elespeculador.com."""
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Calendario de dividendos de la bolsa española (El Especulador)",
        "description": "Próximos dividendos del mercado continuo con su fecha ex, importe bruto por acción y fecha de pago, lo repartido por cada empresa en los últimos doce meses y su rentabilidad por dividendo sobre el último cierre, con datos de BME actualizados cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de BME", "isBasedOn": "https://www.bolsasymercados.es/",
        "dateModified": r["hoy"].date().isoformat(),
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ["proximos", "ultimos_12m", "rentabilidad", "dividendos"]],
    }, ensure_ascii=False) + "</script>"


def con_ld(frag: str, ld: str) -> str:
    marca = "\n<!-- dividendos:fin -->"
    assert frag.count(marca) == 1 and "$" not in ld
    return frag.replace(marca, "\n" + ld + marca)


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
    rent = r.get("rentabilidad", pd.DataFrame())
    if not rent.empty:
        rr = rent.copy()
        rr["fecha_cierre"] = rr["fecha_cierre"].dt.date
        if r.get("ibex"):
            rr["ibex35"] = rr["isin"].isin(r["ibex"])
        rr.to_csv(DATOS / "rentabilidad.csv", index=False)
    prox = r["proximos"]
    (DATOS / "ultima.json").write_text(json.dumps({
        "fecha": r["hoy"].date().isoformat(),
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proximos": int(len(prox)),
        "siguiente": None if prox.empty else {"fecha_ex": prox["fecha_ex"].min().date().isoformat(),
                                              "empresas": sorted(prox.loc[prox["fecha_ex"] == prox["fecha_ex"].min(), "empresa"].unique().tolist())},
        "mayor_rentabilidad": None if rent.empty else rent.head(3)[["empresa", "isin", "rentabilidad_ordinaria_pct"]].to_dict("records"),
        "fuente": "BME, operaciones financieras: dividendos; cierres de la ficha de cada valor", "licencia": "Sin licencia abierta: datos de origen de BME, sujetos a sus condiciones. Cita: El Especulador, a partir de datos de BME",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento_wp(r)
    (SALIDA / "fragmento-wp.html").write_text(con_ld(frag, ld_wp(r)), encoding="utf-8")
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
<p>CSV: <a href="datos/proximos.csv">próximos dividendos</a> · <a href="datos/ultimos_12m.csv">últimos doce meses</a> · <a href="datos/rentabilidad.csv">rentabilidad por dividendo</a> · <a href="datos/dividendos.csv">todos desde hace tres años</a> · <a href="datos/ultima.json">JSON</a>. Puedes reutilizarlos citando «El Especulador, a partir de datos de BME»; los datos de origen son de BME y se rigen por sus condiciones. Cómo funcionan las fechas: <a href="{PILAR}">qué día hay que tener las acciones para cobrar el dividendo</a>.</p>
<p class="pie">Fuente: BME, operaciones financieras del mercado continuo. Importes brutos por acción, antes de retenciones. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="JSON con la lista de dividendos de BME")
    ap.add_argument("--cotizaciones", help="JSON con las fichas de BME (isin -> ficha), para probar sin red")
    args = ap.parse_args()
    filas = json.loads(Path(args.local).read_text(encoding="utf-8")) if args.local else descargar()
    r = calcular(acumular(preparar(filas)))
    isins = sorted(r["ultimos_12m"]["isin"].unique())
    if args.cotizaciones:
        fichas = json.loads(Path(args.cotizaciones).read_text(encoding="utf-8"))
        cot = [{k: f.get(k) for k in ("isin", "lastClosePrice", "lastClosePriceDate", "capitalisation", "currency")}
               for f in fichas.values() if isinstance(f, dict) and f.get("lastClosePrice")]
    else:
        cot = cotizaciones(isins)
    r["rentabilidad"] = rentabilidad(r, cot)
    r["ibex"] = ibex35(r["hoy"])
    print(f"Cierres: {len(cot)} de {len(isins)}; rentabilidad calculada para {len(r['rentabilidad'])}.")
    escribir(r)
    print(frase(r), frase_rentabilidad(r["rentabilidad"], r["ibex"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
