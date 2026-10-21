"""Sonda temporal 36: búsquedas por palabra clave de las que fallaron en la 35."""
import json, re, html, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "Accept-Language": "es-ES,es;q=0.9"}
BUSQ = "https://www.cnmv.es/portal/Consultas/Busqueda?id=7"
BASE = "https://www.cnmv.es/portal/consultas/DerechosVoto/"
API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
CAB = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}


def limpiar(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def pedir(s, metodo, url, **kw):
    for i in range(3):
        try:
            return s.request(metodo, url, timeout=120, **kw)
        except requests.RequestException:
            time.sleep(10 * (i + 1))
    return None


def ocultos(t):
    return {m.group(1): html.unescape(m.group(2)) for m in re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', t)}


def buscar(s, nombre):
    g = pedir(s, "GET", BUSQ)
    if g is None:
        return None, "sin respuesta GET"
    d = ocultos(g.text)
    d.update({"ctl00$ContentPrincipal$btnOk": "Buscar", "ctl00$ContentPrincipal$wNombreEntidad$txtDenominacion": nombre})
    p = pedir(s, "POST", BUSQ, data=d, headers={"Referer": BUSQ})
    if p is None:
        return None, "sin respuesta POST"
    m = re.search(r'Notificaciones-Participaciones\.aspx\?qS=(\{[0-9a-f-]+\})', p.text)
    if m:
        return m.group(1), limpiar((re.search(r'id="ctl00_lblSubtitulo">(.*?)<', p.text) or [None, ""])[1])
    sec = re.search(r'<section id="maincontent".*?</section>', p.text, re.S)
    sec = sec.group(0) if sec else ""
    (OUT / ("busq_" + re.sub(r"\W+", "_", nombre)[:30] + ".html")).write_text(sec)
    cands = [(limpiar(x.group(2)), html.unescape(x.group(1))) for x in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', sec, re.S)]
    return None, {"final": p.url, "candidatos": cands[:30], "texto": limpiar(sec)[:1500]}


def accionistas(s, guid):
    r = pedir(s, "GET", BASE + "Notificaciones-Participaciones.aspx?qS=" + guid)
    if r is None:
        return {"error": "sin respuesta"}
    t = r.text
    tot = re.search(r"Número total de derechos de voto.*?([\d]{1,3}(?:\.\d{3})+)", limpiar(t))
    fmod = re.search(r"Fecha de última modificación del número de derechos de voto:\s*(?:<[^>]+>\s*)*([\d/]+)", t)
    tab = re.search(r'<table[^>]+id="ctl00_ContentPrincipal_gridAccionistasSignificativos".*?</table>', t, re.S)
    filas = []
    if tab:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tab.group(0), re.S):
            celdas = {m.group(1): limpiar(m.group(2)) for m in re.finditer(r'<td[^>]*data-th="([^"]+)"[^>]*>(.*?)</td>', tr, re.S)}
            if celdas.get("Denominación"):
                filas.append(celdas)
    otras = re.search(r'<table[^>]+id="([^"]*Otras[^"]*)"', t, re.I)
    return {"total_derechos": tot.group(1) if tot else None, "fecha_derechos": fmod.group(1) if fmod else None,
            "accionistas": filas, "tabla_otras": otras.group(1) if otras else None, "len": len(t)}


CLAVES = ["ACCIONA", "ACTIVIDADES DE CONSTRUCCION", "BANKINTER", "LOGISTA", "ACCIONA ENERGIAS", "ENDESA", "FERROVIAL",
          "INDRA", "TEXTIL", "INTERNATIONAL CONSOLIDATED", "PUIG", "SOLARIA", "IBERDROLA"]
res = {"empresas": []}
s = requests.Session(); s.headers.update(H)
for c in CLAVES:
    guid, info = buscar(s, c)
    e = {"clave": c, "guid": guid, "info": info}
    if guid:
        e.update(accionistas(s, guid))
    res["empresas"].append(e)
    time.sleep(2)
(OUT / "cnmv_ibex2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(sum(1 for e in res["empresas"] if e.get("guid")))
