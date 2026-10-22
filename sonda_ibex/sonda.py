"""Sonda temporal 54: texto refundido de la Ley Concursal (BOE-A-2020-4859) por la API de legislación consolidada del BOE.
Índice completo y artículos que mencionan a los socios o accionistas, la liquidación, la disolución o los planes de reestructuración."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
BASE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2020-4859"
res = {"indice": None, "articulos": {}, "errores": []}
def limpio(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
try:
    r = requests.get(BASE + "/texto/indice", headers=H, timeout=120)
    res["indice_http"] = r.status_code
    bloques = re.findall(r"<bloque>(.*?)</bloque>", r.text, re.S)
    ind = []
    for b in bloques:
        i = re.search(r"<id>(.*?)</id>", b); t = re.search(r"<titulo>(.*?)</titulo>", b)
        ind.append([i.group(1) if i else "", limpio(t.group(1)) if t else ""])
    res["indice"] = ind
except Exception as e:  # noqa: BLE001
    res["errores"].append("indice: " + str(e)[:200])
try:
    r = requests.get(BASE + "/texto", headers=H, timeout=180)
    res["texto_http"] = r.status_code; res["texto_len"] = len(r.text)
    for m in re.finditer(r'<bloque id="([^"]+)"[^>]*>(.*?)</bloque>', r.text, re.S):
        bid, cuerpo = m.group(1), m.group(2)
        if not bid.startswith("a"):
            continue
        # última versión del bloque
        vers = re.findall(r"<version[^>]*>(.*?)</version>", cuerpo, re.S)
        t = limpio(vers[-1] if vers else cuerpo)
        if re.search(r"\bsocio|accionist|reestructuraci|liquidaci[oó]n|disoluci[oó]n|extinci[oó]n de la persona|capitalizaci", t, re.I):
            res["articulos"][bid] = t[:6000]
except Exception as e:  # noqa: BLE001
    res["errores"].append("texto: " + str(e)[:200])
(OUT / "trlc.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok", len(res["articulos"]))
