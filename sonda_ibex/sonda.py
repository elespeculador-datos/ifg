"""Sonda temporal 58: índice de la Ley 6/2023 (BOE-A-2023-7053) y los artículos de reserva de actividad."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Accept": "application/xml"}
B = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2023-7053/texto"
res = {}
r = requests.get(B + "/indice", headers=H, timeout=90)
res["indice_http"] = r.status_code
(OUT / "indice_7053.xml").write_text(r.text)
bloques = re.findall(r"<bloque>(.*?)</bloque>", r.text, re.S)
lista = []
for b in bloques:
    i = re.search(r"<id>([^<]+)</id>", b); t = re.search(r"<titulo>([^<]*)</titulo>", b)
    lista.append(((i.group(1) if i else ""), html.unescape(t.group(1) if t else "")))
res["n_bloques"] = len(lista)
res["muestra"] = [f"{i} | {t}" for i, t in lista if re.search(r"Art[ií]culo 1(2[0-9]|3[0-5])\b|[Rr]eserva", t)][:30]
for i, t in lista:
    if re.search(r"Art[ií]culo 1(2[4-9]|30)\.", t) or re.search(r"Art[ií]culo 1(2[4-9]|30)$", t):
        rr = requests.get(f"{B}/bloque/{i}", headers=H, timeout=90)
        vers = re.findall(r"<version[^>]*>(.*?)</version>", rr.text, re.S)
        res[i] = {"titulo": t, "http": rr.status_code,
                  "texto": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", vers[-1] if vers else rr.text))).strip()[:9000]}
(OUT / "boe_7053.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
