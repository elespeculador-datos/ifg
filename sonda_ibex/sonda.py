"""Sonda temporal 29: ¿están indexables las páginas comerciales de tntbolsa.com? (robots, canonical, estado HTTP, sitemap)."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (compatible; auditoria SEO TNT)"}
PAGS = ["", "cursos-bolsa", "curso-bolsa", "cursos-de-bolsa-online", "trading-mentor-coach", "webinars-trading", "federico-ferreres",
        "tnt-bolsa", "contacto", "planes-suscripcion", "kit-plan-diario-trading", "plan-trading"]
res = {"sitemap_index": requests.get("https://tntbolsa.com/sitemap_index.xml", headers=H, timeout=60).text[:2000]}
try:
    ps = requests.get("https://tntbolsa.com/page-sitemap.xml", headers=H, timeout=60)
    res["page_sitemap"] = {"http": ps.status_code, "inicio": ps.text[:500]}
except Exception as e:  # noqa: BLE001
    res["page_sitemap"] = str(e)
for s in PAGS:
    url = f"https://tntbolsa.com/{s}/" if s else "https://tntbolsa.com/"
    try:
        p = requests.get(url, headers=H, timeout=60, allow_redirects=True)
        h = p.text
        rob = re.search(r"<meta name=[\"']robots[\"'] content=[\"']([^\"']*)", h)
        can = re.search(r"<link rel=[\"']canonical[\"'] href=[\"']([^\"']*)", h)
        tit = re.search(r"<title>(.*?)</title>", h, re.S)
        res[s or "/"] = {"http": p.status_code, "final": p.url, "robots": rob and rob.group(1), "canonical": can and can.group(1),
                         "title": tit and tit.group(1).strip()[:120], "x_robots": p.headers.get("X-Robots-Tag")}
    except Exception as e:  # noqa: BLE001
        res[s or "/"] = {"error": str(e)}
for s in ["", "ibex-35", "historico-ibex-35-records", "ibex-35-en-cifras"]:
    url = f"https://elespeculador.com/{s}/" if s else "https://elespeculador.com/"
    p = requests.get(url, headers=H, timeout=60)
    rob = re.search(r"<meta name=[\"']robots[\"'] content=[\"']([^\"']*)", p.text)
    ld = re.findall(r'"@type":\s*"([A-Za-z]+)"', p.text)
    res["ee:" + (s or "/")] = {"http": p.status_code, "robots": rob and rob.group(1), "dataset": "Dataset" in ld}
(OUT / "tnt.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:3000])
