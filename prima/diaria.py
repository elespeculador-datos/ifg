"""Prima de riesgo diaria España-Alemania a diez años: la sección «día a día» de la página de la prima (9362).

España: tipo medio diario de las operaciones simples al contado con bonos y obligaciones del Estado no segregados a
10 años en el mercado secundario (Banco de España, cuadro ti_1_3, serie D_G0B1F0ZP). Es la media del mercado a ese
plazo, no exactamente el bono de referencia.
Alemania: rentabilidad diaria del Bund a 10 años más reciente (Deutsche Bundesbank, serie
BBSSY.D.REN.EUR.A630.000000WT1010.A), que el Bundesbank calcula con su precio de referencia diario.

Licencias: Banco de España (verificada el 02/11/2026) y Bundesbank (política de reutilización del SEBC, verificada el
24/11/2026). Reutilización libre citando la fuente y sin modificar las series; el diferencial es cálculo propio.

Validación (25/11/2026) frente a la media mensual de Eurostat que ya publica la página: 36 meses, de noviembre de
2023 a octubre de 2026; correlación 0,997, diferencia media −1,8 pb, máxima 5,1 pb. Cada pasada repite la comparación
y, si la diferencia media pasa de CONTROL_PB, la sección diaria no se publica (y queda aviso). Si el dato tiene más de
DIAS_SIN_PUBLICAR días, tampoco. La parte mensual de la página no depende de nada de esto.
"""
from __future__ import annotations

import csv
import io
import time
from datetime import date

import pandas as pd

URL_BDE = "https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/ti_1_3.csv"
SERIE_BDE = "D_G0B1F0ZP"
CUADRO_BDE = "https://www.bde.es/webbe/es/estadisticas/temas/tipos-interes.html"
URL_BUND = "https://api.statistiken.bundesbank.de/rest/data/BBSSY/D.REN.EUR.A630.000000WT1010.A?format=csv&lang=en&startPeriod={desde}"
SERIE_BUND = "BBSSY.D.REN.EUR.A630.000000WT1010.A"
DESDE = "2015-01-01"
CONTROL_MESES = 36
CONTROL_MINIMO = 12
CONTROL_PB = 10.0
DIAS_AVISO, DIAS_SIN_PUBLICAR = 7, 15
MESES_BDE = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
CABECERAS = {"User-Agent": "ElEspeculadorPrima (+https://elespeculador.com)"}


def descargar(url: str, codificacion: str, intentos: int = 3, dormir=time.sleep) -> str:
    import requests
    ultimo = None
    for i in range(intentos):
        try:
            r = requests.get(url, headers=CABECERAS, timeout=60)
            r.raise_for_status()
            return r.content.decode(codificacion)
        except Exception as e:  # red: se reintenta; si no, la sección diaria no sale y la mensual sigue
            ultimo = e
            if i < intentos - 1:
                dormir(5 * (i + 1))
    raise RuntimeError(f"{url}: {type(ultimo).__name__}: {str(ultimo)[:120]}")


def leer_bde(texto: str) -> pd.Series:
    """Serie diaria del cuadro ti_1_3 del Banco de España, buscada por su código (no por la posición de la columna)."""
    filas = list(csv.reader(io.StringIO(texto)))
    cab = next((f for f in filas if f and f[0].strip().upper().startswith("C") and SERIE_BDE in f), None)
    if cab is None:
        raise ValueError(f"el cuadro ti_1_3 no trae la serie {SERIE_BDE}")
    col = cab.index(SERIE_BDE)
    datos = {}
    for f in filas:
        partes = f[0].split() if f else []
        if len(partes) != 3 or partes[1].upper() not in MESES_BDE or len(f) <= col:
            continue
        v = f[col].strip()
        try:
            datos[pd.Timestamp(int(partes[2]), MESES_BDE[partes[1].upper()], int(partes[0]))] = float(v)
        except ValueError:  # «_» o «-»: sin dato ese día
            continue
    if not datos:
        raise ValueError(f"la serie {SERIE_BDE} no trae ningún dato")
    return pd.Series(datos).sort_index()


def leer_bund(texto: str) -> pd.Series:
    """Serie diaria del Bundesbank (CSV de su API). «.» es «sin dato»."""
    datos = {}
    for f in csv.reader(io.StringIO(texto.lstrip("﻿"))):
        if len(f) < 2 or len(f[0]) != 10 or f[0][4] != "-":
            continue
        try:
            datos[pd.Timestamp(f[0])] = float(f[1])
        except ValueError:
            continue
    if not datos:
        raise ValueError(f"la serie {SERIE_BUND} no trae ningún dato")
    return pd.Series(datos).sort_index()


def _valor_hasta(s: pd.Series, f: pd.Timestamp) -> float | None:
    a = s[s.index <= f]
    return float(a.iloc[-1]) if len(a) else None


def calcular(es: pd.Series, de: pd.Series, mensual: pd.Series, hoy: date) -> tuple[dict | None, pd.DataFrame, list[str]]:
    """(resumen o None si no debe publicarse, serie diaria común, avisos). `mensual`: prima España-Alemania de Eurostat
    (puntos básicos, índice en el primer día de cada mes)."""
    avisos: list[str] = []
    comun = pd.concat([es.rename("es"), de.rename("de")], axis=1, join="inner").dropna()
    comun = comun[comun.index >= pd.Timestamp(DESDE)]
    comun["pb"] = ((comun["es"] - comun["de"]) * 100).round(1)
    if len(comun) < 2:
        return None, comun, ["Prima diaria: menos de dos días con dato de los dos países; no se publica"]
    pb = comun["pb"]
    f = pb.index[-1]
    m = pb.groupby(pb.index.to_period("M")).mean()
    m.index = m.index.to_timestamp()
    cmp = pd.concat([m.rename("diaria"), mensual.rename("eurostat")], axis=1, join="inner").dropna()
    cmp = cmp[cmp.index < f.to_period("M").to_timestamp()].tail(CONTROL_MESES)  # solo meses completos
    if len(cmp) < CONTROL_MINIMO:
        return None, comun, [f"Prima diaria: solo {len(cmp)} meses para compararla con Eurostat (mínimo {CONTROL_MINIMO}); no se publica"]
    dif = cmp["diaria"] - cmp["eurostat"]
    control = {"meses": len(cmp), "desde": cmp.index[0].strftime("%Y-%m"), "hasta": cmp.index[-1].strftime("%Y-%m"),
               "dif_media_pb": round(float(dif.mean()), 1), "dif_max_pb": round(float(dif.abs().max()), 1),
               "correlacion": None}
    corr = cmp["diaria"].corr(cmp["eurostat"])
    if not pd.isna(corr):
        control["correlacion"] = round(float(corr), 3)
    if abs(control["dif_media_pb"]) > CONTROL_PB:
        return None, comun, [f"Prima diaria: su media mensual se aparta {control['dif_media_pb']} pb de la de Eurostat "
                             f"({control['desde']} a {control['hasta']}); no se publica hasta revisarlo"]
    edad = (hoy - f.date()).days
    if edad > DIAS_SIN_PUBLICAR:
        return None, comun, [f"Prima diaria: el último dato común es del {f.date()} ({edad} días); no se publica"]
    if edad > DIAS_AVISO:
        avisos.append(f"Prima diaria: el último dato común es del {f.date()} ({edad} días)")
    ultimo = float(pb.iloc[-1])
    v12 = pb[pb.index > f - pd.Timedelta(days=365)]
    def var(dias: int) -> float | None:
        x = _valor_hasta(pb.iloc[:-1], f - pd.Timedelta(days=dias)) if dias else float(pb.iloc[-2])
        return None if x is None else round(ultimo - x, 1)
    res = {"fecha": f.date().isoformat(), "pb": round(ultimo, 1), "es": round(float(comun["es"].iloc[-1]), 3), "de": round(float(comun["de"].iloc[-1]), 2),
           "fecha_anterior": pb.index[-2].date().isoformat(), "var_sesion": var(0), "var_semana": var(7), "var_mes": var(30),
           "max_12m": round(float(v12.max()), 1), "fecha_max_12m": v12.idxmax().date().isoformat(),
           "min_12m": round(float(v12.min()), 1), "fecha_min_12m": v12.idxmin().date().isoformat(),
           "percentil": round(100.0 * float((pb <= ultimo).mean()), 0), "desde": pb.index[0].date().isoformat(), "dias": int(len(pb)),
           "control": control}
    return res, comun, avisos


def seccion(d: dict, f, v, dif) -> str:
    """HTML de la sección diaria. `f`, `v` y `dif` son los formateadores de fecha, número y variación de prima.py."""
    frase = (f"<p>El {f(d['fecha'])}, último día con dato, la prima de riesgo España-Alemania a diez años fue de "
             f"<strong>{v(d['pb'])} puntos básicos</strong>: el bono español rendía de media el {v(d['es'], 3)} % en el mercado secundario y el "
             f"Bund alemán, el {v(d['de'], 2)} %. Respecto a la sesión anterior ({f(d['fecha_anterior'])}) ha variado {dif(d['var_sesion'])} puntos básicos")
    if d["var_semana"] is not None:
        frase += f"; en una semana, {dif(d['var_semana'])}"
    if d["var_mes"] is not None:
        frase += f"; en un mes, {dif(d['var_mes'])}"
    frase += (f". En los últimos doce meses se ha movido entre {v(d['min_12m'])} puntos básicos ({f(d['fecha_min_12m'])}) y "
              f"{v(d['max_12m'])} ({f(d['fecha_max_12m'])}). Desde {d['desde'][:4]}, ese dato está en el percentil {v(d['percentil'], 0)} "
              f"(ha estado igual o más baja el {v(d['percentil'], 0)} % de los días).</p>")
    c = d["control"]
    nota = (f'<p class="has-small-font-size">Dato diario: tipo medio de las operaciones con bonos y obligaciones del Estado a diez años '
            f"en el mercado secundario (Banco de España) frente a la rentabilidad del Bund a diez años de referencia (Deutsche Bundesbank). "
            f"No es exactamente el bono español de referencia, así que puede diferir unos puntos básicos de otras fuentes: en los últimos "
            f"{c['meses']} meses, su media mensual se ha apartado de la de Eurostat {v(abs(c['dif_media_pb']))} puntos básicos de media "
            f"(como mucho, {v(c['dif_max_pb'])}). El Banco de España lo publica con uno o dos días hábiles de retraso.</p>")
    return "<h2>La prima, día a día</h2>\n" + frase + "\n" + nota
