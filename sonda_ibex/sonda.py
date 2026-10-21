"""Sonda temporal 32: enlaces de la ficha de entidad de la CNMV (Iberdrola) y página de participaciones significativas."""
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
r = s.get("https://www.cnmv.es/portal/Consultas/DatosEntidad?nif=A48010615", timeout=60)
t = r.text
links = []
for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
    href = html.unescape(m.group(1))
    if "onsultas" in href or "articipac" in txt.lower() or "voto" in txt.lower():
        links.append([txt[:80], href[:200]])
res = {"links": links[:80]}
ps = [h for tx, h in links if "articipac" in tx.lower() or "articipac" in h.lower()]
if ps:
    u = ps[0] if ps[0].startswith("http") else "https://www.cnmv.es" + (ps[0] if ps[0].startswith("/") else "/portal/" + ps[0])
    p = s.get(u, timeout=60)
    tablas = re.findall(r"<table.*?</table>", p.text, re.S)
    res["ps_url"] = u; res["ps_http"] = p.status_code; res["ps_final"] = p.url
    res["ps_tablas"] = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", x))[:2500] for x in tablas[:3]]
    (OUT / "ps.html").write_text(p.text[:400000])
(OUT / "cnmv_entidad.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:3000])
