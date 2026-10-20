"""Sonda temporal 4: de dónde saca BME los dividendos y el calendario del mercado."""
import json, time
from pathlib import Path
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright
llamadas = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/126")
    def anota(resp):
        u = resp.url
        if ("apiweb" in u or "six-group" in u or ".json" in u) and "cookielaw" not in u and "labels" not in u:
            try: cuerpo = resp.text()[:6000]
            except Exception: cuerpo = ""
            llamadas.append({"url": u, "status": resp.status, "muestra": cuerpo})
    pg.on("response", anota)
    for u in ["https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/operaciones-financieras/dividendos.html",
              "https://www.bolsasymercados.es/es/bme-exchange/negociar/calendario-del-mercado.html",
              "https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/operaciones-financieras.html"]:
        try:
            pg.goto(u, wait_until="networkidle", timeout=60000); time.sleep(4)
            (OUT / ("p_" + u.rsplit("/", 1)[-1])).write_text(pg.content()[:400000], encoding="utf-8")
        except Exception as e:
            llamadas.append({"url": u, "error": str(e)[:300]})
    b.close()
(OUT / "llamadas.json").write_text(json.dumps(llamadas, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(llamadas))
