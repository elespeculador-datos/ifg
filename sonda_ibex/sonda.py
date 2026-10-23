"""Sonda temporal 57 (bis): artículos de la Ley 6/2023 de los Mercados de Valores (BOE-A-2023-7053), la LSSI (BOE-A-2002-13758),
el TRLGDCU (BOE-A-2007-20555) y la Ley de Competencia Desleal (BOE-A-1991-628) por la API del BOE, para la entrada de TNT
«Cómo elegir un curso de bolsa»."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
PEDIDOS = {"BOE-A-2023-7053": ["a124", "a125", "a126", "a127", "a128", "a129", "a130"],
           "BOE-A-2002-13758": ["a10"],
           "BOE-A-2007-20555": ["a102", "a103", "a104", "a105", "a106", "a107"],
           "BOE-A-1991-628": ["a5", "a7", "a8", "a23", "a26", "a27"]}
res = {}
try:
    r = requests.get("https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2023-7053/texto/indice", headers=H, timeout=90)
    ids = re.findall(r"<id>([^<]+)</id>\s*<titulo>([^<]*)</titulo>", r.text)
    res["indice_7053"] = {"http": r.status_code, "bloques": [f"{i} | {t}" for i, t in ids if re.search(r"Art[ií]culo 1[2-3]\d", t)][:40]}
except Exception as e:  # noqa: BLE001
    res["indice_7053"] = {"error": str(e)[:200]}
for ley, bloques in PEDIDOS.items():
    for b in bloques:
        u = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ley}/texto/bloque/{b}"
        try:
            r = requests.get(u, headers=H, timeout=90)
            vers = re.findall(r"<version[^>]*>(.*?)</version>", r.text, re.S)
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", vers[-1] if vers else r.text))).strip()
            res[f"{ley}/{b}"] = {"http": r.status_code, "texto": t[:9000]}
        except Exception as e:  # noqa: BLE001
            res[f"{ley}/{b}"] = {"error": str(e)[:200]}
(OUT / "boe_articulos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
