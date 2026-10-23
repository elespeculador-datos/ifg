"""Sonda temporal 61: RD 813/2023 (BOE-A-2023-22763), artículos 1 a 15."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
limpia = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
base = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2023-22763/texto/bloque/"
res = {}
for i in [f"a{n}" for n in range(1, 10)] + [f"a1-{n}" for n in range(2, 8)]:
    rb = requests.get(base + i, headers=H, timeout=90)
    vers = re.findall(r"<version[^>]*>(.*?)</version>", rb.text, re.S)
    res[i] = {"http": rb.status_code, "texto": limpia(vers[-1] if vers else rb.text)[:9000]}
(OUT / "boe_rd813_arts.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
