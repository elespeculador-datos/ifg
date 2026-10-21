"""Sonda temporal 52: Orden ECM/2/2026 (creación de Deuda del Estado 2026), fórmulas de precio de las Letras."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
res = {}
for u in ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-678", "https://www.boe.es/buscar/doc.php?id=BOE-A-2026-678"]:
    try:
        r = requests.get(u, headers=H, timeout=90)
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S))))
        titulo = re.search(r"Orden [A-Z]+/\d+/\d{4}[^.]{0,200}", t)
        trozos = []
        for m in re.finditer(r"360|redonde|Letras del Tesoro", t):
            trozos.append(t[max(0, m.start() - 700):m.start() + 700])
        res[u] = {"http": r.status_code, "titulo": titulo.group(0) if titulo else None, "len": len(t), "trozos": trozos[:25]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
(OUT / "orden.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
