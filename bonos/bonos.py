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

Uso:
  python bonos/bonos.py --salida docs/bonos
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
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
PAGES = "https://elespeculador-datos.github.io/ifg/bonos/"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]
# Plazos de referencia para la media anual (clase, años)
REFERENCIAS = (("B", 3), ("B", 5), ("O", 10), ("O", 30))
ACTIVO = re.compile(r"^\s*(B|O)\s*(€i|\(BV\)|\(v\))?\s*-\s*(>)?\s*(\d+)\s*(a|y)\b\s*(\(s\))?\s*$", re.I)


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


def _dec(x: str) -> float | None:
    """Número con formato español de la web del Tesoro: 1.886,84 -> 1886.84."""
    x = (x or "").strip()
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
        md = re.match(r"^(B|O)\s*(€i)?\s+(-?[\d.,]+)\s*%\s*(\((.*)\))?$", den)
        if not mp or not md:
            raise DatosRaros(f"plazo o denominación inesperados ({grupo}): {filas['Plazo'][i]!r} / {den!r}")
        vr = re.search(r"VR\s*(\d+)\s*a", md.group(5) or "")
        out.append({
            "grupo": grupo, "columna": int(mp.group(1)), "denominacion": den, "clase": md.group(1),
            "indexado": bool(md.group(2)), "verde": False, "variable": False, "sindicada": False, "mas_de": False,
            "plazo": int(vr.group(1)) if vr else int(mp.group(1)), "vida_residual": md.group(5) or "",
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
    m = re.match(r"^\s*(-?[\d]+(?:[.,]\d+)?)\s*(v)?\s*$", str(v))
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


# --------------------------------------------------------------------------- unión y comprobaciones
def _clave(f: dict) -> tuple:
    return (f["fecha"], round(f["cupon"], 3) if f.get("cupon") is not None else None, f["indexado"])


def unir(web: list[dict], mensual: list[dict], historico: list[dict]) -> list[dict]:
    por: dict[tuple, dict] = {}
    for fuente in (historico, mensual):  # el mensual manda sobre el histórico
        for f in fuente:
            k = _clave(f) + (f["sindicada"], f["activo"])
            por[k] = {**por.get(k, {}), **{c: v for c, v in f.items() if v is not None}}
    for w in web:
        cand = [k for k in por if k[:3] == _clave(w) and not k[3]]
        if len(cand) > 1:
            AVISOS.append(f"La subasta web {_clave(w)} casa con varias filas del Excel; se usa la primera")
        if cand:
            a = por[cand[0]]
            for c in ("marginal", "medio"):
                if a.get(c) is not None and w.get(c) is not None and abs(a[c] - w[c]) > 0.0015:
                    AVISOS.append(f"La web y el Excel no coinciden en {c} de la subasta {_clave(w)}: {w[c]} frente a {a[c]}")
            extra = {c: v for c, v in w.items() if v is not None and c not in ("plazo", "fuente", "clase", "mas_de", "sindicada",
                                                                              "verde", "variable")}
            por[cand[0]] = {**a, **extra, "fuente": a["fuente"] + "+web"}
        else:
            w = {**w, "activo": w["denominacion"]}
            por[_clave(w) + (False, w["activo"])] = w
    filas = sorted(por.values(), key=lambda f: (f["fecha"], f["clase"], f["plazo"], f.get("cupon") or 0))
    for f in filas:
        for c in ("marginal", "medio"):
            minimo = -3 if f["indexado"] else -1  # los indexados dan rendimiento real: llegó a -1,2 % en 2017
            if f.get(c) is not None and not minimo <= f[c] <= 15:
                raise DatosRaros(f"rendimiento fuera de rango en {f['fecha']} ({f.get('activo')}): {f[c]}")
        for c in ("solicitado", "adjudicado"):
            if f.get(c) is not None and f[c] < 0:
                raise DatosRaros(f"importe negativo en {f['fecha']} ({f.get('activo')})")
    return filas


def _referencia(f: dict, clase: str, plazo: int) -> bool:
    return (f["clase"] == clase and f["plazo"] == plazo and not f["indexado"] and not f["verde"] and not f["variable"]
            and not f["sindicada"] and not f["mas_de"] and f.get("medio") is not None)


def huella(datos: dict) -> str:
    base = [[f["fecha"], f.get("activo"), f.get("marginal"), f.get("medio")] for f in datos["subastas"][-60:]]
    base.append([[w["fecha"], w["denominacion"], w.get("medio")] for w in datos["ultimas"]])
    base.append([[c["subasta"], c["peticiones"]] for c in datos["proximas"][:4]])
    base.append([[v["valor"], v["cupon"], v["vencimiento"]] for v in datos["en_emision"]])
    base.append(datos["tenedores"]["ultimo"])
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
    v = ("Bono" if w["clase"] == "B" else "Obligación") + (" €i" if w["indexado"] else "") + " " + _num(w["cupon"], 2) + " %"
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
                   "el plazo para los particulares con Cuenta Directa en el Banco de España; quien compre a través de un "
                   "banco o un bróker tiene el plazo que fije su entidad.</p>",
                   _tabla(["Subasta", "Peticiones con Cuenta Directa, hasta el", "Emisión", "Puede incluir indexados"],
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
                   "<p>Subastas de los dos últimos años con la etiqueta de 10 años del Tesoro, sin las indexadas ni las "
                   "sindicaciones. El cupón identifica el valor subastado.</p>",
                   _tabla(["Subasta", "Cupón del valor", "Rendimiento medio", "Rendimiento marginal", "Nominal adjudicado (mill. €)"],
                          [[_f(f["fecha"]), _num(f["cupon"], 2) + " %" if f.get("cupon") is not None else "—", _pct(f["medio"]),
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
               "«—»: ese año no hubo subastas de ese plazo.</p>",
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


def escribir(datos: dict, fecha: str, salida: Path) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(datos)
    cambia = antes.get("huella") != nueva
    fecha_pub = fecha if cambia else antes.get("fecha", fecha)
    campos = ["fecha", "activo", "clase", "plazo_anios", "mas_de", "indexado", "verde", "tipo_variable", "sindicacion", "cupon",
              "rendimiento_medio", "rendimiento_marginal", "solicitado_mill", "adjudicado_mill", "segunda_vuelta_mill",
              "precio_medio_ex_cupon", "precio_medio_compra", "vencimiento", "fuente"]
    with (dd / "subastas_bonos_obligaciones.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for f in datos["subastas"]:
            w.writerow([f["fecha"], f.get("activo"), f["clase"], f["plazo"], int(f["mas_de"]), int(f["indexado"]), int(f["verde"]),
                        int(f["variable"]), int(f["sindicada"]), f.get("cupon"), f.get("medio"), f.get("marginal"),
                        f.get("solicitado"), f.get("adjudicado"), f.get("segunda_vuelta"), f.get("precio_medio_ex"),
                        f.get("precio_medio_compra"), f.get("vencimiento", ""), f.get("fuente")])
    with (dd / "proximas_subastas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["subasta", "puede_incluir_indexados", "peticiones_particulares_hasta", "pago_particulares", "emision"])
        for c in datos["proximas"]:
            w.writerow([c["subasta"], int(c["indexados"]), c["peticiones"], c["pago"], c["emision"]])
    previo.write_text(json.dumps({
        "fecha": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "ultimas": datos["ultimas"], "en_emision": datos["en_emision"], "proximas": datos["proximas"][:8],
        "tenedores": datos["tenedores"]["ultimo"],
        "fuente_tenedores": "Tesoro Público, Bonos y Obligaciones del Estado no segregados: distribución por tenedores "
                            "(estadísticas mensuales)",
        "fuente": "D. G. del Tesoro y Política Financiera (www.tesoro.es)",
        "condiciones": "Reproducción fiel de la información del Tesoro Público, que la ofrece gratuitamente en www.tesoro.es. "
                       "Cita: El Especulador, a partir de datos de la D. G. del Tesoro y Política Financiera",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
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
<p class="pie">Comprobado el {_f(datetime.now(timezone.utc).date().isoformat())}. Contenido informativo; no constituye asesoramiento financiero ni recomendación de inversión.</p>
</body></html>
""", encoding="utf-8")
    return cambia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--fecha")
    a = ap.parse_args()
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).date()
    s = sesion()
    web = []
    for grupo, url in URL_RESULTADOS.items():
        web += leer_resultados(grupo, _get(s, url).text)
    mensual = subastas_excel(_get(s, DOC + "11-xlsx").content, "mensual")
    historico = subastas_excel(_get(s, DOC + "historico_subastas-xlsx").content, "historico")
    if len(historico) < 1000 or len(mensual) < 20:
        raise DatosRaros(f"pocas subastas leídas: histórico {len(historico)}, mensual {len(mensual)}")
    filas = unir(web, mensual, historico)
    ult = max(f["fecha"] for f in filas)
    if (hoy - date.fromisoformat(ult)).days > 45:
        AVISOS.append(f"La última subasta de Bonos y Obligaciones leída es del {ult}")
    datos = {"subastas": filas, "ultimas": web, "en_emision": leer_en_emision(_get(s, URL_EN_EMISION).text),
             "proximas": calendario(s, hoy), "tenedores": tenedores(_get(s, DOC + "05-xlsx").content)}
    if not [c for c in datos["proximas"] if c["subasta"] >= hoy.isoformat()]:
        AVISOS.append("No hay próximas subastas en el calendario leído")
    cambia = escribir(datos, hoy.isoformat(), Path(a.salida))
    for av in AVISOS:
        print(f"::warning::{av}")
    diez = [f for f in filas if _referencia(f, "O", 10)]
    print(f"{len(filas)} subastas de Bonos y Obligaciones ({filas[0]['fecha']} a {ult}). 10 años: {diez[-1]['fecha']} "
          f"{diez[-1].get('medio')} %. Próximas: {len(datos['proximas'])}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
