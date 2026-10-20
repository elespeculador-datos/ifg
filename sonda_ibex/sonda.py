"""Sonda temporal: qué fuentes de cierres diarios del IBEX 35 responden desde GitHub Actions."""
import json, sys, time
from pathlib import Path
import requests

OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
res = {}

def prueba(nombre, url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=60, **kw)
        res[nombre] = {"url": url, "status": r.status_code, "tipo": r.headers.get("content-type"), "bytes": len(r.content)}
        (OUT / f"{nombre}.txt").write_bytes(r.content[:200000])
    except Exception as e:
        res[nombre] = {"url": url, "error": str(e)}

# prueba("stooq_ibex", "https://stooq.com/q/d/l/?s=^ibex&i=d")
# prueba("stooq_ibex_es", "https://stooq.pl/q/d/l/?s=^ibex&i=d")
# prueba("yahoo_ibex", "https://query1.finance.yahoo.com/v8/finance/chart/%5EIBEX?period1=0&period2=4102444800&interval=1d")
# prueba("yahoo_ibex_div", "https://query1.finance.yahoo.com/v8/finance/chart/%5EIBEXTR?period1=0&period2=4102444800&interval=1d")
# prueba("bme_ficha", "https://www.bolsasymercados.es/bme-exchange/es/Indices/Ibex/Ficha/IBEX-35")
prueba("bme_factsheet", "https://www.bolsasymercados.es/dam/descargas/indices/factsheet-ibex-35-es.pdf")
prueba("bme_boletin", "https://www.bolsasymercados.es/dam/descargas/indices/boletin-semanal-indices-ibex-es-en.pdf")

# Captura de las llamadas que hace la web de BME al cargar las páginas del IBEX
try:
    from playwright.sync_api import sync_playwright
    llamadas = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent=UA["User-Agent"])
        def anota(resp):
            u = resp.url
            if ("apiweb" in u or "six-group" in u or "fqs" in u or "istoric" in u) and not u.endswith((".js", ".css")):
                try:
                    cuerpo = resp.text()[:3000]
                except Exception:
                    cuerpo = ""
                llamadas.append({"url": u, "status": resp.status, "tipo": resp.headers.get("content-type"), "muestra": cuerpo})
        pg.on("response", anota)
        for u in ["https://www.bolsasymercados.es/es/bme-exchange/indices/ficha.ibex-35-es0si0000005.html",
                  "https://www.bolsasymercados.es/es/bme-exchange/indices/ibex/historico.html",
                  "https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ibex-35-es0si0000005.html"]:
            try:
                pg.goto(u, wait_until="networkidle", timeout=60000); time.sleep(3)
                (OUT / ("pagina_" + u.rsplit("/", 1)[-1])).write_text(pg.content()[:600000], encoding="utf-8")
                for texto in ["Histórico", "Historico", "Descargar", "Exportar", "CSV", "Excel"]:
                    try:
                        el = pg.get_by_text(texto, exact=False).first
                        if el.count():
                            el.click(timeout=5000); time.sleep(4)
                    except Exception:
                        pass
            except Exception as e:
                llamadas.append({"url": u, "error": str(e)})
        b.close()
    (OUT / "bme_llamadas.json").write_text(json.dumps(llamadas, ensure_ascii=False, indent=1), encoding="utf-8")
    res["bme_playwright"] = {"llamadas": len(llamadas)}
except Exception as e:
    res["bme_playwright"] = {"error": str(e)}

(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
