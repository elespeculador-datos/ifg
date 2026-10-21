"""Sonda temporal 33: participaciones significativas de Iberdrola en la CNMV (variantes de URL sin .aspx)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "Accept-Language": "es-ES,es;q=0.9"}
s = requests.Session(); s.headers.update(H)
URLS = ["https://www.cnmv.es/portal/Consultas/Busqueda?id=7&nif=A48010615",
        "https://www.cnmv.es/portal/Consultas/EE/ParticipacionesSignificativas?nif=A48010615",
        "https://www.cnmv.es/portal/consultas/participacionessignificativas?nif=A48010615",
        "https://www.cnmv.es/portal/Consultas/EE/ParticipacionesSignificativasAutocartera?nif=A48010615"]
res = {}
for u in URLS:
    try:
        p = s.get(u, timeout=60)
        t = p.text
        tablas = re.findall(r"<table.*?</table>", t, re.S)
        enl = []
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
            tx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
            h = html.unescape(m.group(1))
            if any(k in (tx + h).lower() for k in ("particip", "voto", "nif=", "autocart")):
                enl.append([tx[:70], h[:180]])
        res[u] = {"http": p.status_code, "final": p.url, "len": len(t), "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:120],
                  "tablas": [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", x))[:1800] for x in tablas[:2]], "enlaces": enl[:40]}
        if tablas:
            (OUT / ("p%d.html" % URLS.index(u))).write_text(t[:300000])
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)}
(OUT / "cnmv_ps2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:2000])
