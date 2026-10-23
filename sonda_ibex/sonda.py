"""Sonda temporal 59: artículos 124 a 130 de la Ley 6/2023 (BOE-A-2023-7053, bloques a1-36 a a1-42)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
B = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2023-7053/texto/bloque/"
res = {}
for n in range(36, 43):
    b = f"a1-{n}"
    r = requests.get(B + b, headers=H, timeout=90)
    vers = re.findall(r"<version[^>]*>(.*?)</version>", r.text, re.S)
    res[b] = {"http": r.status_code, "texto": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", vers[-1] if vers else r.text))).strip()[:12000]}
(OUT / "boe_7053_arts.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
