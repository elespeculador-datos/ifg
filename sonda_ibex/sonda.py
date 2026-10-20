"""Sonda temporal 13: histórico completo de OPAs en la API de BME (CorporateActions/TakeoverBids)."""
import json
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/"
res = {}
for nombre, desde in [("desde1990", "19900101"), ("desde2005", "20050101"), ("desde2015", "20150101")]:
    r = requests.get(A + "TakeoverBids", params={"from": desde, "to": "20261231", "page": 0, "pageSize": 0}, headers=H, timeout=60)
    res[nombre] = {"status": r.status_code, "bytes": len(r.text)}
    if r.status_code == 200:
        j = r.json(); res[nombre].update({"total": j.get("totalResults"), "params": j.get("params")})
        (OUT / f"opas_{nombre}.json").write_text(r.text, encoding="utf-8")
# una OPA concreta con companyKey (Sabadell) por si da más campos
r = requests.get(A + "TakeoverBids", params={"companyKey": "13860", "from": "20200101", "to": "20261231", "page": 0, "pageSize": 0}, headers=H, timeout=60)
(OUT / "opa_sabadell.json").write_text(r.text, encoding="utf-8")
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
