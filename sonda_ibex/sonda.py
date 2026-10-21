"""Sonda temporal 46: aviso de composición del IBEX 35 (21/09/2026) y llamadas a la API en la ficha y en las cotizaciones del IBEX 35."""
import json, re, subprocess, sys
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
res = {}
for nombre, url in [("ag1526", "https://www.bolsasymercados.es/dam/descargas/indices/notices/index-manager/ag1526-revision.pdf"),
                    ("ag1026", "https://www.bolsasymercados.es/dam/descargas/indices/notices/index-manager/ag1026-revision.pdf"),
                    ("comite1526", "https://www.bolsasymercados.es/dam/descargas/indices/notices/technical-advisory-committee/aviso-comite-ibex-15-26.pdf")]:
    try:
        r = requests.get(url, headers=H, timeout=90)
        res[nombre] = {"status": r.status_code, "bytes": len(r.content)}
        if r.ok and r.content[:4] == b"%PDF":
            (OUT / f"{nombre}.pdf").write_bytes(r.content)
            t = subprocess.run(["pdftotext", "-layout", str(OUT / f"{nombre}.pdf"), "-"], capture_output=True, text=True).stdout
            (OUT / f"{nombre}.txt").write_text(t)
            (OUT / f"{nombre}.pdf").unlink()
    except Exception as e:
        res[nombre] = {"error": str(e)[:300]}
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], check=True)
subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True, stdout=subprocess.DEVNULL)
from playwright.sync_api import sync_playwright
capt, paginas, actual = [], {}, [""]
def respuesta(r):
    u = r.url
    if "apiweb" in u or ("bolsasymercados.es" in u and ".json" in u and "labels" not in u):
        try:
            cuerpo = r.text()
        except Exception as e:
            cuerpo = f"ERR {e}"
        capt.append({"pagina": actual[0], "url": u, "status": r.status, "metodo": r.request.method,
                     "post": (r.request.post_data or "")[:2000], "cuerpo": cuerpo[:60000]})
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(locale="es-ES", user_agent=H["User-Agent"])
    pg.on("response", respuesta)
    for url in ["https://www.bolsasymercados.es/es/bme-exchange/indices/ficha.ibex-35-es0si0000005.html",
                "https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ibex-35-es0si0000005.html"]:
        actual[0] = url
        try:
            pg.goto(url, wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(6000)
            paginas[url] = {"final": pg.url, "titulo": pg.title(), "texto": pg.inner_text("body")[:12000]}
        except Exception as e:
            paginas[url] = {"error": str(e)[:300]}
    b.close()
(OUT / "descargas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
(OUT / "paginas.json").write_text(json.dumps(paginas, ensure_ascii=False, indent=1))
(OUT / "peticiones.json").write_text(json.dumps(capt, ensure_ascii=False, indent=1))
print(res, len(capt))
