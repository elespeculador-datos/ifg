"""Sonda temporal 9: guardar el script de la ficha de BME y probar rutas de datos de empresa y operaciones."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
r = requests.get("https://www.bolsasymercados.es/etc.clientlibs/bme/components/dynamic/share-details/clientlibs.min.ACSHASH6578360742099df01e9899a2fda039f4.js", headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
(OUT / "share_details.js").write_text(r.text, encoding="utf-8")
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}
def prueba(nombre, ep, params):
    try:
        x = requests.get(A + ep, params=params, headers=H, timeout=60)
        res[nombre] = {"url": x.url, "status": x.status_code, "bytes": len(x.text), "muestra": x.text[:900]}
        if x.status_code == 200:
            (OUT / (re.sub(r"[^A-Za-z0-9_]+", "_", nombre)[:60] + ".json")).write_text(x.text[:600000], encoding="utf-8")
    except Exception as e:
        res[nombre] = {"error": str(e)[:200]}
SAN = "ES0113900J37"
prueba("LastHist_sin", "LastHistoricalSharesPrices", {"tradingSystem": "SIBE"})
prueba("LastHist_isin", "LastHistoricalSharesPrices", {"ISIN": SAN})
prueba("BasicData_isin", "CompanyData/BasicData", {"isin": SAN})
prueba("BasicData_key", "CompanyData/BasicData", {"companyKey": "13900"})
prueba("AllData_key", "CompanyData/AllData", {"companyKey": "13900"})
prueba("ShareDetailsInfo", "ShareDetailsInfo", {"isin": SAN})
prueba("ListedCompanies", "ListedCompanies", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0})
prueba("IndicesGroup", "IndicesGroup", {})
prueba("Delistings", "CorporateActions/Delistings", {"from": "20200101", "to": "20261020", "page": 0, "pageSize": 0})
prueba("NewListings", "CorporateActions/NewListings", {"from": "20200101", "to": "20261020", "page": 0, "pageSize": 0})
prueba("TakeoverBids", "CorporateActions/TakeoverBids", {"from": "20200101", "to": "20261020", "page": 0, "pageSize": 0})
prueba("Splits", "CorporateActions/Splits", {"from": "20200101", "to": "20261020", "page": 0, "pageSize": 0})
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v.get("status") for k, v in res.items()}, indent=1))
