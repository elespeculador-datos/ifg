# -*- coding: utf-8 -*-
"""
Oscilador Geopolítico 0.10.1 · capa de publicación sobre el cálculo 0.10.0.

QUÉ ES
    El índice que hasta la versión 0.10.0 se publicó como «Índice de Fricción
    Global» pasa a llamarse Oscilador Geopolítico (nombre decidido por Federico
    el 20/11/2026; versión 0.10.1 elegida el 25/11/2026). La 0.10.1 NO cambia
    el cálculo: mismo código, mismos componentes, misma escala y los mismos
    valores que la 0.10.0, sesión a sesión. Cambian el nombre, los tramos (por
    dirección y con histéresis) y las direcciones de publicación. Las reglas
    están en CONGELADO-0.10.1.md.

QUÉ HACE
    Lee lo que publicar_diario.py ya ha escrito y verificar_estabilidad.py ha
    dado por bueno en docs/:
        docs/ifg_serie.csv        serie completa publicada
        docs/ifg.json             foto del día
        docs/ifg_serie_12m.json   doce meses para el gráfico
    y escribe en docs/oscilador-geo/:
        oscilador-geo.json             foto del día del Oscilador
        oscilador-geo_serie_12m.json   doce meses del Oscilador
        oscilador-geo_serie.csv        serie completa con el tramo nuevo (archivo, no se publica)

    No recalcula ni cambia ningún valor. Si algo no cuadra sale con error y no
    escribe nada. El script diario lo llama DESPUÉS de publicar /ifg/, así que
    un fallo aquí nunca impide la publicación del IFG.

TRAMOS (regla R7, decidida el 20/11/2026)
    Alivio fuerte [0, 20) · Alivio [20, 40) · Estable [40, 60) ·
    Presión [60, 80) · Presión fuerte [80, 100].
    Histéresis: una sesión conserva el tramo de la anterior mientras su valor
    no quede más de 2 puntos por fuera de los límites de ese tramo. Sin sesión
    anterior con dato, el tramo es el que corresponde al valor.
    Lo cerrado no se toca: el tramo de una sesión que ya se publicó como
    definitiva se conserva tal cual en las pasadas siguientes.

Uso (desde /home/smpro/ifg, con el venv del proyecto):
    python oscilador.py              escribe docs/oscilador-geo/
    python oscilador.py --comprobar  calcula y comprueba, sin escribir
    python oscilador.py --resumen    además, reparto de tramos de toda la serie

Dependencias: pandas (las del proyecto). Python 3.10 o posterior.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile

import pandas as pd

# ---------------------------------------------------------------------------
# Reglas congeladas de la 0.10.1 (ver CONGELADO-0.10.1.md). No se tocan sin
# numerar otra versión.
# ---------------------------------------------------------------------------
VERSION = "0.10.1"
VERSION_CALCULO = "0.10.0"
NOMBRE = "Oscilador Geopolítico"
NOMBRE_ANTERIOR = ("Hasta la versión 0.10.0 este índice se publicó como "
                   "Índice de Fricción Global.")
URL_FICHA = "https://elespeculador.com/indices/oscilador-geopolitico/"
LICENCIA = ("Consulta y cita. Sin licencia de reutilización comercial ni de "
            "redistribución. Ver " + URL_FICHA + "#licencia")

TRAMOS = [
    (0, 20, "Alivio fuerte"),
    (20, 40, "Alivio"),
    (40, 60, "Estable"),
    (60, 80, "Presión"),
    (80, 101, "Presión fuerte"),
]
HISTERESIS = 2.0
SIN_DATO = "sin dato"
LIMITES = {nombre: (bajo, alto) for bajo, alto, nombre in TRAMOS}

# Textos públicos de la foto del día. Los lee el plugin de la web (2.0.1) para
# la entradilla de la ficha y la leyenda del desglose. Pasan por Cumplimiento.
LECTURA = (
    "Mide si los precios más sensibles a la tensión geopolítica (energía, gas, "
    "trigo, navieras de crudo, activos refugio, defensa europea, transporte "
    "aéreo, volatilidad del crudo y prima de crédito de la zona euro) se mueven "
    "en la dirección de más tensión o de menos, frente a su comportamiento "
    "reciente. Incluye además el flujo de noticias de conflicto y el índice de "
    "riesgo geopolítico de Caldara e Iacoviello. El 50 es neutral: por encima, "
    "presión; por debajo, alivio. No mide el miedo bursátil."
)
LEYENDA_DESGLOSE = ("Aportación de cada componente al valor de hoy. A la "
                    "derecha, más presión; a la izquierda, más alivio.")
# Política de revisiones, sin remitir a ficheros que no están publicados en
# datos.elespeculador.com (revisión de Cumplimiento del 25/11/2026).
REVISIONES = ("Un valor definitivo no se revisa nunca. Un valor provisional, al "
              "que le falta algún componente, queda abierto cinco sesiones por "
              "si llega el dato que falta; toda corrección queda registrada.")

# ---------------------------------------------------------------------------
# Rutas (relativas a /home/smpro/ifg)
# ---------------------------------------------------------------------------
DIR_DOCS = "docs"
DIR_SALIDA = os.path.join(DIR_DOCS, "oscilador-geo")
ENT_SERIE = os.path.join(DIR_DOCS, "ifg_serie.csv")
ENT_FOTO = os.path.join(DIR_DOCS, "ifg.json")
ENT_12M = os.path.join(DIR_DOCS, "ifg_serie_12m.json")
SAL_FOTO = os.path.join(DIR_SALIDA, "oscilador-geo.json")
SAL_12M = os.path.join(DIR_SALIDA, "oscilador-geo_serie_12m.json")
SAL_SERIE = os.path.join(DIR_SALIDA, "oscilador-geo_serie.csv")

# Los valores se publican con dos decimales: dos cifras que deberían ser la
# misma pueden diferir como mucho en el redondeo.
TOLERANCIA = 0.005 + 1e-9


class ErrorOscilador(Exception):
    """Algo no cuadra: no se escribe nada."""


# ---------------------------------------------------------------------------
# Tramos
# ---------------------------------------------------------------------------
def es_nulo(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def tramo_por_valor(v: float) -> str:
    """Tramo que corresponde al valor, sin histéresis."""
    for bajo, alto, nombre in TRAMOS:
        if bajo <= v < alto:
            return nombre
    return TRAMOS[0][2] if v < TRAMOS[0][0] else TRAMOS[-1][2]


def paso_histeresis(anterior: str | None, v) -> str:
    """
    Tramo de una sesión sabiendo el de la anterior. Se conserva el anterior
    mientras el valor no quede más de HISTERESIS puntos por fuera de sus
    límites: con «Alivio» (20-40), un 41,5 o un 42,0 siguen en Alivio y un
    42,01 pasa a Estable; un 18,0 sigue en Alivio y un 17,99 pasa a Alivio
    fuerte.
    """
    if es_nulo(v):
        return SIN_DATO
    v = float(v)
    nuevo = tramo_por_valor(v)
    if anterior in LIMITES and nuevo != anterior:
        bajo, alto = LIMITES[anterior]
        if bajo - HISTERESIS <= v <= alto + HISTERESIS:
            return anterior
    return nuevo


def calcular_tramos(valores: pd.Series, fijados: dict | None = None) -> pd.Series:
    """
    Tramos de toda la serie, de la primera sesión a la última. `fijados`
    {fecha: tramo} son tramos ya publicados de sesiones cerradas: se respetan
    y la histéresis sigue a partir de ellos.
    """
    fijados = fijados or {}
    salida, actual = [], None
    for fecha, v in valores.items():
        t = fijados[fecha] if fecha in fijados else paso_histeresis(actual, v)
        salida.append(t)
        actual = None if t == SIN_DATO else t
    return pd.Series(salida, index=valores.index, name="tramo")


# ---------------------------------------------------------------------------
# Lectura y comprobaciones
# ---------------------------------------------------------------------------
def leer_json(ruta: str) -> dict:
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        raise ErrorOscilador(f"no se puede leer {ruta}: {e}") from e


def leer_serie(ruta: str = ENT_SERIE) -> pd.DataFrame:
    try:
        s = pd.read_csv(ruta, index_col=0)
    except Exception as e:  # noqa: BLE001
        raise ErrorOscilador(f"no se puede leer {ruta}: {e}") from e
    s.index = s.index.astype(str)
    faltan = {"ifg", "estado"} - set(s.columns)
    if faltan:
        raise ErrorOscilador(f"faltan columnas {sorted(faltan)} en {ruta}")
    if s.empty:
        raise ErrorOscilador(f"{ruta} está vacía")
    if s.index.duplicated().any():
        raise ErrorOscilador(f"fechas repetidas en {ruta}")
    if not s.index.is_monotonic_increasing:
        raise ErrorOscilador(f"{ruta} no está en orden de fechas")
    s["estado"] = s["estado"].astype(str)
    return s


def es_cerrada(estado: str) -> bool:
    return str(estado).startswith("definitivo")


def tramos_fijados(serie: pd.DataFrame, ruta_previa: str = SAL_SERIE) -> dict:
    """
    Tramos de las sesiones que ya se publicaron cerradas en una pasada
    anterior. Comprueba de paso que su valor no ha cambiado: el IFG no mueve lo
    cerrado (verificar_estabilidad.py) y, si pasara, aquí se para.
    """
    if not os.path.exists(ruta_previa):
        return {}
    try:
        previa = pd.read_csv(ruta_previa, index_col=0)
    except Exception as e:  # noqa: BLE001
        raise ErrorOscilador(f"no se puede leer {ruta_previa}: {e}") from e
    previa.index = previa.index.astype(str)
    fijados = {}
    for fecha, fila in previa.iterrows():
        if not es_cerrada(fila.get("estado", "")):
            continue
        if fecha not in serie.index:
            raise ErrorOscilador(f"la sesión cerrada {fecha} ya no está en la serie del IFG")
        v_nuevo, v_previo = serie.at[fecha, "ifg"], fila.get("valor")
        if es_nulo(v_nuevo) != es_nulo(v_previo) or (
                not es_nulo(v_nuevo) and abs(float(v_nuevo) - float(v_previo)) > 1e-9):
            raise ErrorOscilador(
                f"la sesión cerrada {fecha} ha cambiado de valor ({v_previo} → {v_nuevo})")
        fijados[fecha] = str(fila["tramo"])
    return fijados


# ---------------------------------------------------------------------------
# Construcción de las salidas
# ---------------------------------------------------------------------------
def escala() -> list[dict]:
    return [{"desde": bajo, "hasta": min(alto, 100), "nombre": nombre}
            for bajo, alto, nombre in TRAMOS]


def construir_foto(foto_ifg: dict, serie: pd.DataFrame, tramos: pd.Series) -> dict:
    fecha = foto_ifg.get("fecha")
    if fecha != serie.index[-1]:
        raise ErrorOscilador(
            f"la foto del IFG es de {fecha} y la serie acaba en {serie.index[-1]}")
    v_serie = serie["ifg"].iloc[-1]
    if es_nulo(v_serie) or abs(float(foto_ifg.get("valor")) - float(v_serie)) > TOLERANCIA:
        raise ErrorOscilador(
            f"el valor de la foto ({foto_ifg.get('valor')}) no es el de la serie ({v_serie})")
    salida = {
        "indice": NOMBRE,
        "fecha": fecha,
        "version": VERSION,
        "valor": foto_ifg.get("valor"),
        "valor_crudo": foto_ifg.get("valor_crudo"),
        "valor_tendencia": foto_ifg.get("valor_tendencia"),
        "variacion": foto_ifg.get("variacion"),
        "tramo": tramos.iloc[-1],
        "cobertura": foto_ifg.get("cobertura"),
        "parcial": foto_ifg.get("parcial"),
        "motores": foto_ifg.get("motores"),
        "componentes_activos": foto_ifg.get("componentes_activos"),
        "estado_dato": foto_ifg.get("estado_dato"),
        "faltan": foto_ifg.get("faltan"),
        "lectura": LECTURA,
        "leyenda_desglose": LEYENDA_DESGLOSE,
        "escala": escala(),
        "histeresis": HISTERESIS,
        "nombre_anterior": NOMBRE_ANTERIOR,
        "version_calculo": VERSION_CALCULO,
        "licencia": LICENCIA,
        "aviso": foto_ifg.get("aviso"),
        "estado": foto_ifg.get("estado"),
        "revisiones": REVISIONES,
        "generado": foto_ifg.get("generado"),
    }
    # Claves nuevas que pueda traer el IFG en el futuro: pasan tal cual.
    for clave, valor in foto_ifg.items():
        if clave not in salida:
            salida[clave] = valor
    if not salida["aviso"]:
        raise ErrorOscilador("la foto del IFG no trae el aviso legal")
    return salida


def construir_12m(s12: dict, serie: pd.DataFrame, tramos: pd.Series) -> dict:
    fechas, valores = s12.get("fechas") or [], s12.get("valores") or []
    if not fechas or len(fechas) != len(valores):
        raise ErrorOscilador("la serie de doce meses del IFG viene vacía o descuadrada")
    if fechas[-1] != serie.index[-1]:
        raise ErrorOscilador(
            f"la serie de doce meses acaba en {fechas[-1]} y la completa en {serie.index[-1]}")
    for f, v in zip(fechas, valores):
        if f not in serie.index:
            raise ErrorOscilador(f"la sesión {f} de los doce meses no está en la serie completa")
        vs = serie.at[f, "ifg"]
        if es_nulo(v) != es_nulo(vs) or (not es_nulo(v) and abs(float(v) - float(vs)) > TOLERANCIA):
            raise ErrorOscilador(f"la sesión {f} no coincide entre los doce meses y la serie")
    por_sesion = [tramos[f] for f in fechas]
    cuenta = {nombre: 0 for _, _, nombre in TRAMOS}
    for t in por_sesion:
        if t in cuenta:
            cuenta[t] += 1
    salida = {
        "indice": NOMBRE,
        "version": VERSION,
        "generado": s12.get("generado"),
        "desde": s12.get("desde"),
        "hasta": s12.get("hasta"),
        "sesiones": s12.get("sesiones"),
        "fechas": fechas,
        "valores": valores,
        "valores_tendencia": s12.get("valores_tendencia"),
        "tramos_sesion": por_sesion,
        "maximo": s12.get("maximo"),
        "minimo": s12.get("minimo"),
        "sesiones_por_tramo": cuenta,
        "escala": escala(),
        "desglose_nivel": s12.get("desglose_nivel"),
        "licencia": LICENCIA,
    }
    for clave, valor in s12.items():
        if clave not in salida and clave != "sesiones_por_tramo":
            salida[clave] = valor
    return salida


def construir_serie(serie: pd.DataFrame, tramos: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=serie.index)
    out.index.name = "fecha"
    out["valor"] = serie["ifg"]
    if "ifg_suavizado" in serie.columns:
        out["valor_tendencia"] = serie["ifg_suavizado"]
    if "variacion" in serie.columns:
        out["variacion"] = serie["variacion"]
    out["tramo"] = tramos
    if "cobertura" in serie.columns:
        out["cobertura"] = serie["cobertura"]
    out["estado"] = serie["estado"]
    return out


def calcular(dir_base: str = ".") -> tuple[dict, dict, pd.DataFrame, int]:
    cwd = os.getcwd()
    os.chdir(dir_base)
    try:
        serie = leer_serie()
        fijados = tramos_fijados(serie)
        tramos = calcular_tramos(serie["ifg"], fijados)
        foto = construir_foto(leer_json(ENT_FOTO), serie, tramos)
        s12 = construir_12m(leer_json(ENT_12M), serie, tramos)
        tabla = construir_serie(serie, tramos)
    finally:
        os.chdir(cwd)
    return foto, s12, tabla, len(fijados)


# ---------------------------------------------------------------------------
# Escritura atómica
# ---------------------------------------------------------------------------
def _escribir(ruta: str, contenido: str) -> None:
    carpeta = os.path.dirname(ruta)
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
        # mkstemp crea el fichero con permisos 600 y nginx no podría leer la
        # copia publicada (403 el 25/11/2026). Lectura para todos, como /ifg/.
        os.chmod(tmp, 0o644)
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def escribir(foto: dict, s12: dict, tabla: pd.DataFrame) -> None:
    # Se serializa todo antes de escribir nada: si algo falla, no queda nada a medias.
    t_foto = json.dumps(foto, ensure_ascii=False, indent=2) + "\n"
    t_12m = json.dumps(s12, ensure_ascii=False, separators=(",", ":")) + "\n"
    t_serie = tabla.to_csv(float_format="%.2f", lineterminator="\n")
    _escribir(SAL_SERIE, t_serie)
    _escribir(SAL_12M, t_12m)
    _escribir(SAL_FOTO, t_foto)   # la foto, la última: es lo que se publica


def resumen(tabla: pd.DataFrame) -> str:
    validos = tabla[tabla["tramo"] != SIN_DATO]
    sin = validos["valor"].map(tramo_por_valor)
    lineas = [f"Sesiones: {len(tabla)} ({tabla.index[0]} a {tabla.index[-1]}); sin dato: {len(tabla) - len(validos)}"]
    lineas.append("Reparto de tramos      sin histéresis   con histéresis")
    for _, _, n in TRAMOS:
        a = (sin == n).mean() * 100
        b = (validos["tramo"] == n).mean() * 100
        lineas.append(f"  {n:<16} {a:>10.1f} %   {b:>10.1f} %")
    cambios_sin = int((sin != sin.shift()).sum() - 1)
    cambios_con = int((validos["tramo"] != validos["tramo"].shift()).sum() - 1)
    lineas.append(f"Cambios de tramo: {cambios_sin} sin histéresis, {cambios_con} con histéresis")
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Oscilador Geopolítico 0.10.1 (publicación)")
    ap.add_argument("--comprobar", action="store_true", help="calcula y comprueba, sin escribir")
    ap.add_argument("--resumen", action="store_true", help="reparto de tramos de toda la serie")
    a = ap.parse_args(argv)
    try:
        foto, s12, tabla, n_fijados = calcular()
    except ErrorOscilador as e:
        print(f"OSCILADOR-ERROR: {e}", file=sys.stderr)
        return 1
    if a.resumen:
        print(resumen(tabla))
    if not a.comprobar:
        escribir(foto, s12, tabla)
    print(f"OSCILADOR {VERSION} {'comprobado' if a.comprobar else 'escrito'}: "
          f"{foto['fecha']} = {foto['valor']} ({foto['tramo']}, {foto.get('estado_dato')}); "
          f"tramos cerrados conservados: {n_fijados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
