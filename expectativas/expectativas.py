"""Expectativas de los hogares españoles: inflación que perciben y que esperan, y lo que esperan de su casa, su sueldo, el paro y la hipoteca.

Indicador 20c del catálogo de Datos de El Especulador. Toma la encuesta de expectativas de los consumidores del
BCE (CES, conjunto `CES` del portal de datos: medianas ponderadas, mensual desde abril de 2020) para España, la
zona euro de la encuesta (once países), Alemania, Francia e Italia, y la compara con el IPC real del INE que ya
publica el indicador de ahorro (ahorro/datos/serie.csv, al lado de la salida). Publica en <salida>/:

  fragmento-wp.html   lectura del mes (inflación esperada a 12 meses frente a la zona euro y al IPC real, la
                      brecha de percepción, 3 y 5 años, incertidumbre), la tabla de las demás expectativas
                      (vivienda, ingresos, gasto, crecimiento, paro, hipoteca), gráfico de tres años y método,
                      entre <!-- expectativas:inicio HUELLA --> y <!-- expectativas:fin -->
  index.html          página propia de la salida
  datos/ultima.json   resumen versionado
  datos/serie.csv     todas las series mensuales (formato largo)

Sin predicción ni recomendación: la encuesta dice lo que esperan los hogares, no lo que pasará.

Uso:
  python expectativas/expectativas.py --salida docs/expectativas
  python expectativas/expectativas.py --salida docs/expectativas --local ces.csv --ipc ahorro_serie.csv --fecha 2026-11-18
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

VERSION = "1.0.1"
API = "https://data-api.ecb.europa.eu/service/data/CES/"
PORTAL = "https://data.ecb.europa.eu/data/datasets/CES"
AREAS = {"ES": "España", "Z18": "Zona euro (11 países de la encuesta)", "DE": "Alemania", "FR": "Francia", "IT": "Italia"}
VARIABLES = {  # código CES -> (nombre corto, unidad)
    "C1020": ("inflación percibida en los últimos 12 meses", "%"),
    "C1120": ("inflación esperada a 12 meses", "%"),
    "C1220": ("inflación esperada a 3 años", "%"),
    "E2020": ("inflación esperada a 5 años", "%"),
    "C1150_UNCERT": ("incertidumbre sobre la inflación a 12 meses (rango intercuartílico)", "puntos"),
    "C2120": ("precio de la vivienda a 12 meses", "%"),
    "C3220": ("ingresos del hogar a 12 meses", "%"),
    "C6120": ("gasto del hogar a 12 meses", "%"),
    "C4020": ("crecimiento económico a 12 meses", "%"),
    "C4031": ("tasa de paro esperada a 12 meses", "% de paro"),
    "C5111": ("tipo hipotecario esperado a 12 meses", "%"),
}
PRINCIPALES = ["C1120", "C1020", "C1220", "E2020", "C1150_UNCERT"]
OTRAS = ["C2120", "C3220", "C6120", "C4020", "C4031", "C5111"]
CLAVE = "M." + "+".join(AREAS) + ".ALL.T." + "+".join(VARIABLES) + ".NUM_VAR.WM"
PARAMS = {"format": "csvdata", "startPeriod": "2020-01-01"}
PAGINA_WP = "https://elespeculador.com/expectativas-de-los-hogares/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/expectativas/"
DIAS_AVISO, DIAS_FALLO = 75, 120
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
AVISOS: list[str] = []


class DatosRaros(Exception):
    """El portal no responde o los datos no tienen la forma esperada: mejor parar que publicar basura."""


# --------------------------------------------------------------------------- descarga y lectura
def descargar(esperas: list[int] | None = None, dormir=time.sleep) -> str:
    esperas = [15, 30, 60, 120] if esperas is None else esperas
    ultimo = None
    for intento in range(len(esperas) + 1):
        try:
            r = requests.get(API + CLAVE, params=PARAMS, timeout=(20, 120),
                             headers={"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "text/csv"})
            if r.status_code == 200 and "TIME_PERIOD" in r.text[:2000]:
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres, empieza por {r.text[:60]!r}"
        except requests.RequestException as e:
            ultimo = str(e)
        print(f"AVISO  descarga, intento {intento + 1} de {len(esperas) + 1}: {ultimo}", file=sys.stderr)
        if intento < len(esperas):
            dormir(esperas[intento])
    raise DatosRaros(f"No se pudo descargar la encuesta CES del portal del BCE tras {len(esperas) + 1} intentos: {ultimo}")


def leer(texto: str) -> pd.DataFrame:
    """CSV del portal (csvdata) -> DataFrame largo: mes (AAAA-MM), area, variable, valor."""
    df = pd.read_csv(io.StringIO(texto))
    for col in ("KEY", "TIME_PERIOD", "OBS_VALUE"):
        if col not in df.columns:
            raise DatosRaros(f"El CSV del portal no trae la columna {col}; columnas: {list(df.columns)[:12]}")

    def partes(clave: str) -> tuple[str | None, str | None]:
        p = str(clave).split(".")
        area = next((x for x in p if x in AREAS), None)
        var = next((x for x in p if x in VARIABLES), None)
        return area, var

    filas = []
    for clave, mes, valor in zip(df["KEY"], df["TIME_PERIOD"], pd.to_numeric(df["OBS_VALUE"], errors="coerce")):
        area, var = partes(clave)
        if area and var and pd.notna(valor) and isinstance(mes, str) and len(mes) >= 7:
            filas.append((mes[:7], area, var, float(valor)))
    out = pd.DataFrame(filas, columns=["mes", "area", "variable", "valor"]).drop_duplicates(["mes", "area", "variable"], keep="last")
    if out.empty:
        raise DatosRaros("El CSV del portal no trae ninguna observación de la encuesta")
    for var in ("C1120", "C1020"):
        if out[(out["area"] == "ES") & (out["variable"] == var)].empty:
            raise DatosRaros(f"El portal no ha devuelto la variable {var} de España")
    if (out["variable"].isin(["C1120", "C1020", "C1220", "E2020"]) & ((out["valor"] < -20) | (out["valor"] > 60))).any():
        raise DatosRaros("Hay expectativas de inflación fuera de rango (−20 % a 60 %)")
    return out.sort_values(["area", "variable", "mes"]).reset_index(drop=True)


def leer_ipc(ruta: Path | None) -> pd.Series | None:
    """IPC general interanual del INE desde la salida del indicador de ahorro (mes AAAA-MM -> %)."""
    if ruta is None or not ruta.exists():
        return None
    df = pd.read_csv(ruta)
    if not {"mes", "serie", "valor"} <= set(df.columns):
        AVISOS.append(f"{ruta} no tiene las columnas mes, serie, valor: sin IPC")
        return None
    ipc = df[df["serie"] == "ipc"].copy()
    if ipc.empty:
        AVISOS.append(f"{ruta} no trae la serie ipc")
        return None
    ipc["mes"] = ipc["mes"].astype(str).str[:7]
    s = pd.Series(pd.to_numeric(ipc["valor"], errors="coerce").values, index=ipc["mes"]).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


# --------------------------------------------------------------------------- cálculo
def _mes_menos(mes: str, n: int) -> str:
    a, m = int(mes[:4]), int(mes[5:7])
    m -= n
    while m <= 0:
        m += 12
        a -= 1
    return f"{a:04d}-{m:02d}"


def percentil(serie: pd.Series, valor: float) -> float:
    s = serie.dropna()
    return float((s <= valor).mean() * 100) if len(s) else float("nan")


def _serie(df: pd.DataFrame, area: str, var: str) -> pd.Series:
    s = df[(df["area"] == area) & (df["variable"] == var)].set_index("mes")["valor"].sort_index()
    return s


def _ficha(s: pd.Series, mes: str) -> dict | None:
    if s.empty or mes not in s.index:
        return None
    v = float(s.loc[mes])
    ant = s.get(_mes_menos(mes, 1))
    hace12 = s.get(_mes_menos(mes, 12))
    return {"valor": v, "mes": mes, "variacion_1m": round(v - float(ant), 1) if ant is not None and pd.notna(ant) else None,
            "variacion_12m": round(v - float(hace12), 1) if hace12 is not None and pd.notna(hace12) else None,
            "percentil": round(percentil(s, v), 1), "meses": int(len(s)), "desde": s.index[0], "max": float(s.max()), "mes_max": s.idxmax(), "min": float(s.min()), "mes_min": s.idxmin()}


def calcular(df: pd.DataFrame, ipc: pd.Series | None, hoy: date) -> dict:
    es12 = _serie(df, "ES", "C1120")
    mes = es12.index[-1]
    a, m = int(mes[:4]), int(mes[5:7])
    desfase = (hoy - date(a, m, 28)).days
    if desfase > DIAS_FALLO:
        raise DatosRaros(f"El último mes de la encuesta para España es {mes}: más de {DIAS_FALLO} días de desfase")
    if desfase > DIAS_AVISO:
        AVISOS.append(f"El último mes de la encuesta para España es {mes} ({desfase} días)")
    fichas = {}
    for area in AREAS:
        fichas[area] = {var: _ficha(_serie(df, area, var), mes) for var in VARIABLES}
        if area != "ES" and fichas[area]["C1120"] is None:
            AVISOS.append(f"{AREAS[area]}: sin expectativa a 12 meses en {mes}")
    ipc_mes, ipc_valor, brecha = None, None, None
    ipc_12m_antes = None
    if ipc is not None and len(ipc):
        ipc_mes = max(x for x in ipc.index if x <= mes) if any(x <= mes for x in ipc.index) else None
        if ipc_mes:
            ipc_valor = float(ipc.loc[ipc_mes])
            if ipc_mes == mes and fichas["ES"]["C1020"]:
                brecha = round(fichas["ES"]["C1020"]["valor"] - ipc_valor, 1)
        # qué esperaban hace 12 meses frente a lo que ha pasado: expectativa en mes-12 contra IPC de mes
        esperado_antes = es12.get(_mes_menos(mes, 12))
        if esperado_antes is not None and pd.notna(esperado_antes) and ipc_mes == mes:
            ipc_12m_antes = {"mes_expectativa": _mes_menos(mes, 12), "esperado": float(esperado_antes), "ipc_real": ipc_valor, "diferencia": round(float(esperado_antes) - ipc_valor, 1)}
    else:
        AVISOS.append("Sin IPC del INE al lado (ahorro/datos/serie.csv): la comparación con la inflación real no se publica")
    return {"mes": mes, "desfase_dias": desfase, "fichas": fichas, "ipc": {"mes": ipc_mes, "valor": ipc_valor}, "brecha_percepcion": brecha,
            "acierto_12m": ipc_12m_antes, "primer_mes": es12.index[0], "meses": int(len(es12))}


def huella(res: dict) -> str:
    base = {"version": VERSION, "mes": res["mes"], "es": {k: (v["valor"] if v else None) for k, v in res["fichas"]["ES"].items()},
            "ea": {k: (v["valor"] if v else None) for k, v in res["fichas"]["Z18"].items()}, "ipc": res["ipc"]}
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _mes_txt(mes: str | None) -> str:
    return f"{MESES[int(mes[5:7]) - 1]} de {mes[:4]}" if mes else "—"


def _v(x: float | None, dec: int = 1, signo: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{x:+.{dec}f}" if signo else f"{x:.{dec}f}"
    return s.replace(".", ",").replace("-", "−")


def _pp(x: float | None) -> str:
    return "—" if x is None else (_v(x, 1, True) + " p.p.")


def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def grafico_svg(df: pd.DataFrame, ipc: pd.Series | None, mes: str) -> str:
    """Inflación esperada a 12 meses (España y zona euro), percibida e IPC real, últimos 36 meses."""
    W, H, ml, mr, mt, mb = 720, 280, 40, 12, 10, 28
    desde = _mes_menos(mes, 35)
    series = {"esperada": _serie(df, "ES", "C1120"), "zona euro": _serie(df, "Z18", "C1120"), "percibida": _serie(df, "ES", "C1020")}
    if ipc is not None:
        series["IPC real"] = ipc
    series = {k: s[(s.index >= desde) & (s.index <= mes)] for k, s in series.items()}
    series = {k: s for k, s in series.items() if len(s)}
    if not series:
        return ""
    todos = pd.concat(series.values())
    y0, y1 = min(0.0, float(todos.min()) - 0.5), float(todos.max()) + 0.5
    meses = sorted({m for s in series.values() for m in s.index})
    pos = {m: i for i, m in enumerate(meses)}
    def X(m): return ml + pos[m] / max(len(meses) - 1, 1) * (W - ml - mr)
    def Y(v): return mt + (1 - (v - y0) / max(y1 - y0, 1e-9)) * (H - mt - mb)
    partes = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Inflación esperada, percibida y real en España, tres años" xmlns="http://www.w3.org/2000/svg">',
              '<style>.eje{font:11px sans-serif;fill:#5b6675}.lin{fill:none;stroke-width:1.6}</style>']
    for i in range(5):
        v = y0 + (y1 - y0) * i / 4
        partes.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{W - mr}" y2="{Y(v):.1f}" stroke="#e3e8ef"/>'
                      f'<text class="eje" x="{ml - 4}" y="{Y(v) + 4:.1f}" text-anchor="end">{_v(v, 1)}</text>')
    for m in meses:
        if m.endswith("-01"):
            partes.append(f'<text class="eje" x="{X(m):.1f}" y="{H - 8}" text-anchor="middle">{m[:4]}</text>')
    colores = {"esperada": "#1f4e8c", "zona euro": "#9aa5b1", "percibida": "#e0a44c", "IPC real": "#c0392b"}
    for n, s in series.items():
        puntos = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in s.items())
        partes.append(f'<polyline class="lin" stroke="{colores[n]}" points="{puntos}"/>')
    x = ml + 6
    for n in series:
        partes.append(f'<text class="eje" x="{x}" y="{mt + 14}" fill="{colores[n]}">{n}</text>')
        x += 90
    partes.append("</svg>")
    return "".join(partes)


def fragmento(res: dict, df: pd.DataFrame, ipc: pd.Series | None, fecha_pub: str) -> str:
    es, ea = res["fichas"]["ES"], res["fichas"]["Z18"]
    mes = res["mes"]
    e12 = es["C1120"]
    frase = (f"En {_mes_txt(mes)}, el hogar español mediano esperaba una inflación del <strong>{_v(e12['valor'])} %</strong> para los doce meses siguientes"
             + (f" ({_pp(e12['variacion_1m'])} respecto al mes anterior; {_pp(e12['variacion_12m'])} respecto a un año antes)" if e12["variacion_1m"] is not None else "")
             + (f", frente al {_v(ea['C1120']['valor'])} % del hogar mediano de la zona euro" if ea["C1120"] else "") + ". ")
    if es["C1020"]:
        frase += f"La inflación que decía haber sufrido en los doce meses anteriores era del {_v(es['C1020']['valor'])} %"
        if res["ipc"]["valor"] is not None and res["ipc"]["mes"] == mes:
            frase += f", cuando el IPC del INE de ese mes fue del {_v(res['ipc']['valor'])} %: una brecha de percepción de {_pp(res['brecha_percepcion'])}"
        frase += ". "
    if es["C1220"] and es["E2020"]:
        frase += f"A tres años esperaba un {_v(es['C1220']['valor'])} % y a cinco, un {_v(es['E2020']['valor'])} %. "
    frase += f"Es el percentil {e12['percentil']:.0f} de la expectativa a doce meses desde {_mes_txt(e12['desde'])} (máximo {_v(e12['max'])} % en {_mes_txt(e12['mes_max'])}; mínimo {_v(e12['min'])} % en {_mes_txt(e12['mes_min'])})."
    filas = []
    for area, nombre in AREAS.items():
        f = res["fichas"][area]
        if not f["C1120"]:
            continue
        filas.append([f"<strong>{nombre}</strong>" if area == "ES" else nombre, _v(f["C1120"]["valor"]), _pp(f["C1120"]["variacion_1m"]), _pp(f["C1120"]["variacion_12m"]),
                      _v(f["C1020"]["valor"]) if f["C1020"] else "—", _v(f["C1220"]["valor"]) if f["C1220"] else "—", _v(f["E2020"]["valor"]) if f["E2020"] else "—",
                      _v(f["C1150_UNCERT"]["valor"]) if f["C1150_UNCERT"] else "—"])
    otras = []
    for var in OTRAS:
        f = es[var]
        if not f:
            continue
        nombre, unidad = VARIABLES[var]
        otras.append([nombre.capitalize(), _v(f["valor"]) + (" %" if unidad.startswith("%") else ""), _pp(f["variacion_1m"]), _pp(f["variacion_12m"]),
                      _v(ea[var]["valor"]) + (" %" if unidad.startswith("%") else "") if ea[var] else "—"])
    partes = [f"<!-- expectativas:inicio {res['huella']} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)} con la encuesta del BCE de {_mes_txt(mes)} (medianas ponderadas de las respuestas de los hogares).</p>',
              "<p>" + frase + "</p>",
              "<h2>España frente a la zona euro y las grandes economías</h2>",
              _tabla(["Hogares de", "Esperan a 12 meses", "1 mes", "12 meses", "Perciben (últimos 12 meses)", "A 3 años", "A 5 años", "Incertidumbre (p.p.)"], filas)]
    if res["acierto_12m"]:
        ac = res["acierto_12m"]
        partes.append(f"<p>Lo que esperaban hace un año frente a lo que ha pasado: en {_mes_txt(ac['mes_expectativa'])} el hogar mediano esperaba un {_v(ac['esperado'])} % "
                      f"y el IPC de {_mes_txt(mes)} ha sido del {_v(ac['ipc_real'])} % ({_pp(ac['diferencia'])}).</p>")
    partes += ["<h2>Lo demás que esperan los hogares españoles</h2>",
               _tabla(["A doce meses", "España", "1 mes", "12 meses", "Zona euro"], otras),
               "<h2>Los últimos tres años</h2>",
               '<figure class="wp-block-image">' + grafico_svg(df, ipc, mes) + "</figure>",
               '<p class="has-small-font-size">Inflación esperada a doce meses por los hogares españoles y por los de la zona euro, inflación percibida e IPC general interanual del INE, por mes de encuesta.</p>',
               '<h2 id="metodo">Qué mide y cómo se hace</h2>'
               "<p>La encuesta de expectativas de los consumidores del BCE (CES) pregunta cada mes a unos 19.000 hogares de once países de la zona euro, varios miles en "
               "España, qué inflación creen haber sufrido, cuál esperan a uno, tres y cinco años, y qué esperan del precio de su vivienda, de sus ingresos, de su gasto, "
               "del crecimiento, del paro y del tipo de su hipoteca. El Especulador toma las medianas ponderadas que publica el BCE en su portal de datos, sin "
               "modificarlas, y las compara con el IPC general interanual del INE del mismo mes (brecha de percepción) y con la expectativa de doce meses antes "
               "(acierto). Las variaciones son en puntos porcentuales; el percentil es «débil» (porcentaje de meses con un valor igual o inferior) desde el inicio de la "
               "serie. Esta página describe lo que esperan los hogares y cuánto acertaron; no predice la inflación ni recomienda nada.</p>"
               f'<p class="has-small-font-size">Fuente: BCE, <a href="{PORTAL}">Consumer Expectations Survey (conjunto CES)</a>, series mensuales desde {_mes_txt(res["primer_mes"])}; '
               "INE, IPC general, variación anual (licencia CC BY 4.0: «Elaboración propia con datos extraídos del sitio web del INE: www.ine.es»). Reutilización según la "
               "política del SEBC, citando la fuente y sin modificar las series; la brecha, el acierto, las variaciones y los percentiles son cálculo de El Especulador "
               "(CC BY 4.0). Contenido informativo y educativo; no es asesoramiento financiero ni recomendación de inversión.</p>",
               "<!-- expectativas:fin -->"]
    return "\n".join(partes)


def _f(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Expectativas de los hogares españoles: inflación percibida y esperada, vivienda, ingresos, paro e hipoteca (El Especulador)",
        "description": "Medianas de la encuesta de expectativas de los consumidores del BCE para España y la zona euro, comparadas con el IPC del INE, mensual desde 2020.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de la Consumer Expectations Survey del BCE y del IPC del INE", "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": PORTAL, "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/serie.csv"},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{PAGES}datos/ultima.json"}],
    }, ensure_ascii=False) + "</script>"


def escribir(df: pd.DataFrame, ipc: pd.Series | None, res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    cambia = antes.get("huella") != res["huella"]
    completos = all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/serie.csv"))
    if not cambia and not forzar and completos:
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    largo = df.copy()
    largo["nombre"] = largo["variable"].map(lambda v: VARIABLES[v][0])
    largo.sort_values(["area", "variable", "mes"]).to_csv(dd / "serie.csv", index=False)
    previo.write_text(json.dumps({**res, "version": VERSION, "fecha_publicacion": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "variables": {k: v[0] for k, v in VARIABLES.items()}, "areas": AREAS,
                                  "fuente": "BCE, Consumer Expectations Survey (CES), medianas ponderadas; INE, IPC general interanual",
                                  "condiciones": "Series reproducidas sin modificar, citando la fuente (política del SEBC; INE CC BY 4.0). Brecha, acierto, variaciones y "
                                                 "percentiles de El Especulador (CC BY 4.0). Contenido informativo; no es asesoramiento financiero."},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(res, df, ipc, fecha_pub)
    marca = "\n<!-- expectativas:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expectativas de los hogares españoles: inflación, vivienda, ingresos, paro e hipoteca | El Especulador</title>
<meta name="description" content="Qué inflación perciben y esperan los hogares españoles según la encuesta del BCE, comparada con el IPC del INE, y qué esperan de su vivienda, sus ingresos, el paro y su hipoteca.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:980px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} table{{border-collapse:collapse;width:100%;font-size:.92rem}} th,td{{border-bottom:1px solid #e3e8ef;padding:4px 6px;text-align:left}}
a{{color:#1f4e8c}} .has-small-font-size{{color:#5b6675;font-size:.85rem}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Expectativas de los hogares españoles</h1>
{cuerpo}
<h3>Datos abiertos</h3>
<p>CSV: <a href="datos/serie.csv">todas las series mensuales</a> · <a href="datos/ultima.json">JSON</a>. Fuente: BCE (CES) e INE; cálculos de El Especulador (CC BY 4.0). Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p class="pie">Comprobado el {_f(hoy.isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--local", help="CSV del portal ya descargado (pruebas)")
    ap.add_argument("--ipc", help="serie.csv del indicador de ahorro (por defecto, ../ahorro/datos/serie.csv respecto a --salida)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else date.today()
    salida = Path(a.salida)
    texto = Path(a.local).read_text(encoding="utf-8") if a.local else descargar()
    df = leer(texto)
    ruta_ipc = Path(a.ipc) if a.ipc else salida.resolve().parent / "ahorro" / "datos" / "serie.csv"
    ipc = leer_ipc(ruta_ipc)
    res = calcular(df, ipc, hoy)
    res["huella"] = huella(res)
    cambia = escribir(df, ipc, res, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    es = res["fichas"]["ES"]
    print(f"Encuesta de {res['mes']}: España espera {es['C1120']['valor']} % a 12 meses, percibe {es['C1020']['valor'] if es['C1020'] else '—'} %; "
          f"IPC {res['ipc']['valor']} ({res['ipc']['mes']}); zona euro {res['fichas']['Z18']['C1120']['valor'] if res['fichas']['Z18']['C1120'] else '—'} %. "
          f"{'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
