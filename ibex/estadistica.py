"""Estadística del IBEX 35 de El Especulador.

Cada día hábil, con los cierres oficiales que publica BME, calcula y publica:

  docs/ibex/datos/ultima.json              último cierre, rentabilidades y récords
  docs/ibex/datos/rentabilidad_anual.csv   rentabilidad de cada año natural desde 1993
  docs/ibex/datos/rentabilidad_mensual.csv rentabilidad de cada mes de los últimos años
  docs/ibex/datos/maximos.csv              cada nuevo máximo histórico al cierre
  docs/ibex/fragmento-wp.html              tablas en HTML para la página de elespeculador.com
  docs/ibex/index.html                     página propia del dato

La API de BME solo da los últimos cinco años. Los años anteriores salen de
ibex/historico_anual.csv (serie verificada de El Especulador) y, en los años
que se solapan, el script comprueba que su cálculo coincide con esa serie: si
no coincide, se para sin publicar. No se publica la serie diaria de
cotizaciones, solo las cifras derivadas.

Uso:
  python ibex/estadistica.py                 descarga y publica
  python ibex/estadistica.py --local F.csv   usa un CSV con fecha,cierre[,maximo] (pruebas)
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "ibex"
DATOS = SALIDA / "datos"
HISTORICO = Path(__file__).resolve().parent / "historico_anual.csv"
PILAR = "https://elespeculador.com/historico-ibex-35-records/"
PAGINA_WP = "https://elespeculador.com/ibex-35-en-cifras/"
PAGES = "https://elespeculador-datos.github.io/ifg/ibex/"

# Récords anteriores a la ventana de la API: 15.945,70 puntos al cierre y
# 16.040,40 intradía, los dos del 8/11/2007. Ningún cierre ni máximo intradía
# anterior a octubre de 2021 llegó a 16.200 puntos, así que cualquier máximo de la
# ventana por encima de esa cota es también el máximo de toda la historia.
RECORD_PREVIO = (15945.70, "2007-11-08")
COTA_PREVIA = 16200.0
TOLERANCIA_PP = 0.05

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


class DatosRaros(Exception):
    """La serie no tiene la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- formato
def _num(x, dec=2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, signo=True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return (("+" if x > 0 and signo else "") + _num(x) + " %").replace("-", "−")


def _fecha(d) -> str:
    return "—" if d is None or pd.isna(d) else pd.Timestamp(d).strftime("%d/%m/%Y")


def _fecha_larga(d) -> str:
    t = pd.Timestamp(d)
    return f"{t.day} de {MESES[t.month - 1]} de {t.year}"


# --------------------------------------------------------------------------- validación
def validar(s: pd.DataFrame) -> pd.DataFrame:
    s = s.dropna(subset=["cierre"]).copy()
    s["fecha"] = pd.to_datetime(s["fecha"]).dt.normalize()
    s = s[s["fecha"].dt.dayofweek < 5]
    s = s.sort_values("fecha").drop_duplicates("fecha", keep="last").reset_index(drop=True)
    if len(s) < 900:
        raise DatosRaros(f"Serie demasiado corta: {len(s)} sesiones")
    retraso = (pd.Timestamp.now().normalize() - s["fecha"].iloc[-1]).days
    if retraso > 6:
        raise DatosRaros(f"El último cierre es del {s['fecha'].iloc[-1].date()}: la fuente no se ha actualizado")
    var = s["cierre"].pct_change().abs()
    if (var > 0.25).any():
        malas = s.loc[var > 0.25, ["fecha", "cierre"]].head(3).to_dict("records")
        raise DatosRaros(f"Saltos diarios imposibles en la serie: {malas}")
    if not (1000 < s["cierre"].iloc[-1] < 100000):
        raise DatosRaros(f"Cierre fuera de rango: {s['cierre'].iloc[-1]}")
    return s


# --------------------------------------------------------------------------- cálculos
def calcular(s: pd.DataFrame, hist: pd.DataFrame) -> dict:
    s = s.copy()
    s["var_pct"] = s["cierre"].pct_change() * 100
    s["anio"] = s["fecha"].dt.year
    s["mes"] = s["fecha"].dt.month
    ult = s.iloc[-1]
    hoy = ult["fecha"]
    primer_anio = int(s["anio"].iloc[0])

    fin_anio = s.groupby("anio")["cierre"].last()
    fin_mes = s.groupby(["anio", "mes"])["cierre"].last()

    # Rentabilidad anual: años calculables con la ventana + serie verificada
    hist = hist.set_index("anio")
    filas = {}
    for a in hist.index:
        filas[int(a)] = {"anio": int(a), "periodo": "año completo", "rentabilidad_pct": float(hist.loc[a, "rentabilidad_pct"]),
                         "con_dividendos_pct": None if pd.isna(hist.loc[a, "con_dividendos_pct"]) else float(hist.loc[a, "con_dividendos_pct"]),
                         "cierre": None, "fuente": "serie verificada de El Especulador"}
    for a in fin_anio.index:
        if a == primer_anio:
            continue  # la ventana empieza a mitad de ese año
        r = round(float((fin_anio[a] / fin_anio[a - 1] - 1) * 100), 2)
        if a in filas and abs(filas[a]["rentabilidad_pct"] - r) > TOLERANCIA_PP:
            raise DatosRaros(f"La rentabilidad de {a} calculada ({r}) no coincide con la serie verificada ({filas[a]['rentabilidad_pct']})")
        previa = filas.get(a, {})
        filas[a] = {"anio": int(a), "periodo": "año completo" if a < hoy.year else f"hasta el {_fecha(hoy)}",
                    "rentabilidad_pct": r, "con_dividendos_pct": previa.get("con_dividendos_pct") if a < hoy.year else None,
                    "cierre": round(float(fin_anio[a]), 2), "fuente": "cálculo con los cierres de BME"}
    anual = pd.DataFrame(sorted(filas.values(), key=lambda x: x["anio"]))

    mensual = []
    claves = list(fin_mes.index)
    for i, k in enumerate(claves):
        if i == 0:
            continue  # primer mes incompleto
        r = (fin_mes[k] / fin_mes[claves[i - 1]] - 1) * 100
        mensual.append({"anio": k[0], "mes": k[1], "cierre": round(float(fin_mes[k]), 2), "rentabilidad_pct": round(float(r), 2),
                        "completo": not (k[0] == hoy.year and k[1] == hoy.month)})
    mensual = pd.DataFrame(mensual)

    # Máximos históricos al cierre
    s["max_previo"] = s["cierre"].cummax().shift(1).fillna(0).clip(lower=RECORD_PREVIO[0])
    nuevos = s[s["cierre"] > s["max_previo"]][["fecha", "cierre"]]
    if s["cierre"].max() > COTA_PREVIA:
        i_max = s["cierre"].idxmax()
        maximo = {"valor": round(float(s.loc[i_max, "cierre"]), 2), "fecha": s.loc[i_max, "fecha"].date().isoformat()}
    else:
        maximo = {"valor": RECORD_PREVIO[0], "fecha": RECORD_PREVIO[1]}
    intradia = None
    if "maximo" in s.columns and s["maximo"].max() > COTA_PREVIA:
        j = s["maximo"].idxmax()
        intradia = {"valor": round(float(s.loc[j, "maximo"]), 2), "fecha": s.loc[j, "fecha"].date().isoformat()}

    # Sesiones más fuertes del año en curso
    del_anio = s[(s["anio"] == hoy.year)].dropna(subset=["var_pct"])
    subidas = del_anio.nlargest(5, "var_pct")[["fecha", "cierre", "var_pct"]]
    caidas = del_anio.nsmallest(5, "var_pct")[["fecha", "cierre", "var_pct"]]

    def rent_desde(fecha_ref):
        previas = s[s["fecha"] <= fecha_ref]
        return None if previas.empty else round(float((ult["cierre"] / previas["cierre"].iloc[-1] - 1) * 100), 2)

    cierre_ant = fin_anio.get(hoy.year - 1)
    mes_ant = s[s["fecha"] < hoy.replace(day=1)]
    return {
        "fecha": hoy.date().isoformat(),
        "cierre": round(float(ult["cierre"]), 2),
        "variacion_dia_pct": round(float(ult["var_pct"]), 2),
        "rentabilidad_anio_pct": None if cierre_ant is None else round(float((ult["cierre"] / cierre_ant - 1) * 100), 2),
        "cierre_anio_anterior": None if cierre_ant is None else round(float(cierre_ant), 2),
        "rentabilidad_mes_pct": None if mes_ant.empty else round(float((ult["cierre"] / mes_ant["cierre"].iloc[-1] - 1) * 100), 2),
        "rentabilidad_12m_pct": rent_desde(hoy - pd.DateOffset(years=1)),
        "maximo_historico_cierre": maximo,
        "maximo_historico_intradia": intradia,
        "distancia_maximo_pct": round(float((ult["cierre"] / maximo["valor"] - 1) * 100), 2),
        "maximos_historicos_en_el_anio": int((nuevos["fecha"].dt.year == hoy.year).sum()),
        "fuente": "BME, cierres oficiales del IBEX 35",
        "_anual": anual, "_mensual": mensual, "_maximos": nuevos, "_subidas": subidas, "_caidas": caidas,
    }


# --------------------------------------------------------------------------- textos y tablas
def frase_resumen(r: dict) -> str:
    partes = [f"El IBEX 35 cerró el {_fecha_larga(r['fecha'])} en {_num(r['cierre'])} puntos "
              f"({_pct(r['variacion_dia_pct'])} en la sesión)."]
    x = r["rentabilidad_anio_pct"]
    if x is not None:
        anio = pd.Timestamp(r["fecha"]).year
        if x == 0:
            partes.append(f"En lo que va de {anio} está igual que al cierre de {anio - 1}.")
        else:
            partes.append(f"En lo que va de {anio} {'sube' if x > 0 else 'cae'} un {_num(abs(x))} %.")
    m = r["maximo_historico_cierre"]
    if m["fecha"] == r["fecha"]:
        partes.append("Es un nuevo máximo histórico al cierre.")
    else:
        partes.append(f"Su máximo histórico al cierre son {_num(m['valor'])} puntos, del {_fecha_larga(m['fecha'])}, "
                      f"y hoy está un {_num(abs(r['distancia_maximo_pct']))} % por debajo.")
    return " ".join(partes)


def _tabla(cabecera: list[str], filas: list[list[str]]) -> str:
    cab = "".join(f"<th>{c}</th>" for c in cabecera)
    cuerpo = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return f"<figure class=\"wp-block-table\"><table><thead><tr>{cab}</tr></thead><tbody>\n{cuerpo}\n</tbody></table></figure>"


def fragmento_wp(r: dict) -> str:
    def e(x) -> str:
        return html.escape(str(x)).replace("$", "&#36;")
    hoy = pd.Timestamp(r["fecha"])
    m = r["maximo_historico_cierre"]
    clave = [
        ["Último cierre", f"{_num(r['cierre'])} puntos ({_fecha(r['fecha'])})"],
        ["Variación en la sesión", _pct(r["variacion_dia_pct"])],
        [f"Rentabilidad en {hoy.year}", f"{_pct(r['rentabilidad_anio_pct'])} (cierre de {hoy.year - 1}: {_num(r['cierre_anio_anterior'])} puntos)"],
        [f"Rentabilidad en {MESES[hoy.month - 1]}", _pct(r["rentabilidad_mes_pct"])],
        ["Rentabilidad a 12 meses", _pct(r["rentabilidad_12m_pct"])],
        ["Máximo histórico al cierre", f"{_num(m['valor'])} puntos ({_fecha(m['fecha'])})"],
    ]
    if r["maximo_historico_intradia"]:
        mi = r["maximo_historico_intradia"]
        clave.append(["Máximo histórico intradía", f"{_num(mi['valor'])} puntos ({_fecha(mi['fecha'])})"])
    clave += [["Distancia al máximo histórico al cierre", _pct(r["distancia_maximo_pct"])],
              [f"Máximos históricos al cierre en {hoy.year}", str(r["maximos_historicos_en_el_anio"])]]
    t_clave = ("<figure class=\"wp-block-table\"><table><tbody>\n"
               + "\n".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in clave) + "\n</tbody></table></figure>")

    anual = r["_anual"].sort_values("anio", ascending=False)
    t_anual = _tabla(["Año", "IBEX 35", "Con dividendos"], [
        [f"{x.anio}" + (f" ({e(x.periodo)})" if x.periodo != "año completo" else ""), _pct(x.rentabilidad_pct), _pct(x.con_dividendos_pct)]
        for x in anual.itertuples()])

    mensual = r["_mensual"]
    anios = sorted(mensual["anio"].unique(), reverse=True)[:5]
    filas_m = []
    for a in anios:
        fila = [str(a)]
        for mes in range(1, 13):
            x = mensual[(mensual["anio"] == a) & (mensual["mes"] == mes)]
            fila.append(_pct(x["rentabilidad_pct"].iloc[0]) if len(x) else "")
        filas_m.append(fila)
    t_mensual = _tabla(["Año"] + MESES_CORTOS, filas_m)

    t_sub = _tabla(["Fecha", "Subida", "Cierre"], [[_fecha(x.fecha), _pct(x.var_pct), _num(x.cierre)] for x in r["_subidas"].itertuples()])
    t_caid = _tabla(["Fecha", "Caída", "Cierre"], [[_fecha(x.fecha), _pct(x.var_pct), _num(x.cierre)] for x in r["_caidas"].itertuples()])

    maxs = r["_maximos"][r["_maximos"]["fecha"].dt.year == hoy.year].sort_values("fecha", ascending=False)
    if len(maxs):
        bloque_max = (f"<p>En {hoy.year} el índice ha marcado {len(maxs)} {'máximo histórico' if len(maxs) == 1 else 'máximos históricos'} al cierre. Los más recientes:</p>\n"
                      + _tabla(["Fecha", "Cierre"], [[_fecha(x.fecha), _num(x.cierre)] for x in maxs.head(10).itertuples()]))
    else:
        bloque_max = f"<p>En {hoy.year} el índice no ha marcado ningún máximo histórico al cierre.</p>"

    return f"""<!-- ibex:inicio {r['fecha']} -->
<p><strong>Datos al cierre del {_fecha(r['fecha'])}.</strong> {e(frase_resumen(r))}</p>
{t_clave}
<h2>Rentabilidad del IBEX 35 año a año</h2>
<p>Variación entre el último cierre de cada año y el del año anterior. La columna con dividendos es la del IBEX 35 con Dividendos, que los reinvierte; solo para años completos.</p>
{t_anual}
<h2>Rentabilidad mes a mes</h2>
{t_mensual}
<h2>Máximos históricos de {hoy.year}</h2>
{bloque_max}
<h2>Las sesiones más fuertes de {hoy.year}</h2>
<p>Las cinco mayores subidas y las cinco mayores caídas del año en una sola sesión.</p>
{t_sub}
{t_caid}
<!-- ibex:fin -->"""


def pagina(r: dict, frag: str) -> str:
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Estadística del IBEX 35 de El Especulador",
        "description": "Último cierre, rentabilidad del año, máximos históricos y rentabilidad anual y mensual del IBEX 35, actualizados cada día hábil.",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de BME", "dateModified": r["fecha"],
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"datos/{n}.csv"}
                         for n in ["rentabilidad_anual", "rentabilidad_mensual", "maximos"]],
    }, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>El IBEX 35 en cifras: máximo histórico y rentabilidad | El Especulador</title>
<meta name="description" content="Último cierre del IBEX 35, rentabilidad en el año, máximo histórico y rentabilidad de cada año y cada mes, actualizados cada día hábil.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;white-space:nowrap}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style>
<script type="application/ld+json">{ld}</script>
</head><body>
<h1>El IBEX 35 en cifras</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/rentabilidad_anual.csv">rentabilidad anual</a> · <a href="datos/rentabilidad_mensual.csv">rentabilidad mensual</a> · <a href="datos/maximos.csv">máximos históricos</a> · <a href="datos/ultima.json">JSON</a>. Puedes reutilizar nuestros cálculos citando «El Especulador, a partir de datos de BME»; los cierres de origen son de BME y se rigen por sus condiciones. Historia y récords explicados: <a href="{PILAR}">histórico del IBEX 35</a>.</p>
<p class="pie">Cálculos de El Especulador con los cierres oficiales del IBEX 35 que publica BME; rentabilidades de años anteriores a 2022, de la serie verificada de El Especulador. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
"""


def ld_wp(r: dict) -> str:
    """Marcado Dataset (schema.org) en una sola línea, para la página de elespeculador.com."""
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Estadística del IBEX 35 de El Especulador",
        "description": "Último cierre, rentabilidad del año, máximos históricos y rentabilidad anual y mensual del IBEX 35, con los cierres oficiales de BME, actualizados cada día hábil.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de BME", "isBasedOn": "https://www.bolsasymercados.es/",
        "dateModified": r["fecha"],
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ["rentabilidad_anual", "rentabilidad_mensual", "maximos"]],
    }, ensure_ascii=False) + "</script>"


def con_ld(frag: str, ld: str) -> str:
    marca = "\n<!-- ibex:fin -->"
    assert frag.count(marca) == 1 and "$" not in ld
    return frag.replace(marca, "\n" + ld + marca)


def escribir(r: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    r["_anual"].to_csv(DATOS / "rentabilidad_anual.csv", index=False)
    r["_mensual"].to_csv(DATOS / "rentabilidad_mensual.csv", index=False)
    mx = r["_maximos"].copy()
    mx["fecha"] = mx["fecha"].dt.date
    mx.round(2).to_csv(DATOS / "maximos.csv", index=False)
    publico = {k: v for k, v in r.items() if not k.startswith("_")}
    publico["generado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    publico["licencia"] = "Sin licencia abierta: cierres de origen de BME, sujetos a sus condiciones. Cita: El Especulador, a partir de datos de BME"
    (DATOS / "ultima.json").write_text(json.dumps(publico, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento_wp(r)
    (SALIDA / "fragmento-wp.html").write_text(con_ld(frag, ld_wp(r)), encoding="utf-8")
    (SALIDA / "index.html").write_text(pagina(r, frag), encoding="utf-8")


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="CSV con columnas fecha,cierre[,maximo]")
    args = ap.parse_args()
    if args.local:
        s = pd.read_csv(args.local)
    else:
        from fuente import descargar
        s = descargar()
    s = validar(s)
    estado = DATOS / "ultima.json"
    previa = json.loads(estado.read_text(encoding="utf-8")).get("fecha") if estado.exists() else None
    if previa == s["fecha"].iloc[-1].date().isoformat() and not args.local:
        print(f"Sin cierre nuevo desde el {previa}: no se toca nada.")
        return 0
    r = calcular(s, pd.read_csv(HISTORICO))
    escribir(r)
    print(frase_resumen(r))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
