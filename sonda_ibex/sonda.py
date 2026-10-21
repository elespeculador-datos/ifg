"""Sonda temporal 53: artículos de la Ley de Sociedades de Capital y de la Ley del IRPF por la API de legislación consolidada del BOE."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
PEDIDOS = {"BOE-A-2010-10544": ["a303", "a304", "a305", "a306", "a308", "a503", "a504", "a505", "a506"],
           "BOE-A-2006-20764": ["a37", "a101"]}
res = {}
for ley, bloques in PEDIDOS.items():
    for b in bloques:
        u = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ley}/texto/bloque/{b}"
        try:
            r = requests.get(u, headers=H, timeout=90)
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r.text))).strip()
            res[f"{ley}/{b}"] = {"http": r.status_code, "texto": t[:12000]}
        except Exception as e:  # noqa: BLE001
            res[f"{ley}/{b}"] = {"error": str(e)[:200]}
(OUT / "boe_articulos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
