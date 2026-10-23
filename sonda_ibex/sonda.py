"""Sonda temporal 60: RD 813/2023 (BOE-A-2023-22763), artículos 1 a 15, y Resolución CNMV de 11/07/2023 sobre CFD (BOE-A-2023-16394)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
limpia = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
res = {}
base = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2023-22763/texto/"
r = requests.get(base + "indice", headers=H, timeout=90)
res["indice_http"] = r.status_code
bloques = re.findall(r"<bloque>\s*<id>(.*?)</id>\s*<titulo>(.*?)</titulo>", r.text, re.S)
res["indice"] = [[i, limpia(t)] for i, t in bloques][:200]
if not bloques:
    res["indice_crudo"] = r.text[:4000]
for i, t in bloques:
    m = re.match(r"Artículo (\d+)\.", limpia(t))
    if m and int(m.group(1)) <= 15:
        rb = requests.get(base + "bloque/" + i, headers=H, timeout=90)
        vers = re.findall(r"<version[^>]*>(.*?)</version>", rb.text, re.S)
        res[i] = {"http": rb.status_code, "titulo": limpia(t), "texto": limpia(vers[-1] if vers else rb.text)[:9000]}
r = requests.get("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2023-16394", headers={"User-Agent": H["User-Agent"]}, timeout=90)
m = re.search(r'<div id="textoxslt".*?</div>\s*</div>', r.text, re.S)
res["resolucion_cfd"] = {"http": r.status_code, "texto": limpia(m.group(0) if m else r.text)[:60000]}
(OUT / "boe_rd813_cfd.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
