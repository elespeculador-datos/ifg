"""Sonda temporal 56: salidas a bolsa. Empresas cotizadas del SIBE, ofertas públicas 2000-2026, admisiones y exclusiones del último año
y precios históricos (cinco años) de las salidas recientes, de la API de BME."""
import json, re, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json"}
def get(ruta, params):
    for i in range(3):
        try:
            r = requests.get(API + ruta, params=params, headers=H, timeout=60)
            if r.status_code == 200:
                return r.json()
            err = f"http {r.status_code} {r.text[:200]}"
        except Exception as e:  # noqa: BLE001
            err = str(e)[:200]
        time.sleep(3)
    return {"error": err}
res = {}
res["listed"] = get("ListedCompanies", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0})
res["offerings"] = get("CorporateActions/PublicOfferings", {"from": "20000101", "to": "20261231", "page": 0, "pageSize": 0})
res["newlistings"] = get("CorporateActions/NewListings", {"from": "20000101", "to": "20261231", "page": 0, "pageSize": 0})
res["delistings"] = get("CorporateActions/Delistings", {"from": "20000101", "to": "20261231", "page": 0, "pageSize": 0})
listed = res["listed"].get("data", []) if isinstance(res["listed"], dict) else []
objetivo = re.compile(r"PUIG|HBX|CIRSA|ACCIONA ENER|ECOENER|OPDENERG|LINEA DIRECTA|L[IÍ]NEA DIRECTA|SOLTEC|INMOCEMENTO|ARIMA|NEINOR|AEDAS|METROVACESA|UNICAJA", re.I)
hist = {}
nuevos = set()
for d in (res["newlistings"].get("data", []) if isinstance(res["newlistings"], dict) else []):
    for k in ("isin", "shareIsin", "ISIN"):
        if d.get(k):
            nuevos.add(d[k])
for c in listed:
    if objetivo.search(c.get("name", "") + " " + c.get("shareName", "")) or c.get("isin") in nuevos:
        j = get("HistoricalSharesPrices", {"isin": c["isin"], "from": "20211001", "to": "20261231", "page": 0, "pageSize": 0})
        hist[c["isin"]] = {"name": c.get("name"), "shareName": c.get("shareName"), "resp": j}
        time.sleep(1)
res["hist"] = hist
(OUT / "salidas.json").write_text(json.dumps(res, ensure_ascii=False))
print("ok", len(listed), len(hist))
