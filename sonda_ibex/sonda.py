"""Sonda temporal 18: exclusiones, admisiones, splits/contrasplits, ampliaciones y otros pagos de BME (lo que dé la API) para las piezas del clúster «¿qué pasa con mis acciones si…?»."""
import json, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}
for ep in ["CorporateActions/Delistings", "CorporateActions/NewListings", "CorporateActions/Splits", "CorporateActions/CapitalIncreases",
           "CorporateActions/Mergers", "CorporateActions/OtherPayments", "CorporateActions/PublicOfferings"]:
    nombre = ep.split("/")[1]
    try:
        r = requests.get(A + ep, params={"from": "20000101", "to": "20261231", "page": 0, "pageSize": 0, "tradingSystem": "SIBE", "listingType": "All"}, headers=H, timeout=90)
        j = r.json() if r.status_code == 200 else {"status": r.status_code, "texto": r.text[:300]}
        (OUT / f"{nombre}.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
        d = j.get("data") or []
        res[nombre] = {"status": r.status_code, "n": len(d), "params": j.get("params"), "mas": j.get("hasMoreResults"), "muestra": d[:2]}
    except Exception as e:
        res[nombre] = {"error": str(e)[:200]}
    time.sleep(0.5)
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
