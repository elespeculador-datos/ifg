"""Sonda temporal 62: lectura pública de tntbolsa.com (robots, sitemaps, tipos, páginas con su robots de Yoast y final de la entrada plan-trading)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, comprobación técnica)"}
B = "https://tntbolsa.com"
res = {}
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=60)
        return r.status_code, r.text, r.headers.get("content-type", "")
    except Exception as e:
        return -1, str(e), ""
for k, u in [("robots", "/robots.txt"), ("sitemap_index", "/sitemap_index.xml"), ("page_sitemap", "/page-sitemap.xml")]:
    s, t, c = get(B + u)
    res[k] = {"http": s, "ct": c, "texto": t[:4000]}
s, t, c = get(B + "/wp-json/")
try:
    j = json.loads(t)
    res["raiz"] = {"http": s, "home": j.get("home"), "url": j.get("url"), "timezone_string": j.get("timezone_string"), "gmt_offset": j.get("gmt_offset"), "namespaces": j.get("namespaces")}
except Exception:
    res["raiz"] = {"http": s, "texto": t[:500]}
s, t, c = get(B + "/wp-json/wp/v2/types")
try:
    res["tipos"] = {k: {"rest_base": v.get("rest_base"), "name": v.get("name")} for k, v in json.loads(t).items()}
except Exception:
    res["tipos"] = {"http": s, "texto": t[:500]}
paginas = []
for pag in (1, 2):
    s, t, c = get(B + f"/wp-json/wp/v2/pages?per_page=100&page={pag}&_fields=id,slug,link,parent,yoast_head_json.robots,yoast_head_json.canonical")
    try:
        lote = json.loads(t)
    except Exception:
        break
    if not isinstance(lote, list) or not lote:
        break
    paginas += lote
res["paginas"] = paginas
s, t, c = get(B + "/wp-json/wp/v2/posts?slug=plan-trading&_fields=id,slug,link,modified,content")
try:
    p = json.loads(t)[0]
    r = p["content"]["rendered"]
    res["plan_trading"] = {"id": p["id"], "link": p["link"], "modified": p["modified"], "len": len(r), "final": r[-3500:]}
except Exception as e:
    res["plan_trading"] = {"http": s, "error": str(e), "texto": t[:300]}
(OUT / "tnt_publico.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
