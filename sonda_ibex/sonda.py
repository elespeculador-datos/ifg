"""Sonda temporal 39: subastas de Letras del Tesoro en tesoro.es (páginas y archivos descargables)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 (El Especulador, datos abiertos)",
     "Accept-Language": "es-ES,es;q=0.9"}
URLS = ["https://www.tesoro.es/deuda-publica/subastas/resultado-ultimas-subastas/letras-del-tesoro",
        "https://www.tesoro.es/deuda-publica/subastas/resultado-ultimas-subastas",
        "https://www.tesoro.es/deuda-publica/subastas/calendario-de-subastas",
        "https://www.tesoro.es/deuda-publica/estadisticas",
        "https://www.tesoro.es/aviso-legal",
        "https://www.tesoro.es/"]
def limpiar(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
res = {}
s = requests.Session(); s.headers.update(H)
for u in URLS:
    try:
        r = s.get(u, timeout=60)
        t = r.text
        enl = []
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
            h = html.unescape(m.group(1)); tx = limpiar(m.group(2))
            if re.search(r"\.(xlsx?|csv|pdf)|subasta|letra|estad|hist|calend|reutiliz|aviso", h + tx, re.I):
                enl.append([tx[:80], h[:220]])
        main = re.search(r"<main.*?</main>", t, re.S)
        res[u] = {"http": r.status_code, "final": r.url, "len": len(t), "enlaces": enl[:80],
                  "texto": limpiar(main.group(0) if main else t)[:4000], "tablas": [limpiar(x)[:1500] for x in re.findall(r"<table.*?</table>", t, re.S)[:3]]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
(OUT / "tesoro.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
