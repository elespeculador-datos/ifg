"""Sonda temporal 55: artículos sueltos de la Ley Concursal (BOE-A-2020-4859) y de la Ley de Sociedades de Capital (BOE-A-2010-10544) por la API del BOE."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
PEDIDOS = {"BOE-A-2020-4859": ["a5", "a1-18", "a1-19", "a1-20", "a1-39", "a1-40", "a1-41", "a2-81", "a2-92", "a2-93",
                               "a4-41", "a4-42", "a4-45", "a4-47", "a4-48", "a4-49", "a4-55", "a4-56", "a4-57", "a4-58", "a4-59", "a4-60"],
           "BOE-A-2010-10544": ["a363", "a365", "a367"]}
res = {}
for ley, bloques in PEDIDOS.items():
    for b in bloques:
        u = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ley}/texto/bloque/{b}"
        try:
            r = requests.get(u, headers=H, timeout=90)
            vers = re.findall(r"<version[^>]*>(.*?)</version>", r.text, re.S)
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", vers[-1] if vers else r.text))).strip()
            res[f"{ley}/{b}"] = {"http": r.status_code, "texto": t[:8000]}
        except Exception as e:  # noqa: BLE001
            res[f"{ley}/{b}"] = {"error": str(e)[:200]}
(OUT / "boe_articulos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
