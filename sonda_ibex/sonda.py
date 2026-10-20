"""Sonda temporal 21 (IRPF): artículos de normas del BOE (API de legislación consolidada), buscando el bloque por su título."""
import json, re, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{id}/texto/{q}"
H = {"Accept": "application/xml", "User-Agent": "Mozilla/5.0 (El Especulador, verificación)"}
NORMAS = {
    "BOE-A-2006-20764": [25, 33, 37, 46, 49, 101],   # Ley 35/2006 del IRPF
    "BOE-A-2007-6820": [75, 90, 93],                  # Reglamento del IRPF (RD 439/2007)
}
res = {}
def texto(xml: str) -> str:
    t = re.sub(r"<[^>]+>", " ", xml)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()
for norma, arts in NORMAS.items():
    res[norma] = {}
    r = requests.get(API.format(id=norma, q="indice"), headers=H, timeout=60)
    res[norma]["indice"] = r.status_code
    bloques = re.findall(r"<bloque>(.*?)</bloque>", r.text, re.S)
    por_num = {}
    for b in bloques:
        i = re.search(r"<id>(.*?)</id>", b); t = re.search(r"<titulo>(.*?)</titulo>", b, re.S)
        if i and t:
            m = re.match(r"Art[íi]culo\s*(\d+)", t.group(1).replace("\xa0", " ").strip())
            if m and int(m.group(1)) not in por_num:
                por_num[int(m.group(1))] = i.group(1)
    for a in arts:
        bid = por_num.get(a)
        if not bid:
            res[norma][a] = "sin bloque"; continue
        rr = requests.get(API.format(id=norma, q=f"bloque/{bid}"), headers=H, timeout=60)
        (OUT / f"{norma}_art{a}.txt").write_text(texto(rr.text), encoding="utf-8")
        res[norma][a] = [bid, rr.status_code, len(rr.text)]
        time.sleep(0.4)
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok")
