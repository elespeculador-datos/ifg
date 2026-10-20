"""Sonda temporal 19: artículos de normas del BOE (API de datos abiertos de legislación consolidada) para verificar piezas."""
import json, re, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{id}/texto/{q}"
H = {"Accept": "application/xml", "User-Agent": "Mozilla/5.0 (El Especulador, verificación)"}
NORMAS = {
    "BOE-A-2023-7053": ["a52", "a64", "a65", "a116", "a117", "a118", "a119", "a120"],   # Ley 6/2023 de los Mercados de Valores
    "BOE-A-2007-14398": ["a10", "a11", "a47", "a48"],                                    # RD 1066/2007 de OPAs
    "BOE-A-2010-10544": ["a285", "a286", "a287", "a288", "a290", "a291"],                # Ley de Sociedades de Capital
}
res = {}
def texto(xml: str) -> str:
    t = re.sub(r"<[^>]+>", " ", xml)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()
for norma, arts in NORMAS.items():
    res[norma] = {}
    try:
        r = requests.get(API.format(id=norma, q="indice"), headers=H, timeout=60)
        (OUT / f"{norma}_indice.xml").write_text(r.text, encoding="utf-8")
        res[norma]["indice"] = [r.status_code, len(r.text)]
        ids = re.findall(r"<id>([^<]+)</id>", r.text)
        res[norma]["ids_muestra"] = ids[:15]
    except Exception as e:
        res[norma]["indice"] = str(e)[:200]
    for a in arts:
        try:
            r = requests.get(API.format(id=norma, q=f"bloque/{a}"), headers=H, timeout=60)
            (OUT / f"{norma}_{a}.txt").write_text(texto(r.text), encoding="utf-8")
            res[norma][a] = [r.status_code, len(r.text)]
        except Exception as e:
            res[norma][a] = str(e)[:200]
        time.sleep(0.5)
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok")
