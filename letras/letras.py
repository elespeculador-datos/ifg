"""Letras del Tesoro: los tipos de cada subasta, las próximas fechas y quién las tiene.

Fuente: Tesoro Público (Dirección General del Tesoro y Política Financiera), www.tesoro.es:
- resultado de las últimas subastas de Letras (página web);
- estadísticas mensuales: subastas del año en curso y del anterior (11-xlsx) y Letras por tenedores (04-xlsx);
- histórico de subastas 2001-2025 (historico_subastas-xlsx);
- calendario de subastas en PDF de cada año (con la fecha límite de peticiones de los particulares).

El aviso legal del Tesoro permite reproducir su información si se hace fielmente, sin alterarla y citando
como fuente a la D. G. del Tesoro y Política Financiera, y publicar cálculos hechos con ella.

Comprobaciones antes de publicar:
- los tipos deben estar entre -1 % y 15 % y los importes ser positivos;
- la última subasta tiene que ser de los últimos 45 días; si no, el flujo avisa;
- las cifras de la página web y las del Excel mensual deben coincidir cuando hablan de la misma subasta;
  si no coinciden, manda la página web (es la más reciente) y el flujo avisa.

El servidor de tesoro.es no envía el certificado intermedio de su cadena TLS: se descarga el que anuncia
el propio certificado (AIA, FNMT) y se añade al almacén de certifi. La verificación TLS sigue activa.

Uso:
  python letras/letras.py --salida docs/letras
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
URL_ULTIMAS = TESORO + "/deuda-publica/subastas/resultado-ultimas-subastas/letras-del-tesoro"
URL_CALENDARIO = TESORO + "/deuda-publica/subastas/calendario"
DOC = TESORO + "/documents/d/tesoro/"
CAB = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124 Safari/537.36 (El Especulador, datos abiertos)", "Accept-Language": "es-ES,es;q=0.9"}
PAGINA_WP = "https://elespeculador.com/letras-del-tesoro/"
METODOLOGIA = PAGINA_WP + "#como-se-hace"
PAGES = "https://elespeculador-datos.github.io/ifg/letras/"
PLAZOS = (3, 6, 9, 12)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]


class DatosRaros(Exception):
    pass


AVISOS: list[str] = []


def _num(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x: float | None, dec: int = 3) -> str:
    return "—" if x is None else _num(x, dec) + " %"


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


# --------------------------------------------------------------------------- conexión
def sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(CAB)
    s.verify = _almacen_con_intermedio("www.tesoro.es")
    return s


def _almacen_con_intermedio(host: str) -> str:
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
def ultimas(s: requests.Session) -> list[dict]:
    """La tabla de la última subasta de cada plazo."""
    t = _get(s, URL_ULTIMAS).text
    tabla = next((x for x in re.findall(r"<table.*?</table>", t, re.S) if "Tipo de inter" in x and "MESES" in x.upper()), None)
    if not tabla:
        raise DatosRaros("la página de últimas subastas no trae la tabla de Letras")
    filas = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla, re.S):
        celdas = [_limpiar(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if len(celdas) >= 5:
            filas[celdas[0]] = celdas[1:5]
    plazos = [int(re.match(r"(\d+)", p).group(1)) for p in filas.get("Plazo", [])]
    if plazos != list(PLAZOS):
        raise DatosRaros(f"plazos inesperados en la última subasta: {filas.get('Plazo')}")

    def fecha(k: str, i: int) -> str:
        v = filas[k][i]
        if not re.fullmatch(r"\d\d/\d\d/\d{4}", v):
            raise DatosRaros(f"fecha inesperada en {k}: {v!r}")
        return f"{v[6:10]}-{v[3:5]}-{v[0:2]}"

    def valor(k: str, i: int) -> float | None:
        return _dec(filas[k][i]) if k in filas else None

    out = []
    for i, p in enumerate(plazos):
        out.append({"fecha": fecha("Fecha subasta", i), "plazo": p, "vencimiento": fecha("Fecha vencimiento", i),
                    "liquidacion": fecha("Fecha de liquidación", i), "solicitado": valor("Nominal solicitado", i),
                    "adjudicado": valor("Nominal adjudicado", i), "segunda_vuelta": valor("Nominal adjudicado (2ª vuelta)", i),
                    "precio_minimo": valor("Precio mínimo aceptado", i), "marginal": valor("Tipo de interés marginal", i),
                    "precio_medio": valor("Precio medio", i), "medio": valor("Tipo de interés medio", i), "fuente": "web"})
    return out


def subastas_excel(contenido: bytes, fuente: str) -> list[dict]:
    """Subastas de Letras de un Excel del Tesoro con una hoja por año (columnas: fecha, activo y plazo, solicitado,
    2.ª vuelta, adjudicado, tipo marginal, tipo medio). La fecha se toma del día y el mes de la celda y del año de la
    hoja, porque en las hojas antiguas el año de la celda no es fiable."""
    xl = pd.ExcelFile(io.BytesIO(contenido))
    out = []
    for hoja in xl.sheet_names:
        if not re.fullmatch(r"\d{4}", str(hoja).strip()):
            continue
        anio = int(hoja)
        df = xl.parse(hoja, header=None)
        actual = None
        for fila in df.itertuples(index=False):
            c = list(fila) + [None] * 8
            if isinstance(c[0], (datetime, pd.Timestamp)):
                actual = date(anio, c[0].month, c[0].day)
            m = re.match(r"^\s*L\s*-\s*(\d+)\s*m", str(c[1] or ""))
            if not m or actual is None:
                continue

            def n(v):
                return None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "" else float(v)
            out.append({"fecha": actual.isoformat(), "plazo": int(m.group(1)), "solicitado": n(c[2]),
                        "segunda_vuelta": n(c[3]), "adjudicado": n(c[4]), "marginal": n(c[5]), "medio": n(c[6]),
                        "fuente": fuente})
    return out


def tenedores(contenido: bytes) -> dict:
    """Letras en manos de personas físicas: cierre de cada año y último mes publicado."""
    xl = pd.ExcelFile(io.BytesIO(contenido))
    df = xl.parse(xl.sheet_names[0], header=None).fillna("")
    cab = [str(x).replace("\n", " ").strip() for x in df.iloc[5].tolist()]
    try:
        i_pf = cab.index("PERSONAS FÍSICAS")
        i_tot = next(i for i, x in enumerate(cab) if x.replace(" ", "") == "TOTAL")
    except (ValueError, StopIteration):
        raise DatosRaros("el Excel de tenedores de Letras ha cambiado de columnas")
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
        raise DatosRaros("el Excel de tenedores de Letras no trae meses")
    for m in meses:  # años sin fila de cierre (los más recientes): el dato de diciembre
        if m["mes"] == 12 and m["anio"] not in anios:
            anios[m["anio"]] = {"personas_fisicas": m["personas_fisicas"], "total": m["total"]}
    return {"anios": anios, "ultimo": meses[-1], "meses": meses}


def calendario(s: requests.Session, hoy: date) -> list[dict]:
    """Subastas de Letras del calendario en PDF del año en curso y del siguiente, si ya está publicado."""
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
        filas = {}
        for linea in txt.splitlines():
            m = re.match(r"\s*(Peticiones\*\*|Subastas|Pago particulares\*\*\*|Emisión)\s+((?:\d\d/\d\d/\d{4}\*?\s*){4})\s*$", linea)
            if not m:
                continue
            clave = m.group(1).rstrip("*").split()[0].lower()
            fechas = re.findall(r"(\d\d)/(\d\d)/(\d{4})", m.group(2))
            filas.setdefault(clave, []).append([f"{a}-{mm}-{d}" for d, mm, a in fechas])
        if not filas.get("subastas"):
            AVISOS.append(f"No se ha podido leer el calendario de subastas de {anio}")
            continue
        for k in range(len(filas["subastas"])):
            for col, plazos in ((0, (6, 12)), (1, (3, 9))):
                try:
                    out.append({"subasta": filas["subastas"][k][col], "plazos": plazos,
                                "peticiones": filas["peticiones"][k][col], "pago": filas["pago"][k][col],
                                "emision": filas["emisión"][k][col], "anio_calendario": anio})
                except (KeyError, IndexError):
                    AVISOS.append(f"Calendario {anio}: fila {k} incompleta")
    return sorted(out, key=lambda x: x["subasta"])


# --------------------------------------------------------------------------- unión y comprobaciones
def unir(web: list[dict], mensual: list[dict], historico: list[dict]) -> list[dict]:
    por = {}
    for fuente in (historico, mensual, web):  # lo más reciente manda
        for f in fuente:
            k = (f["fecha"], f["plazo"])
            if k in por and f["fuente"] == "web" and por[k]["fuente"] == "mensual":
                a, b = por[k], f
                for c in ("marginal", "medio"):
                    if a.get(c) is not None and b.get(c) is not None and abs(a[c] - b[c]) > 0.0015:
                        AVISOS.append(f"La web y el Excel mensual no coinciden en {c} de la subasta {k}: {b[c]} frente a {a[c]}")
            por[k] = {**por.get(k, {}), **{c: v for c, v in f.items() if v is not None}}
    filas = sorted(por.values(), key=lambda f: (f["fecha"], f["plazo"]))
    for f in filas:
        for c in ("marginal", "medio"):
            if f.get(c) is not None and not -1 <= f[c] <= 15:
                raise DatosRaros(f"tipo fuera de rango en {f['fecha']} ({f['plazo']} meses): {f[c]}")
        for c in ("solicitado", "adjudicado"):
            if f.get(c) is not None and f[c] < 0:
                raise DatosRaros(f"importe negativo en {f['fecha']} ({f['plazo']} meses)")
    return filas


def ultima_por_plazo(filas: list[dict]) -> dict[int, dict]:
    out = {}
    for f in filas:
        if f["plazo"] in PLAZOS and f.get("marginal") is not None:
            out[f["plazo"]] = f
    return out


def huella(datos: dict) -> str:
    base = [[f["fecha"], f["plazo"], f.get("marginal"), f.get("medio")] for f in datos["subastas"][-60:]]
    base.append([[c["subasta"], c["peticiones"]] for c in datos["proximas"][:4]])
    base.append(datos["tenedores"]["ultimo"])
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _tabla(cab: list[str], filas: list[list[str]]) -> str:
    return ('<figure class="wp-block-table"><table><thead><tr>' + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead><tbody>\n"
            + "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "\n</tbody></table></figure>")


def fragmento(datos: dict, fecha: str) -> str:
    sub = datos["subastas"]
    ult = ultima_por_plazo(sub)
    doce = ult.get(12)
    partes = [f"<!-- letras:inicio {huella(datos)} -->",
              f'<p class="has-small-font-size">Actualizado el {_f(fecha)} con los datos del Tesoro Público.</p>']
    if doce:
        precio = doce.get("precio_medio")
        frase = (f"<p>En la última subasta de Letras a 12 meses, la del {_flargo(doce['fecha'])}, el tipo de interés medio fue del "
                 f"{_pct(doce['medio'])} y el marginal, el más alto aceptado, del {_pct(doce['marginal'])}.")
        if precio:
            frase += (f" Al precio medio de esa subasta, que es el que pagan las peticiones no competitivas de los particulares, "
                      f"una letra de 1.000 euros costó {_num(precio * 10, 2)} euros y se amortiza por 1.000 al vencimiento: la "
                      f"diferencia es el rendimiento, antes de impuestos.")
        partes.append(frase + "</p>")
    filas = []
    for p in PLAZOS:
        f = ult.get(p)
        if not f:
            continue
        filas.append([f"{p} meses", _f(f["fecha"]), _pct(f.get("medio")), _pct(f.get("marginal")),
                      _num(f["precio_medio"], 3) if f.get("precio_medio") else "—",
                      _num(f["solicitado"], 0) if f.get("solicitado") is not None else "—",
                      _num(f["adjudicado"], 0) if f.get("adjudicado") is not None else "—",
                      _f(f.get("vencimiento", ""))])
    partes += ["<h2>La última subasta de cada plazo</h2>",
               _tabla(["Plazo", "Subasta", "Tipo medio", "Tipo marginal", "Precio medio (% del nominal)",
                       "Solicitado (mill. €)", "Adjudicado (mill. €)", "Vencimiento"], filas)]
    prox = [c for c in datos["proximas"] if c["subasta"] >= fecha][:6]
    if prox:
        partes += ["<h2>Las próximas subastas</h2>",
                   "<p>La columna de peticiones es el plazo del calendario del Tesoro para los particulares con Cuenta Directa "
                   "en el Banco de España: antes de las 14:00 (hora peninsular) de ese día. Quien compre a través de un banco o un "
                   "bróker tiene el plazo que fije su entidad.</p>",
                   _tabla(["Subasta", "Plazos", "Peticiones con Cuenta Directa, hasta el", "Emisión"],
                          [[_f(c["subasta"]), " y ".join(f"{p}" for p in c["plazos"]) + " meses", _f(c["peticiones"]),
                            _f(c["emision"])] for c in prox])]
    # evolución: tipo medio de cada subasta de 12 meses en los últimos 24 meses
    desde = (date.fromisoformat(fecha) - timedelta(days=730)).isoformat()
    evol = [f for f in sub if f["plazo"] == 12 and f["fecha"] >= desde and f.get("medio") is not None]
    if evol:
        partes += ["<h2>El tipo de las Letras a 12 meses, subasta a subasta</h2>",
                   _tabla(["Subasta", "Tipo medio", "Tipo marginal", "Adjudicado (mill. €)"],
                          [[_f(f["fecha"]), _pct(f["medio"]), _pct(f.get("marginal")),
                            _num(f["adjudicado"], 0) if f.get("adjudicado") is not None else "—"] for f in reversed(evol)])]
    # media anual por plazo
    anual = {}
    for f in sub:
        if f["plazo"] in PLAZOS and f.get("medio") is not None:
            anual.setdefault(int(f["fecha"][:4]), {}).setdefault(f["plazo"], []).append(f["medio"])
    anios = sorted(anual)[-15:]
    partes += ["<h2>La media de cada año</h2>",
               "<p>Media simple del tipo medio de todas las subastas de cada año y plazo (el año en curso, hasta la última subasta).</p>",
               _tabla(["Año"] + [f"{p} meses" for p in PLAZOS],
                      [[str(a)] + [_pct(sum(anual[a][p]) / len(anual[a][p])) if p in anual[a] else "—" for p in PLAZOS]
                       for a in reversed(anios)])]
    ten = datos["tenedores"]
    u = ten["ultimo"]
    partes += ["<h2>Cuántas Letras tienen los particulares</h2>",
               f"<p>En {MESES[u['mes'] - 1]} de {u['anio']}, las personas físicas tenían {_num(u['personas_fisicas'], 0)} millones "
               f"de euros en Letras del Tesoro, el {_num(u['personas_fisicas'] / u['total'] * 100, 1)} % del total en circulación "
               f"({_num(u['total'], 0)} millones), según el Tesoro con datos del Banco de España.</p>",
               _tabla(["Cierre de", "Personas físicas (mill. €)", "Total en circulación (mill. €)", "Parte de las personas físicas"],
                      [[str(a), _num(v["personas_fisicas"], 0), _num(v["total"], 0), _num(v["personas_fisicas"] / v["total"] * 100, 1) + " %"]
                       for a, v in sorted(ten["anios"].items()) if a >= 2019][::-1]),
               "<p>Saldos a vencimiento a final de cada año, de la serie de tenedores del Tesoro (fuente: Banco de España).</p>"]
    partes.append(f'<p class="has-small-font-size">Fuente: D. G. del Tesoro y Política Financiera (resultado de las subastas, '
                  f'estadísticas mensuales, histórico de subastas y calendario de subastas). Tipos en porcentaje anual; importes '
                  f'nominales en millones de euros. <a href="{METODOLOGIA}">Cómo se hace</a>.</p>')
    partes.append("<!-- letras:fin -->")
    return "\n".join(partes)


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Subastas de Letras del Tesoro: tipos de interés, calendario y tenedores (El Especulador)",
        "description": "Resultados de todas las subastas de Letras del Tesoro desde 2001 (tipo medio y marginal, importes), "
                       "las próximas subastas con la fecha límite de peticiones de los particulares y las Letras en manos de "
                       "personas físicas, con datos del Tesoro Público.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir de datos de la D. G. del Tesoro y Política Financiera",
        "isBasedOn": "https://www.tesoro.es/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{PAGES}datos/{n}.csv"}
                         for n in ("subastas_letras", "proximas_subastas")],
    }, ensure_ascii=False) + "</script>"


def escribir(datos: dict, fecha: str, salida: Path) -> bool:
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    previo = dd / "ultima.json"
    antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    nueva = huella(datos)
    cambia = antes.get("huella") != nueva
    fecha_pub = fecha if cambia else antes.get("fecha", fecha)
    campos = ["fecha", "plazo", "tipo_medio", "tipo_marginal", "precio_medio", "precio_minimo", "solicitado_mill",
              "adjudicado_mill", "segunda_vuelta_mill", "vencimiento", "liquidacion", "fuente"]
    with (dd / "subastas_letras.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for f in datos["subastas"]:
            w.writerow([f["fecha"], f["plazo"], f.get("medio"), f.get("marginal"), f.get("precio_medio"), f.get("precio_minimo"),
                        f.get("solicitado"), f.get("adjudicado"), f.get("segunda_vuelta"), f.get("vencimiento", ""),
                        f.get("liquidacion", ""), f.get("fuente")])
    with (dd / "proximas_subastas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["subasta", "plazos_meses", "peticiones_particulares_hasta", "pago_particulares", "emision"])
        for c in datos["proximas"]:
            w.writerow([c["subasta"], " y ".join(map(str, c["plazos"])), c["peticiones"], c["pago"], c["emision"]])
    previo.write_text(json.dumps({
        "fecha": fecha_pub, "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "huella": nueva,
        "ultimas": {str(k): v for k, v in ultima_por_plazo(datos["subastas"]).items()},
        "proximas": datos["proximas"][:8], "tenedores": datos["tenedores"]["ultimo"],
        "fuente": "D. G. del Tesoro y Política Financiera (www.tesoro.es)",
        "condiciones": "Reproducción fiel de la información del Tesoro Público, que la ofrece gratuitamente en www.tesoro.es. "
                       "Cita: El Especulador, a partir de datos de la D. G. del Tesoro y Política Financiera",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    frag = fragmento(datos, fecha_pub)
    marca = "\n<!-- letras:fin -->"
    ld = ld_wp(fecha_pub)
    assert "$" not in frag and "$" not in ld and frag.count(marca) == 1
    (salida / "fragmento-wp.html").write_text(frag.replace(marca, "\n" + ld + marca), encoding="utf-8")
    cuerpo = frag.split("\n", 1)[1].rsplit("\n", 1)[0]
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Letras del Tesoro: subastas y tipos | El Especulador</title>
<meta name="description" content="Tipo medio y marginal de cada subasta de Letras del Tesoro, próximas subastas con la fecha límite para particulares y cuántas Letras tienen las personas físicas. Datos del Tesoro Público.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1000px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.9rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style></head><body>
<h1>Letras del Tesoro: subastas, tipos y calendario</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/subastas_letras.csv">todas las subastas de Letras desde 2001</a> · <a href="datos/proximas_subastas.csv">próximas subastas</a> · <a href="datos/ultima.json">JSON</a>. Reproducen la información que el Tesoro Público ofrece gratuitamente en www.tesoro.es. Si los reutilizas, cita como fuente a la D. G. del Tesoro y Política Financiera y, si los incluyes en algo de pago, avisa de que son gratuitos en su web. Explicación completa: <a href="{PAGINA_WP}">la página de elespeculador.com</a>.</p>
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
    web = ultimas(s)
    mensual = subastas_excel(_get(s, DOC + "11-xlsx").content, "mensual")
    historico = subastas_excel(_get(s, DOC + "historico_subastas-xlsx").content, "historico")
    if len(historico) < 1000 or len(mensual) < 20:
        raise DatosRaros(f"pocas subastas leídas: histórico {len(historico)}, mensual {len(mensual)}")
    filas = unir(web, mensual, historico)
    ult = max(f["fecha"] for f in filas)
    if (hoy - date.fromisoformat(ult)).days > 45:
        AVISOS.append(f"La última subasta de Letras leída es del {ult}")
    datos = {"subastas": filas, "proximas": calendario(s, hoy), "tenedores": tenedores(_get(s, DOC + "04-xlsx").content)}
    if not [c for c in datos["proximas"] if c["subasta"] >= hoy.isoformat()]:
        AVISOS.append("No hay próximas subastas en el calendario leído")
    cambia = escribir(datos, hoy.isoformat(), Path(a.salida))
    for av in AVISOS:
        print(f"::warning::{av}")
    u = ultima_por_plazo(filas)
    print(f"{len(filas)} subastas de Letras ({filas[0]['fecha']} a {ult}). 12 meses: {u[12]['fecha']} {u[12].get('medio')} %. "
          f"Próximas: {len(datos['proximas'])}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
