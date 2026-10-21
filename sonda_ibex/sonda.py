"""Sonda temporal 45: de dónde sale la composición del IBEX 35 en la web de BME (peticiones a su API al cargar las páginas del índice)."""
import json, re, subprocess, sys
from pathlib import Path
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], check=True)
subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True,
               stdout=subprocess.DEVNULL)
from playwright.sync_api import sync_playwright
capt, paginas = [], {}
def respuesta(r):
    u = r.url
    if "apiweb" in u or "/api/" in u.lower() or "json" in (r.headers.get("content-type") or ""):
        try:
            cuerpo = r.text()
        except Exception as e:
            cuerpo = f"ERR {e}"
        capt.append({"pagina": actual[0], "url": u, "status": r.status, "metodo": r.request.method,
                     "ct": r.headers.get("content-type"), "cuerpo": cuerpo[:30000]})
actual = [""]
INICIO = ["https://www.bolsasymercados.es/bme-exchange/es/Indices",
          "https://www.bolsasymercados.es/bme-exchange/es/Indices/Ibex"]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(locale="es-ES", user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    pg.on("response", respuesta)
    def visitar(url):
        actual[0] = url
        try:
            pg.goto(url, wait_until="networkidle", timeout=90000)
        except Exception as e:
            paginas[url] = {"error": str(e)[:300]}
            return []
        pg.wait_for_timeout(4000)
        enlaces = pg.eval_on_selector_all("a[href]", "els => els.map(e => [e.getAttribute('href'), (e.innerText||'').trim().slice(0,80)])")
        paginas[url] = {"final": pg.url, "titulo": pg.title(), "texto": pg.inner_text("body")[:6000],
                        "enlaces": [e for e in enlaces if e[0] and re.search(r"ndice|ibex|ponder|compos", e[0] + e[1], re.I)][:150]}
        return [e[0] for e in enlaces if e[0]]
    vistos = set()
    cola = list(INICIO)
    while cola and len(vistos) < 14:
        u = cola.pop(0)
        if u in vistos:
            continue
        vistos.add(u)
        hrefs = visitar(u)
        for h in hrefs:
            if h.startswith("/"):
                h = "https://www.bolsasymercados.es" + h
            if re.search(r"bolsasymercados\.es/bme-exchange/es/Indices/Ibex", h, re.I) and re.search(r"ibex-?35|compos|ponder", h, re.I) and h not in vistos:
                cola.append(h)
    b.close()
(OUT / "paginas.json").write_text(json.dumps(paginas, ensure_ascii=False, indent=1))
(OUT / "peticiones.json").write_text(json.dumps(capt, ensure_ascii=False, indent=1))
print(len(paginas), "páginas,", len(capt), "peticiones")
