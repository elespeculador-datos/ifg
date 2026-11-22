"""Bonos y Obligaciones del Estado: el rendimiento de cada subasta, las próximas fechas, los valores en emisión y
cuántos tienen los particulares.

Fuente: Tesoro Público (Dirección General del Tesoro y Política Financiera), www.tesoro.es:
- resultado de las últimas subastas de Bonos, de Obligaciones y de Bonos y Obligaciones indexados (páginas web);
- valores en emisión (página web);
- estadísticas mensuales: subastas del año en curso y del anterior (11-xlsx) y Bonos y Obligaciones no segregados
  por tenedores (05-xlsx);
- histórico de subastas 2001-2025 (historico_subastas-xlsx);
- calendario de subastas en PDF de cada año (con la fecha límite de peticiones de los particulares).

El aviso legal del Tesoro permite reproducir su información si se hace fielmente, sin alterarla y citando
como fuente a la D. G. del Tesoro y Política Financiera, y publicar cálculos hechos con ella.

Independiente de letras/letras.py: copia sus utilidades de conexión y formato para que un cambio en un activo no
rompa el otro.

Comprobaciones antes de publicar:
- los rendimientos deben estar entre -1 % y 15 % (los indexados, reales, desde -3 %) y los importes ser positivos;
- la última subasta tiene que ser de los últimos 45 días; si no, el flujo avisa;
- las cifras de la página web y las del Excel mensual deben coincidir cuando hablan de la misma subasta;
  si no coinciden, manda la página web (es la más reciente) y el flujo avisa.

Memoria y protección del CSV (desde el 23/11/2026):
- la tabla de resultados del Tesoro solo enseña la última subasta de cada plazo y el Excel mensual tarda semanas en
  recoger las nuevas: el colector lee su propio CSV anterior y conserva lo que leyó en la web aunque la tabla ya no lo
  muestre (así se perdieron dos subastas del 05/11/2026, recuperadas en filas_recuperadas.csv);
- antes de escribir, compara el CSV nuevo con el anterior por fila completa: cada fila anterior tiene que seguir igual
  o estar actualizada (misma subasta: fecha, cupón, indexación, sindicación y el mismo valor o los mismos rendimientos);
  la que desaparecería se conserva tal cual y el flujo avisa.

Plazo (criterio único desde el 23/11/2026): la columna en que el Tesoro presenta la subasta en su tabla de resultados,
con la vida residual en el nombre del valor cuando es una reapertura. Para las subastas que el colector no vio en esa
tabla, el plazo de la etiqueta del Excel del Tesoro (columnas_tesoro.csv recoge las vistas antes de que el CSV las
guardara).

Uso:
  python bonos/bonos.py --salida docs/bonos
  python bonos/bonos.py --salida docs/bonos --recuperar copia.csv   añade las subastas de copia.csv que falten
  python bonos/bonos.py --salida docs/bonos --comparar copia.csv    solo compara el CSV publicado con copia.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import certifi
import pandas as pd
import requests

TESORO = "https://www.tesoro.es"
URL_RESULTADOS = {
    "bonos": TESORO + "/deuda-publica/subastas/resultado-ultimas-subastas/bonos-del-estado",
    "obligaciones": TESORO + "/deuda-publica/subastas/resultado-ultimas-subastas/obligaciones-del-estado",
    "indexados": TESORO + "/deuda-publica/subastas/resultado-ultimas-subastas/bonos-y-obligaciones-indexados",
}
URL_EN_EMISION = TESORO + "/deuda-publica/valores-del-tesoro/valores-en-emision"
URL_CALENDARIO = TESORO + "/deuda-publica/subastas/calendario"
DOC = TESORO + "/documents/d/tesoro/"
CAB = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124 Safari/537.36 (El Especulador, datos abiertos)", "Accept-Language": "es-ES,es;q=0.9"}
PAGINA_WP = "https://elespeculador.com/bonos-y-obligaciones-del-estado/"
METODOLOGIA = PAGINA_WP + "#como-se-hace"
# Dirección pública de esta salida. Por defecto, GitHub Pages; en el servidor
# smpro-datos-1, la variable de entorno ESPEC_DATOS_BASE vale
# "https://datos.elespeculador.com/". Siempre termina en barra.
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/bonos/"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]
# Plazos de referencia para la media anual (clase, años)
REFERENCIAS = (("B", 3), ("B", 5), ("O", 10), ("O", 30))
TEXTOS = "3"  # súbelo al cambiar los textos fijos del fragmento, para que el escenario de Make los copie
ACTIVO = re.compile(r"^\s*(B|O)\s*(€i|\(BV\)|\(v\))?\s*-\s*(>)?\s*(\d+)\s*(a|y)\b\s*(\(s\))?\s*$", re.I)
# Denominación de la tabla de resultados del Tesoro: «O 3,20% (VR 8a 11m)», «O€i 0,70% (VR 7a 1m)», «B 2,60%», «O 3,75% (7A)»
DENOMINACION = re.compile(r"^(B|O)\s*(€i)?\s+(-?[\d.,]+)\s*%\s*(\((.*)\))?$")
VIDA_RESIDUAL = re.compile(r"VR\s*(\d+)\s*a")
AQUI = Path(__file__).resolve().parent
CSV_SUBASTAS = "subastas_bonos_obligaciones.csv"
RECUPERACION = AQUI / "filas_recuperadas.csv"  # subastas perdidas, recuperadas de fuentes del Tesoro (ver LEEME)
COLUMNAS_CONOCIDAS = AQUI / "columnas_tesoro.csv"  # columna del Tesoro de subastas vistas antes de que el CSV la guardara
# Columnas del CSV público y su clave interna, en orden. Las tres últimas se añadieron el 23/11/2026, al final, para no
# mover las anteriores.
COLUMNAS = (("fecha", "fecha"), ("activo", "activo"), ("clase", "clase"), ("plazo_anios", "plazo"), ("mas_de", "mas_de"),
            ("indexado", "indexado"), ("verde", "verde"), ("tipo_variable", "variable"), ("sindicacion", "sindicada"),
            ("cupon", "cupon"), ("rendimiento_medio", "medio"), ("rendimiento_marginal", "marginal"),
            ("solicitado_mill", "solicitado"), ("adjudicado_mill", "adjudicado"), ("segunda_vuelta_mill", "segunda_vuelta"),
            ("precio_medio_ex_cupon", "precio_medio_ex"), ("precio_medio_compra", "precio_medio_compra"),
            ("vencimiento", "vencimiento"), ("fuente", "fuente"),
            ("valor_tesoro", "denominacion"), ("vida_residual", "vida_residual"), ("columna_tesoro", "columna"))
COLUMNAS_ANTES = 19  # columnas del CSV hasta el 22/11/2026
BOOLEANOS = {"mas_de", "indexado", "verde", "variable", "sindicada"}
ENTEROS = {"plazo", "columna"}
CAMPOS_TEXTO = {"fecha", "activo", "clase", "vencimiento", "fuente", "denominacion", "vida_residual"}
# Lo que una fila de la web (o de la memoria) no cambia al casar con una fila del Excel
NO_COPIAR_DE_LA_WEB = ("plazo", "fuente", "clase", "mas_de", "sindicada", "verde", "variable", "activo")


class DatosRaros(Exception):
    pass


AVISOS: list[str] = []


def _num(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def _pct(x: float | None, dec: int = 3) -> str:
    return "—" if x is None else _num(x, dec) + " %"


def _parte(a: float, total: float) -> str:
    x = a / total * 100
    return _num(x, 2 if x < 1 else 1) + " %"


def _f(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def _flargo(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _limpiar(x: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


NOTA = re.compile(r"\[\d+\]")  # llamada a nota a pie de tabla, como «[1]» en la 2.ª vuelta pendiente de anunciar


def _dec(x: str) -> float | None:
    """Número con formato español de la web del Tesoro: 1.886,84 -> 1886.84. Las llamadas a nota («[1]») se quitan: desde el
    19/11/2026 el Tesoro pone «[1]» solo, en vez de la cifra, cuando los resultados de la 2.ª vuelta aún no se han anunciado
    (la nota dice cuándo); una celda que solo tiene la nota vale None, como un guion."""
    x = NOTA.sub("", x or "").strip()
    if not x or x in ("-", "—"):
        return None
    if not re.fullmatch(r"-?[\d.]+(,\d+)?", x):
        raise DatosRaros(f"número con formato inesperado: {x!r}")
    return float(x.replace(".", "").replace(",", "."))


def _fecha_es(v: str, que: str) -> str:
    if not re.fullmatch(r"\d\d/\d\d/\d{4}", v):
        raise DatosRaros(f"fecha inesperada en {que}: {v!r}")
    return f"{v[6:10]}-{v[3:5]}-{v[0:2]}"


# --------------------------------------------------------------------------- conexión
def sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(CAB)
    s.verify = _almacen_con_intermedio("www.tesoro.es")
    return s


def _almacen_con_intermedio(host: str) -> str:
    """El servidor de tesoro.es no envía el certificado intermedio: se descarga el que anuncia su propio certificado
    (AIA) y se añade al almacén de certifi. La verificación TLS sigue activa."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # solo para leer el certificado del servidor y su campo AIA
    with socket.create_connection((host, 443), timeout=30) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            der = ss.getpeercert(binary_form=True)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as t:
        t.write(ssl.DER_cert_to_PEM_cert(der))
    txt = subprocess.run(["openssl", "x509", "-in", t.name, "-noout", "-text"], capture_output=True, text=True).stdout
    extra = ""
    for u in re.findall(r"CA Issuers - URI:(\S+)", txt):
        d = requests.get(u, timeout=30).content
        extra += d.decode() if b"BEGIN CERTIFICATE" in d else ssl.DER_cert_to_PEM_cert(d)
    if not extra:
        raise DatosRaros("no se encuentra el certificado intermedio de tesoro.es")
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as b:
        b.write(Path(certifi.where()).read_text() + "\n" + extra)
    return b.name


def _get(s: requests.Session, url: str) -> requests.Response:
    for i in range(3):
        try:
            r = s.get(url, timeout=90)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(10 * (i + 1))
    raise DatosRaros(f"tesoro.es no devuelve {url}")


# --------------------------------------------------------------------------- lectura
def _filas_tabla(tabla: str) -> dict[str, list[str]]:
    filas = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla, re.S):
        celdas = [_limpiar(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if len(celdas) >= 2:
            filas[celdas[0]] = celdas[1:]
    return filas


def leer_resultados(grupo: str, texto: str) -> list[dict]:
    """La tabla de la última subasta de cada plazo de una de las tres páginas de resultados."""
    tabla = next((x for x in re.findall(r"<table.*?</table>", texto, re.S) if "Denominaci" in x and "Fecha subasta" in x), None)
    if not tabla:
        raise DatosRaros(f"la página de últimas subastas ({grupo}) no trae la tabla")
    filas = _filas_tabla(tabla)
    n = len(filas.get("Plazo", []))
    if not n:
        raise DatosRaros(f"la tabla de últimas subastas ({grupo}) no trae plazos")
    for k in ("Denominación", "Fecha subasta", "Fecha vencimiento", "Tipo de interés marginal", "Tipo de interés medio"):
        if len(filas.get(k, [])) != n:
            raise DatosRaros(f"la tabla de últimas subastas ({grupo}) no trae «{k}» para cada plazo")

    def valor(k: str, i: int) -> float | None:
        v = filas.get(k)
        return _dec(v[i]) if v and i < len(v) else None

    out = []
    for i in range(n):
        mp = re.match(r"(\d+)\s*AÑOS", filas["Plazo"][i].upper())
        den = filas["Denominación"][i]
        md = DENOMINACION.match(den)
        if not mp or not md:
            raise DatosRaros(f"plazo o denominación inesperados ({grupo}): {filas['Plazo'][i]!r} / {den!r}")
        # El plazo es la columna en que el Tesoro presenta la subasta (criterio único desde el 23/11/2026; antes, en las
        # reaperturas, la vida residual). La vida residual queda en el nombre del valor.
        out.append({
            "grupo": grupo, "columna": int(mp.group(1)), "denominacion": den, "clase": md.group(1),
            "indexado": bool(md.group(2)), "verde": False, "variable": False, "sindicada": False, "mas_de": False,
            "plazo": int(mp.group(1)), "vida_residual": md.group(5) or "",
            "cupon": _dec(md.group(3)), "fecha": _fecha_es(filas["Fecha subasta"][i], "Fecha subasta"),
            "vencimiento": _fecha_es(filas["Fecha vencimiento"][i], "Fecha vencimiento"),
            "liquidacion": _fecha_es(filas["Fecha de liquidación"][i], "Fecha de liquidación") if "Fecha de liquidación" in filas else "",
            "solicitado": valor("Nominal solicitado", i), "adjudicado": valor("Nominal adjudicado", i),
            "segunda_vuelta": valor("Nominal adjudicado (2ª vuelta)", i), "precio_minimo": valor("Precio mínimo aceptado", i),
            "marginal": valor("Tipo de interés marginal", i), "precio_medio_ex": valor("Precio medio ex-cupón", i),
            "precio_medio_compra": valor("Precio medio de compra", i), "medio": valor("Tipo de interés medio", i),
            "cobertura": valor("Ratio de cobertura", i), "fuente": "web"})
    return out


def leer_en_emision(texto: str) -> list[dict]:
    tabla = next((x for x in re.findall(r"<table.*?</table>", texto, re.S) if "en emisi" in x and "Cup" in x), None)
    if not tabla:
        raise DatosRaros("la página de valores en emisión no trae la tabla")
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla, re.S):
        c = [_limpiar(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(c) >= 3 and re.match(r"(Bono|Obligación)", c[0]):
            out.append({"valor": c[0], "cupon": _dec(c[1]), "vencimiento": _fecha_es(c[2], "valores en emisión")})
    if len(out) < 5:
        raise DatosRaros(f"pocos valores en emisión leídos: {len(out)}")
    return out


def _cupon(v) -> tuple[float | None, bool]:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    m = re.match(r"^\s*(-?[\d]+(?:[.,]\d+)?)\s*(v)?\s*$", NOTA.sub("", str(v)))
    if not m:
        raise DatosRaros(f"cupón con formato inesperado: {v!r}")
    return float(m.group(1).replace(",", ".")), bool(m.group(2))


def subastas_excel(contenido: bytes, fuente: str) -> list[dict]:
    """Subastas de Bonos y Obligaciones (emisiones a largo plazo) de un Excel del Tesoro con una hoja por año.
    Columnas 7 a 13: activo y plazo, solicitado, 2.ª vuelta, adjudicado, cupón, rendimiento marginal y medio.
    La fecha se toma del día y el mes de la celda y del año de la hoja, porque en las hojas antiguas el año de la
    celda no es fiable."""
    xl = pd.ExcelFile(io.BytesIO(contenido))
    out = []
    for hoja in xl.sheet_names:
        if not re.fullmatch(r"\d{4}", str(hoja).strip()):
            continue
        anio = int(str(hoja).strip())
        df = xl.parse(hoja, header=None)
        cab = " ".join(str(x) for x in df.iloc[3].tolist()) if len(df) > 3 else ""
        if "LARGO" not in cab.upper() or str(df.iloc[3, 7]).upper().find("LARGO") < 0:
            raise DatosRaros(f"la hoja {hoja} de {fuente} ha cambiado de columnas")
        actual = None
        for fila in df.itertuples(index=False):
            c = list(fila) + [None] * 14
            if isinstance(c[0], (datetime, pd.Timestamp)):
                actual = date(anio, c[0].month, c[0].day)
            a = "" if c[7] is None or (isinstance(c[7], float) and pd.isna(c[7])) else str(c[7])
            m = ACTIVO.match(a)
            if not m or actual is None:
                continue

            def n(v):
                return None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "" else float(v)
            cup, var = _cupon(c[11])
            mod = (m.group(2) or "").upper()
            out.append({"fecha": actual.isoformat(), "clase": m.group(1).upper(), "indexado": mod == "€I",
                        "verde": mod == "(BV)", "variable": mod == "(V)" or var, "sindicada": bool(m.group(6)),
                        "mas_de": bool(m.group(3)), "plazo": int(m.group(4)), "activo": a.strip(), "cupon": cup,
                        "solicitado": n(c[8]), "segunda_vuelta": n(c[9]), "adjudicado": n(c[10]),
                        "marginal": n(c[12]), "medio": n(c[13]), "fuente": fuente})
    return out


def tenedores(contenido: bytes) -> dict:
    """Bonos y Obligaciones no segregados en manos de personas físicas: cierre de cada año y último mes publicado."""
    xl = pd.ExcelFile(io.BytesIO(contenido))
    df = xl.parse(xl.sheet_names[0], header=None).fillna("")
    fila_cab = next((i for i in range(min(12, len(df)))
                     if "PERSONAS FÍSICAS" in [str(x).replace("\n", " ").strip() for x in df.iloc[i].tolist()]), None)
    if fila_cab is None:
        raise DatosRaros("el Excel de tenedores de Bonos y Obligaciones ha cambiado de columnas")
    cab = [str(x).replace("\n", " ").strip() for x in df.iloc[fila_cab].tolist()]
    try:
        i_pf = cab.index("PERSONAS FÍSICAS")
        i_tot = next(i for i, x in enumerate(cab) if x.replace(" ", "") == "TOTAL")
    except (ValueError, StopIteration):
        raise DatosRaros("el Excel de tenedores de Bonos y Obligaciones ha cambiado de columnas")
    anios, meses, anio = {}, [], None
    for fila in df.itertuples(index=False):
        c = [str(x).strip() for x in fila]
        if re.fullmatch(r"\d{4}", c[0]):
            anio = int(c[0])
            if c[i_pf]:
                anios[anio] = {"personas_fisicas": float(c[i_pf]), "total": float(c[i_tot])}
        elif c[0].lower() in MESES and anio and c[i_pf]:
            meses.append({"anio": anio, "mes": MESES.index(c[0].lower()) + 1, "personas_fisicas": float(c[i_pf]),
                          "total": float(c[i_tot])})
    if not meses:
        raise DatosRaros("el Excel de tenedores de Bonos y Obligaciones no trae meses")
    for m in meses:  # años sin fila de cierre (los más recientes): el dato de diciembre
        if m["mes"] == 12 and m["anio"] not in anios:
            anios[m["anio"]] = {"personas_fisicas": m["personas_fisicas"], "total": m["total"]}
    for v in list(anios.values()) + meses:
        if not 0 <= v["personas_fisicas"] <= v["total"]:
            raise DatosRaros("tenedores de Bonos y Obligaciones con cifras incoherentes")
    return {"anios": anios, "ultimo": meses[-1], "meses": meses}


def calendario_texto(txt: str, anio: int) -> list[dict]:
    """Subastas de Bonos y Obligaciones (columnas 3.ª y 4.ª de cada mes) del texto del calendario en PDF."""
    filas = {}
    for linea in txt.splitlines():
        m = re.match(r"\s*(Peticiones\*\*|Subastas|Pago particulares\*\*\*|Emisión)\s+((?:\d\d/\d\d/\d{4}\*?\s*){4})\s*$", linea)
        if not m:
            continue
        clave = m.group(1).rstrip("*").split()[0].lower()
        fechas = re.findall(r"(\d\d)/(\d\d)/(\d{4})(\*?)", m.group(2))
        filas.setdefault(clave, []).append([(f"{a}-{mm}-{d}", bool(est)) for d, mm, a, est in fechas])
    out = []
    if not filas.get("subastas"):
        AVISOS.append(f"No se ha podido leer el calendario de subastas de {anio}")
        return out
    for k in range(len(filas["subastas"])):
        for col in (2, 3):
            try:
                out.append({"subasta": filas["subastas"][k][col][0], "indexados": filas["subastas"][k][col][1],
                            "peticiones": filas["peticiones"][k][col][0], "pago": filas["pago"][k][col][0],
                            "emision": filas["emisión"][k][col][0], "anio_calendario": anio})
            except (KeyError, IndexError):
                AVISOS.append(f"Calendario {anio}: fila {k} incompleta")
    return out


def calendario(s: requests.Session, hoy: date) -> list[dict]:
    t = _get(s, URL_CALENDARIO).text
    enlaces = {}
    for m in re.finditer(r'href="([^"]*calendario-tesoro-publico-(\d{4})-espa[^"]*)"', t, re.I):
        enlaces.setdefault(int(m.group(2)), m.group(1))
    out = []
    for anio in sorted(a for a in enlaces if a >= hoy.year):
        url = enlaces[anio] if enlaces[anio].startswith("http") else TESORO + enlaces[anio]
        pdf = _get(s, url).content
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf)
        txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
        out += calendario_texto(txt, anio)
    unicas = {c["subasta"]: c for c in out}  # el calendario de un año repite enero del siguiente
    return sorted(unicas.values(), key=lambda x: x["subasta"])


# --------------------------------------------------------------------------- CSV de todas las subastas
def _fila_csv(f: dict) -> list[str]:
    """La fila tal como se escribe en el CSV; también es la base de la comparación por fila completa."""
    out = []
    for _, k in COLUMNAS:
        v = f.get(k)
        if k == "vida_residual" and v and not re.match(r"\s*VR\b", v):
            v = None  # otros paréntesis del Tesoro, como «(7A)», no son vida residual: quedan solo en valor_tesoro
        out.append(str(int(bool(v))) if k in BOOLEANOS else "" if v is None or v == "" else str(v))
    return out


def _de_csv(d: dict, nombre: str, linea: int) -> dict:
    """Una fila del CSV tal cual (las columnas que no tenga, vacías)."""
    f: dict = {}
    try:
        for col, k in COLUMNAS:
            v = (d.get(col) or "").strip()
            if k in BOOLEANOS:
                if v not in ("0", "1"):
                    raise ValueError(f"{col} = {v!r}")
                f[k] = v == "1"
            elif k in ENTEROS:
                f[k] = int(v) if v else None
            elif k in CAMPOS_TEXTO:
                f[k] = v or None
            else:
                f[k] = float(v) if v else None
    except ValueError as e:
        raise DatosRaros(f"{nombre}, línea {linea}: valor inesperado ({e})")
    if not (f["fecha"] and f["activo"] and f["clase"] and f["fuente"]) or f["plazo"] is None:
        raise DatosRaros(f"{nombre}, línea {linea}: fila incompleta")
    return f


def _completar_web(m: dict) -> dict:
    """Fila de la web guardada por la versión anterior al 23/11/2026, sin columna, nombre ni vida residual propios: el
    activo era la denominación del Tesoro y, en las reaperturas con «VR», el plazo era la vida residual (la columna se
    busca entonces en columnas_tesoro.csv); sin «VR», el plazo ya era la columna."""
    if m.get("columna") or m.get("fuente") != "web":
        return m
    md = DENOMINACION.match(m.get("activo") or "")
    m = {**m, "denominacion": m.get("denominacion") or m["activo"]}
    if md:
        m["vida_residual"] = m.get("vida_residual") or md.group(5) or None
        if not VIDA_RESIDUAL.search(md.group(5) or ""):
            m["columna"] = m["plazo"]
    return m


def leer_csv(ruta: Path | str) -> list[dict]:
    """Filas de un CSV de subastas de este colector (también en el formato de antes del 23/11/2026)."""
    ruta = Path(ruta)
    try:
        with ruta.open(newline="", encoding="utf-8") as fh:
            lector = csv.DictReader(fh)
            cab = lector.fieldnames or []
            falta = [c for c, _ in COLUMNAS[:COLUMNAS_ANTES] if c not in cab]
            if falta:
                raise DatosRaros(f"{ruta.name}: no es un CSV de subastas de este colector (faltan {', '.join(falta)})")
            return [_de_csv(d, ruta.name, i) for i, d in enumerate(lector, 2)]
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise DatosRaros(f"no se puede leer {ruta}: {e}")


def leer_conocidas(ruta: Path | str) -> list[dict]:
    """Columnas del Tesoro de subastas que el colector vio antes de que el CSV las guardara (columnas_tesoro.csv)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    out = []
    with ruta.open(newline="", encoding="utf-8") as fh:
        for i, d in enumerate(csv.DictReader(fh), 2):
            md = DENOMINACION.match((d.get("valor_tesoro") or "").strip())
            if not md or not re.fullmatch(r"\d{4}-\d\d-\d\d", d.get("fecha") or "") or not (d.get("columna_tesoro") or "").isdigit():
                raise DatosRaros(f"{ruta.name}, línea {i}: fila inesperada")
            out.append({"fecha": d["fecha"], "denominacion": d["valor_tesoro"].strip(), "columna": int(d["columna_tesoro"]),
                        "cupon": _dec(md.group(3)), "indexado": bool(md.group(2)), "vida_residual": md.group(5) or None})
    return out


# --------------------------------------------------------------------------- unión y comprobaciones
def _clave(f: dict) -> tuple:
    return (f["fecha"], round(f["cupon"], 3) if f.get("cupon") is not None else None, f["indexado"])


def _orden(f: dict) -> tuple:
    return (f["fecha"], f["clase"], f["plazo"], f.get("cupon") or 0, f.get("activo") or "")


def _aplicar_columnas(filas: list[dict], conocidas: list[dict]) -> None:
    por = defaultdict(list)
    for f in filas:
        if not f.get("columna") and not f["sindicada"]:
            por[_clave(f)].append(f)
    for c in conocidas:
        fs = por.get(_clave(c), [])
        if len(fs) > 1:
            AVISOS.append(f"La columna conocida de {c['denominacion']} ({c['fecha']}) casa con varias filas; no se aplica")
        elif fs:
            f = fs[0]
            f["columna"] = c["columna"]
            f["denominacion"] = f.get("denominacion") or c["denominacion"]
            f["vida_residual"] = f.get("vida_residual") or c["vida_residual"]


def unir(web: list[dict], mensual: list[dict], historico: list[dict], memoria: list[dict] = (),
         conocidas: list[dict] = ()) -> list[dict]:
    """Une las subastas del Excel (histórico y mensual) con las de la tabla de resultados del Tesoro.

    memoria: filas del CSV anterior. Las que vinieron de la web y cuya subasta ya no está en la tabla del Tesoro (que solo
    enseña la última de cada plazo) se tratan como si siguieran en ella: así no se pierden las subastas que la tabla deja
    de mostrar antes de que el Excel mensual las recoja, ni lo que solo da la web (precios medios, vencimiento, columna).
    conocidas: columnas del Tesoro vistas antes de que el CSV las guardara (columnas_tesoro.csv)."""
    por: dict[tuple, dict] = {}
    for fuente in (historico, mensual):  # el mensual manda sobre el histórico
        for f in fuente:
            k = _clave(f) + (f["sindicada"], f["activo"])
            por[k] = {**por.get(k, {}), **{c: v for c, v in f.items() if v is not None}}
    vistas = {_clave(w) for w in web}
    recordadas = [_completar_web(m) for m in memoria
                  if "web" in (m.get("fuente") or "") and not m.get("sindicada") and _clave(m) not in vistas]
    for w in [*web, *recordadas]:
        cand = [k for k in por if k[:3] == _clave(w) and not k[3]]
        if len(cand) > 1:
            AVISOS.append(f"La subasta web {_clave(w)} casa con varias filas del Excel; se usa la primera")
        if cand:
            a = por[cand[0]]
            for c in ("marginal", "medio"):
                if a.get(c) is not None and w.get(c) is not None and abs(a[c] - w[c]) > 0.0015:
                    AVISOS.append(f"La web y el Excel no coinciden en {c} de la subasta {_clave(w)}: {w[c]} frente a {a[c]}")
            extra = {c: v for c, v in w.items() if v is not None and c not in NO_COPIAR_DE_LA_WEB}
            por[cand[0]] = {**a, **extra, "fuente": a["fuente"] if "web" in a["fuente"] else a["fuente"] + "+web"}
        else:
            # Subasta que el Excel aún no tiene: la denominación del Tesoro hace de activo. Una fila de la memoria conserva
            # su activo y su fuente.
            w = {**w, "activo": w.get("activo") or w["denominacion"], "fuente": w.get("fuente") or "web"}
            por[_clave(w) + (False, w["activo"])] = w
    filas = list(por.values())
    _aplicar_columnas(filas, list(conocidas))
    for f in filas:
        if f.get("columna"):  # criterio único: el plazo es la columna del Tesoro, que es exacta
            f["plazo"], f["mas_de"] = f["columna"], False
    filas.sort(key=_orden)
    for f in filas:
        for c in ("marginal", "medio"):
            minimo = -3 if f["indexado"] else -1  # los indexados dan rendimiento real: llegó a -1,2 % en 2017
            if f.get(c) is not None and not minimo <= f[c] <= 15:
                raise DatosRaros(f"rendimiento fuera de rango en {f['fecha']} ({f.get('activo')}): {f[c]}")
        for c in ("solicitado", "adjudicado"):
            if f.get(c) is not None and f[c] < 0:
                raise DatosRaros(f"importe negativo en {f['fecha']} ({f.get('activo')})")
    return filas


# --------------------------------------------------------------------------- protección contra filas perdidas
def _identidad(f: dict) -> tuple:
    """Subasta de un valor: fecha, cupón, indexación y sindicación. No es única (en 2020-2023 hubo Bonos a 3 y a 5 años con
    cupón 0 el mismo día); por eso _misma_subasta mira además el activo, el nombre del valor o los rendimientos."""
    return _clave(f) + (bool(f.get("sindicada")),)


def _misma_subasta(n: dict, p: dict) -> bool:
    """n y p (de la misma _identidad) son la misma subasta: mismo activo; o el nombre del Tesoro de n es el activo o el
    nombre de p (fila de la web que el Excel ya recoge con su etiqueta); o los mismos rendimientos medio y marginal
    (la misma subasta con otra etiqueta del Excel, como «B-5y» y «B-5a»)."""
    if n.get("activo") == p.get("activo"):
        return True
    if n.get("denominacion") and n["denominacion"] in (p.get("activo"), p.get("denominacion")):
        return True
    return (p.get("medio") is not None and p.get("marginal") is not None and n.get("medio") == p.get("medio")
            and n.get("marginal") == p.get("marginal"))


def _diferencias(p: dict, n: dict) -> list[str]:
    return [f"{col}: {a!r} -> {b!r}" for (col, _), a, b in zip(COLUMNAS, _fila_csv(p), _fila_csv(n)) if a != b]


def proteger(previas: list[dict], filas: list[dict]) -> tuple[list[dict], dict]:
    """Compara las filas nuevas con las del CSV anterior por fila completa (todas las columnas, contando repeticiones).

    Cada fila anterior tiene que seguir igual o estar actualizada (la misma subasta con datos nuevos: segunda vuelta
    anunciada, el Excel que recoge una subasta de la web, el plazo con el criterio de la columna). Si ninguna fila nueva
    es su subasta, se conserva tal cual y el flujo avisa: el CSV no pierde subastas. Una fila anterior que repetía una
    subasta que sigue en el CSV con otra etiqueta se cuenta aparte (duplicada) y no se conserva."""
    libres = defaultdict(list)
    for n in filas:
        libres[tuple(_fila_csv(n))].append(n)
    usadas: set[int] = set()
    iguales, resto = 0, []
    for p in previas:
        t = tuple(_fila_csv(p))
        if libres.get(t):
            usadas.add(id(libres[t].pop()))
            iguales += 1
        else:
            resto.append(p)
    por_id = defaultdict(list)
    for n in filas:
        por_id[_identidad(n)].append(n)
    actualizadas, duplicadas, conservadas = [], [], []
    for p in resto:
        cubren = [n for n in por_id.get(_identidad(p), []) if _misma_subasta(n, p)]
        libre = next((n for n in cubren if id(n) not in usadas), None)
        if libre is not None:
            usadas.add(id(libre))
            actualizadas.append((p, libre))
        elif cubren:
            duplicadas.append((p, cubren[0]))
        else:
            conservadas.append(p)
    for p in conservadas:
        AVISOS.append(f"La subasta del {p['fecha']} ({p['activo']}, cupón {p.get('cupon')}) estaba en el CSV anterior y no "
                      f"sale en esta pasada: se conserva tal cual")
    for p, n in duplicadas:
        AVISOS.append(f"La fila del {p['fecha']} ({p['activo']}) repetía la subasta de {n['activo']}: no se conserva")
    nuevas = [n for n in filas if id(n) not in usadas]
    return sorted(filas + conservadas, key=_orden), {
        "previas": len(previas), "iguales": iguales, "actualizadas": actualizadas, "duplicadas": duplicadas,
        "conservadas": conservadas, "nuevas": nuevas}


def recuperar_filas(previas: list[dict], extra: list[dict], detallar: bool = False) -> tuple[list[dict], list[str]]:
    """Filas de un CSV de recuperación cuya subasta no está en las previas. Con detallar, las diferencias de las demás."""
    por_id = defaultdict(list)
    for p in previas:
        por_id[_identidad(p)].append(p)
    nuevas, notas = [], []
    for r in extra:
        cubren = [p for p in por_id.get(_identidad(r), []) if _misma_subasta(p, r)]
        if not cubren:
            nuevas.append(r)
            por_id[_identidad(r)].append(r)
        elif detallar and all(_diferencias(r, p) for p in cubren):
            notas.append(f"{r['fecha']} {r['activo']}: " + "; ".join(_diferencias(r, cubren[0])))
    return nuevas, notas


def calcular(web: list[dict], mensual: list[dict], historico: list[dict], csv_anterior: Path,
             recuperar: list[Path] = (), recuperacion: Path = RECUPERACION,
             conocidas: Path = COLUMNAS_CONOCIDAS) -> tuple[list[dict], dict]:
    """Las filas del CSV nuevo y el control de la comparación con el anterior."""
    anteriores = leer_csv(csv_anterior) if Path(csv_anterior).exists() else []
    recuperadas, notas = [], []
    for ruta, detallar in [(Path(recuperacion), False)] + [(Path(r), True) for r in recuperar]:
        if not ruta.exists():
            if detallar:
                raise DatosRaros(f"no existe el CSV de recuperación {ruta}")
            continue
        nuevas, nt = recuperar_filas(anteriores + recuperadas, leer_csv(ruta), detallar)
        recuperadas += nuevas
        notas += [f"{ruta.name}: {x}" for x in nt]
    previas = anteriores + recuperadas
    filas = unir(web, mensual, historico, memoria=previas, conocidas=leer_conocidas(conocidas))
    filas, control = proteger(previas, filas)
    control.update(anteriores=len(anteriores), recuperadas=recuperadas, notas_recuperacion=notas)
    return filas, control


def informe(control: dict) -> list[str]:
    """Líneas del registro con la comparación por fila completa."""
    c = control
    out = [f"Comparación por fila completa con el CSV anterior ({c['anteriores']} filas) y {len(c['recuperadas'])} recuperadas: "
           f"{c['iguales']} iguales, {len(c['actualizadas'])} actualizadas, {len(c['duplicadas'])} duplicadas quitadas, "
           f"{len(c['conservadas'])} conservadas; {len(c['nuevas'])} filas nuevas."]
    out += [f"  recuperada   {r['fecha']} {r['activo']}" for r in c["recuperadas"]]
    out += [f"  actualizada  {p['fecha']} {p['activo']}: " + "; ".join(_diferencias(p, n)) for p, n in c["actualizadas"]]
    out += [f"  duplicada    {p['fecha']} {p['activo']} (sigue {n['activo']})" for p, n in c["duplicadas"]]
    out += [f"  CONSERVADA   {p['fecha']} {p['activo']}" for p in c["conservadas"]]
    out += [f"  nueva        {n['fecha']} {n['activo']} (plazo {n['plazo']})" for n in c["nuevas"]]
    out += [f"  diferencia con el archivo de recuperación  {x}" for x in c.get("notas_recuperacion", [])]
    return out


def control_json(control: dict) -> dict:
    c = control
    return {"anteriores": c["anteriores"], "recuperadas": len(c["recuperadas"]), "iguales": c["iguales"],
            "actualizadas": len(c["actualizadas"]), "duplicadas_quitadas": len(c["duplicadas"]),
            "conservadas": len(c["conservadas"]), "nuevas": len(c["nuevas"]),
            "detalle_conservadas": [{"fecha": p["fecha"], "activo": p["activo"]} for p in c["conservadas"]],
            "detalle_duplicadas": [{"fecha": p["fecha"], "activo": p["activo"], "sigue": n["activo"]} for p, n in c["duplicadas"]]}


def comparar_archivos(publicado: Path, otro: Path) -> list[str]:
    """Compara dos CSV de subastas por fila completa (sin red): lo que tiene cada uno y lo que cambia."""
    a, b = leer_csv(otro), leer_csv(publicado)
    _, c = proteger(a, b)
    out = [f"{otro} ({len(a)} filas) frente a {publicado} ({len(b)} filas), por fila completa: {c['iguales']} iguales, "
           f"{len(c['actualizadas'])} con cambios, {len(c['conservadas'])} que faltan en {publicado.name}, "
           f"{len(c['duplicadas'])} repetidas, {len(c['nuevas'])} que solo están en {publicado.name}."]
    out += [f"  cambia  {p['fecha']} {p['activo']}: " + "; ".join(_diferencias(p, n)) for p, n in c["actualizadas"]]
    out += [f"  FALTA   {p['fecha']} {p['activo']}" for p in c["conservadas"]]
    out += [f"  repetida {p['fecha']} {p['activo']} (está {n['activo']})" for p, n in c["duplicadas"]]
    out += [f"  solo en {publicado.name}  {n['fecha']} {n['activo']}" for n in c["nuevas"]]
    return out


def _referencia(f: dict, clase: str, plazo: int) -> bool:
    return (f["clase"] == clase and f["plazo"] == plazo and not f["indexado"] and not f["verde"] and not f["variable"]
            and not f["sindicada"] and not f["mas_de"] and f.get("medio") is not None)


def proximas_desde(datos: dict, fecha: str) -> list[dict]:
    """Las subastas del calendario a partir del día dado (todas si no se da fecha), en orden."""
    return [c for c in datos["proximas"] if not fecha or c["subasta"] >= fecha]


def huella(datos: dict, fecha: str = "") -> str:
    base = [[f["fecha"], f.get("activo"), f.get("plazo"), f.get("marginal"), f.get("medio")] for f in datos["subastas"][-60:]]
    base.append([[w["fecha"], w["denominacion"], w.get("medio")] for w in datos["ultimas"]])
    base.append([[c["subasta"], c["peticiones"]] for c in proximas_desde(datos, fecha)[:4]])
    base.append([[v["valor"], v["cupon"], v["vencimiento"]] for v in datos["en_emision"]])
    base.append(datos["tenedores"]["ultimo"])
    base.append(TEXTOS)
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def _nombre_columna(w: dict) -> str:
    base = ("Bono" if w["grupo"] == "bonos" else "Obligación" if w["grupo"] == "obligaciones" else
            "Bono o Obligación indexado")
    return f"{base} a {w['columna']} años"


def _valor(w: dict) -> str:
    """Nombre del valor subastado, con la vida residual si es una reapertura: «Obligación 3,20 % (VR 8a 11m)»."""
    v = ("Bono" if w["clase"] == "B" else "Obligación") + (" €i" if w["indexado"] else "")
    v += " " + _num(w["cupon"], 2) + " %" if w.get("cupon") is not None else ""
    return v + (f" ({w['vida_residual']})" if w.get("vida_residual") else "")


def fragmento(datos: dict, fecha: str) -> str:
    sub, web = datos["subastas"], datos["ultimas"]
    partes = [f"<!-- bonos:inicio {huella(datos)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha)} con los datos del Tesoro Público.</p>']
    diez = next((w for w in web if w["grupo"] == "obligaciones" and w["columna"] == 10), None)
    if diez:
        frase = (f"<p>En la última subasta de Obligaciones a 10 años, la del {_flargo(diez['fecha'])}, el Tesoro colocó la "
                 f"{_valor(diez)} con vencimiento el {_flargo(diez['vencimiento'])}. El rendimiento medio fue del "
                 f"{_pct(diez['medio'])} y el marginal, el más alto aceptado, del {_pct(diez['marginal'])}.")
        if diez.get("precio_medio_ex"):
            frase += (f" El precio medio ex cupón fue del {_num(diez['precio_medio_ex'], 3)} % del nominal: "
                      f"{_num(diez['precio_medio_ex'] * 10, 2)} euros por cada 1.000 euros, sin contar el cupón corrido.")
        frase += (" El rendimiento es el que obtiene quien compra a ese precio y mantiene el valor hasta el vencimiento, antes "
                  "de impuestos y de las comisiones que cobre la entidad, si las hay. El de la próxima subasta no se sabe "
                  "hasta que se resuelve.</p>")
        partes.append(frase)
    filas = []
    for w in web:
        filas.append([_nombre_columna(w), _valor(w), _f(w["vencimiento"]), _f(w["fecha"]), _pct(w.get("medio")),
                      _pct(w.get("marginal")), _num(w["precio_medio_ex"], 3) if w.get("precio_medio_ex") else "—",
                      _num(w["adjudicado"], 0) if w.get("adjudicado") is not None else "—"])
    partes += ["<h2>La última subasta de cada plazo</h2>",
               "<p>Tal como las presenta el Tesoro: cada columna de su tabla de resultados es un plazo, y a veces el valor "
               "subastado en ese plazo es otro más antiguo, con la vida residual (VR) que se indica. €i: indexado a la "
               "inflación europea.</p>",
               _tabla(["Plazo", "Valor subastado", "Vencimiento", "Subasta", "Rendimiento medio", "Rendimiento marginal",
                       "Precio medio ex cupón (% del nominal)", "Nominal adjudicado (mill. €)"], filas)]
    prox = [c for c in datos["proximas"] if c["subasta"] >= fecha][:6]
    if prox:
        partes += ["<h2>Las próximas subastas</h2>",
                   "<p>Jueves de subasta de Bonos y Obligaciones del calendario del Tesoro. Según el Tesoro, los valores que "
                   "salen en cada una se anuncian generalmente el viernes anterior. La columna de peticiones es "
                   "el plazo para los particulares que piden en persona en el Banco de España, con Cuenta Directa: antes de "
                   "las 14:00 (hora peninsular) de ese día. Por internet, en la web del Tesoro, el mismo calendario pide "
                   "presentar la petición como mínimo dos días antes de la subasta. Quien compre a través de un banco o un "
                   "bróker tiene el plazo que fije su entidad.</p>",
                   _tabla(["Subasta", "Peticiones en el Banco de España, hasta el", "Emisión", "Puede incluir indexados"],
                          [[_f(c["subasta"]), _f(c["peticiones"]), _f(c["emision"]), "Sí" if c["indexados"] else "No"]
                           for c in prox])]
    emi = datos["en_emision"]
    partes += ["<h2>Los valores que el Tesoro tiene en emisión</h2>",
               "<p>Son los Bonos y Obligaciones de referencia que el Tesoro reabre en sus subastas hasta darles el volumen "
               "que busca; cuando lo alcanza, abre otro.</p>",
               _tabla(["Valor", "Cupón anual", "Vencimiento"],
                      [[v["valor"], _num(v["cupon"], 2) + " %", _f(v["vencimiento"])] for v in emi])]
    desde = (date.fromisoformat(fecha) - timedelta(days=730)).isoformat()
    evol = [f for f in sub if _referencia(f, "O", 10) and f["fecha"] >= desde]
    if evol:
        partes += ["<h2>El rendimiento de las Obligaciones a 10 años, subasta a subasta</h2>",
                   "<p>Subastas de los dos últimos años con plazo de 10 años, sin las indexadas ni las sindicaciones. El plazo es "
                   "la columna en que el Tesoro publica el resultado, como en la tabla de la última subasta de cada plazo; si el "
                   "valor subastado es una reapertura de otro más antiguo, se indica su vida residual (VR). En las subastas "
                   "anteriores al 15 de octubre de 2026 que no llegamos a ver en esa tabla, el plazo es el de la etiqueta de las "
                   "estadísticas del Tesoro, que en las reaperturas puede reflejar la vida residual en lugar de la columna.</p>",
                   _tabla(["Subasta", "Valor subastado", "Rendimiento medio", "Rendimiento marginal", "Nominal adjudicado (mill. €)"],
                          [[_f(f["fecha"]), _valor(f) if f.get("cupon") is not None else "—", _pct(f["medio"]),
                            _pct(f.get("marginal")), _num(f["adjudicado"], 0) if f.get("adjudicado") is not None else "—"]
                           for f in reversed(evol)])]
    anual: dict[int, dict] = {}
    for f in sub:
        for clase, plazo in REFERENCIAS:
            if _referencia(f, clase, plazo):
                anual.setdefault(int(f["fecha"][:4]), {}).setdefault((clase, plazo), []).append(f["medio"])
    anios = sorted(anual)[-15:]
    nombres = {("B", 3): "Bonos a 3 años", ("B", 5): "Bonos a 5 años", ("O", 10): "Obligaciones a 10 años",
               ("O", 30): "Obligaciones a 30 años"}
    partes += ["<h2>La media de cada año</h2>",
               "<p>Cálculo de El Especulador con datos del Tesoro: media simple del rendimiento medio de las subastas de cada "
               "año y plazo, sin las indexadas, las verdes ni las sindicaciones (el año en curso, hasta la última subasta). "
               "El plazo sigue el mismo criterio que la tabla anterior. «—»: ese año no hubo subastas de ese plazo.</p>",
               _tabla(["Año"] + [nombres[r] for r in REFERENCIAS],
                      [[str(a)] + [_pct(sum(anual[a][r]) / len(anual[a][r])) if r in anual[a] else "—" for r in REFERENCIAS]
                       for a in reversed(anios)])]
    ten = datos["tenedores"]
    u = ten["ultimo"]
    partes += ["<h2>Cuántos Bonos y Obligaciones tienen los particulares</h2>",
               f"<p>Según la estadística de tenedores del Tesoro Público, en {MESES[u['mes'] - 1]} de {u['anio']} las personas físicas "
               f"tenían {_num(u['personas_fisicas'], 0)} millones de euros en Bonos y Obligaciones del Estado no segregados, el "
               f"{_parte(u['personas_fisicas'], u['total'])} del total en circulación ({_num(u['total'], 0)} millones).</p>",
               _tabla(["Cierre de", "Personas físicas (mill. €)", "Total en circulación (mill. €)", "Parte de las personas físicas"],
                      [[str(a), _num(v["personas_fisicas"], 0), _num(v["total"], 0), _parte(v["personas_fisicas"], v["total"])]
                       for a, v in sorted(ten["anios"].items()) if a >= 2019][::-1]),
               "<p>Cartera a vencimiento, saldos nominales a final de cada año. Fuente: Tesoro Público, «Bonos y Obligaciones "
               "del Estado no segregados: distribución por tenedores» (estadísticas mensuales).</p>"]
    partes.append(f'<p class="has-small-font-size">Fuente: D. G. del Tesoro y Política Financiera (resultado de las últimas '
                  f'subastas, valores en emisión, estadísticas mensuales, histórico de subastas y calendario de subastas). '
                  f'Rendimientos en porcentaje anual; importes nominales en millones de euros. <a href="{METODOLOGIA}">Cómo se '
                  f'hace</a>.</p>')
    partes.append("<!-- bonos:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Subastas de Bonos y Obligaciones del Estado: rendimientos, calendario y tenedores (El Especulador)",
        "description": "Resultados de todas las subastas de Bonos y Obligaciones del Estado desde 2001 (rendimiento medio y "
                       "marginal, cupón, importes), la última subasta de cada plazo, los valores en emisión y las próximas "
                       "subastas con la fecha límite de peticiones de los particulares, con datos del Tesoro Público. Incluye "
                       "además los Bonos y Obligaciones en manos de personas físicas (estadística de tenedores del Tesoro).",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de la D. G. del Tesoro y Política Financiera",
        "isBasedOn": "https://www.tesoro.es/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ("subastas_bonos_obligaciones", "proximas_subastas")],
    }, ensure_ascii=False) + "</script>"


def _escribir_csv(ruta: Path, cabecera: list[str], filas: list[list]) -> None:
    """Escribe a un temporal y lo cambia de nombre: una pasada que se corta no deja un CSV a medias (la memoria del
    colector es el propio CSV)."""
    tmp = ruta.with_name("." + ruta.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cabecera)
        w.writerows(filas)
    os.replace(tmp, ruta)


def escribir(datos: dict, fecha: str, salida: Path) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(datos, fecha)
    cambia = antes.get("huella") != nueva
    fecha_pub = fecha if cambia else antes.get("fecha", fecha)
    _escribir_csv(dd / CSV_SUBASTAS, [c for c, _ in COLUMNAS], [_fila_csv(f) for f in datos["subastas"]])
    _escribir_csv(dd / "proximas_subastas.csv",
                  ["subasta", "puede_incluir_indexados", "peticiones_particulares_hasta", "pago_particulares", "emision"],
                  [[c["subasta"], int(c["indexados"]), c["peticiones"], c["pago"], c["emision"]] for c in datos["proximas"]])
    tmp = previo.with_name(".ultima.json.tmp")
    tmp.write_text(json.dumps({
        "fecha": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "ultimas": datos["ultimas"], "en_emision": datos["en_emision"], "proximas": proximas_desde(datos, fecha)[:8],
        "tenedores": datos["tenedores"]["ultimo"],
        "control_csv": datos.get("control"),
        "fuente_tenedores": "Tesoro Público, Bonos y Obligaciones del Estado no segregados: distribución por tenedores "
                            "(estadísticas mensuales)",
        "fuente": "D. G. del Tesoro y Política Financiera (www.tesoro.es)",
        "condiciones": "Reproducción fiel de la información del Tesoro Público, que la ofrece gratuitamente en www.tesoro.es. "
                       "Cita: El Especulador, a partir de datos de la D. G. del Tesoro y Política Financiera",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, previo)
    frag = fragmento(datos, fecha_pub)
    marca = "\n<!-- bonos:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bonos y Obligaciones del Estado: subastas | El Especulador</title>
<meta name="description" content="Rendimiento medio y marginal de cada subasta de Bonos y Obligaciones del Estado, valores en emisión, próximas subastas con la fecha límite para particulares y cuántos tienen las personas físicas. Datos del Tesoro Público.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Bonos y Obligaciones del Estado: subastas, rendimientos y calendario</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/subastas_bonos_obligaciones.csv">todas las subastas de Bonos y Obligaciones desde 2001</a> · <a href="datos/proximas_subastas.csv">próximas subastas</a> · <a href="datos/ultima.json">JSON</a>. Reproducen la información que el Tesoro Público ofrece gratuitamente en www.tesoro.es. Si los reutilizas, cita como fuente a la D. G. del Tesoro y Política Financiera y, si los incluyes en algo de pago, avisa de que son gratuitos en su web. Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
<p>El plazo del CSV de subastas (<code>plazo_anios</code>) es la columna en que el Tesoro publica el resultado en su tabla de resultados cuando la conocemos (<code>columna_tesoro</code>, con el nombre del valor en <code>valor_tesoro</code> y su vida residual en <code>vida_residual</code> si es una reapertura); si no, el de la etiqueta de las estadísticas del Tesoro (<code>activo</code>), que en las reaperturas puede reflejar la vida residual. Cambio del 23/11/2026: hasta entonces, en las reaperturas, <code>plazo_anios</code> era la vida residual o la etiqueta de las estadísticas, y las tres columnas finales no existían. <code>mas_de</code> vale 1 cuando el plazo es «más de N años» según esa etiqueta. Las dos subastas del 05/11/2026 que el CSV perdió el 21/11/2026 se recuperaron de la Resolución de 10/11/2026 de la D. G. del Tesoro y Política Financiera publicada en el BOE del 19/11/2026 (basado en datos de la Agencia Estatal Boletín Oficial del Estado, <a href="https://www.boe.es/">www.boe.es</a>).</p>
<p class="pie">Comprobado el {_f(datetime.now(timezone.utc).date().isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--fecha")
    ap.add_argument("--recuperar", action="append", default=[], metavar="CSV",
                    help="CSV de subastas (de este colector, de cualquier fecha) del que se añaden las subastas que falten en "
                         "el CSV anterior; las que ya están no se tocan y sus diferencias salen en el registro")
    ap.add_argument("--comparar", metavar="CSV",
                    help="no hace pasada: compara por fila completa el CSV de --salida con este y termina")
    a = ap.parse_args()
    salida = Path(a.salida)
    if a.comparar:
        for linea in comparar_archivos(salida / "datos" / CSV_SUBASTAS, Path(a.comparar)):
            print(linea)
        return 0
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).date()
    s = sesion()
    web = []
    for grupo, url in URL_RESULTADOS.items():
        web += leer_resultados(grupo, _get(s, url).text)
    mensual = subastas_excel(_get(s, DOC + "11-xlsx").content, "mensual")
    historico = subastas_excel(_get(s, DOC + "historico_subastas-xlsx").content, "historico")
    if len(historico) < 1000 or len(mensual) < 20:
        raise DatosRaros(f"pocas subastas leídas: histórico {len(historico)}, mensual {len(mensual)}")
    filas, control = calcular(web, mensual, historico, salida / "datos" / CSV_SUBASTAS, [Path(r) for r in a.recuperar])
    ult = max(f["fecha"] for f in filas)
    if (hoy - date.fromisoformat(ult)).days > 45:
        AVISOS.append(f"La última subasta de Bonos y Obligaciones leída es del {ult}")
    datos = {"subastas": filas, "ultimas": web, "en_emision": leer_en_emision(_get(s, URL_EN_EMISION).text),
             "proximas": calendario(s, hoy), "tenedores": tenedores(_get(s, DOC + "05-xlsx").content),
             "control": control_json(control)}
    if not [c for c in datos["proximas"] if c["subasta"] >= hoy.isoformat()]:
        AVISOS.append("No hay próximas subastas en el calendario leído")
    cambia = escribir(datos, hoy.isoformat(), salida)
    for linea in informe(control):
        print(linea)
    for av in AVISOS:
        print(f"::warning::{av}")
    diez = [f for f in filas if _referencia(f, "O", 10)]
    print(f"{len(filas)} subastas de Bonos y Obligaciones ({filas[0]['fecha']} a {ult}). Obligaciones a 10 años (columna del "
          f"Tesoro): {diez[-1]['fecha']} {diez[-1].get('denominacion') or diez[-1].get('activo')} {diez[-1].get('medio')} %. "
          f"Próximas: {len(datos['proximas'])}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
