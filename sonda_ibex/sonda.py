"""Sonda temporal 28: auditoría de indexación de las piezas y páginas nuevas (sitemaps, estado HTTP, robots, canonical, JSON-LD)."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (compatible; El Especulador auditoria SEO)"}
SITES = {
    "elespeculador.com": ["horario-bolsas-hora-espanola", "posiciones-cortas-bolsa-espanola", "historico-ibex-35-records",
                          "como-se-elige-el-ibex-35", "posiciones-cortas-hoy", "ibex-35-en-cifras"],
    "tntbolsa.com": ["cuanto-arriesgar-por-operacion", "profit-factor-backtest", "futuros-ibex-35"],
}
res = {}
for site, slugs in SITES.items():
    r = requests.get(f"https://{site}/sitemap_index.xml", headers=H, timeout=60)
    maps = re.findall(r"<loc>(.*?)</loc>", r.text)
    texto = ""
    for m in maps:
        if "post-sitemap" in m or "page-sitemap" in m:
            try:
                texto += requests.get(m, headers=H, timeout=60).text
            except Exception as e:  # noqa: BLE001
                texto += f"ERROR {m} {e}"
    rob = requests.get(f"https://{site}/robots.txt", headers=H, timeout=30).text
    res[site] = {"sitemaps": maps, "robots_txt": rob[:1500], "urls": {}}
    for s in slugs:
        url = f"https://{site}/{s}/"
        d = {"en_sitemap": f"/{s}/" in texto}
        try:
            p = requests.get(url, headers=H, timeout=60)
            h = p.text
            d.update(http=p.status_code, final=p.url, bytes=len(h),
                     robots=(re.search(r'<meta name="robots" content="([^"]*)"', h) or [None, None])[1],
                     canonical=(re.search(r'<link rel="canonical" href="([^"]*)"', h) or [None, None])[1],
                     title=(re.search(r"<title>(.*?)</title>", h, re.S) or [None, None])[1],
                     ld_types=sorted(set(re.findall(r'"@type":"([A-Za-z]+)"', h))),
                     x_robots=p.headers.get("X-Robots-Tag"), cache=p.headers.get("cf-cache-status") or p.headers.get("x-cache"))
        except Exception as e:  # noqa: BLE001
            d["error"] = str(e)
        res[site]["urls"][s] = d
(OUT / "auditoria.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:3000])
