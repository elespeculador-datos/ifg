"""Sonda temporal 34: búsqueda de participaciones significativas en la CNMV (postback ASP.NET)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "Accept-Language": "es-ES,es;q=0.9"}
URL = "https://www.cnmv.es/portal/Consultas/Busqueda?id=7"


def ocultos(t):
    return {m.group(1): html.unescape(m.group(2)) for m in re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', t)}


def limpiar(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


res = {}
for nombre, extra in [("denominacion", {"ctl00$ContentPrincipal$wNombreEntidad$txtDenominacion": "IBERDROLA"}),
                      ("ultdias", {"ctl00$ContentPrincipal$wFechas$ult_dias": "3"})]:
    s = requests.Session(); s.headers.update(H)
    g = s.get(URL, timeout=60)
    datos = ocultos(g.text)
    datos.update({"ctl00$ContentPrincipal$btnOk": "Buscar"})
    datos.update(extra)
    p = s.post(URL, data=datos, headers={"Referer": URL}, timeout=90)
    t = p.text
    (OUT / f"{nombre}.html").write_text(t[:600000])
    tablas = re.findall(r"<table.*?</table>", t, re.S)
    enl = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        h = html.unescape(m.group(1)); tx = limpiar(m.group(2))
        if re.search(r"nif=|NIF=|ndoc|verDoc|Documento|\.pdf|id=7|Particip", h, re.I) and "lang=" not in h:
            enl.append([tx[:90], h[:220]])
    sec = re.search(r'<section.*?</section>', t, re.S)
    res[nombre] = {"http": p.status_code, "final": p.url, "len": len(t), "ocultos": sorted(datos)[:12],
                   "tablas": [limpiar(x)[:2500] for x in tablas[:3]], "enlaces": enl[:60],
                   "texto": limpiar(sec.group(0))[:3000] if sec else ""}
(OUT / "cnmv_ps3.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:1500])
