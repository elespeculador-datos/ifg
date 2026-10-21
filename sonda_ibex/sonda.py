"""Sonda temporal 25: ficha de BME de la clase B de Grifols (no está en la lista de cotizadas) y de la clase A, para comparar campos."""
import json
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}
B = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}
for isin in ("ES0171996095", "ES0171996087", "ES0105777017"):
    r = requests.get(B + "ShareDetailsInfo", params={"isin": isin}, headers=H, timeout=60)
    res[isin] = {"http": r.status_code, "json": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500]}
    r2 = requests.get(B + "HistoricalSharesPrices", params={"isin": isin, "from": "20261015", "to": "20261031", "pageSize": 0, "page": 0}, headers=H, timeout=60)
    res[isin]["hist_http"] = r2.status_code
    res[isin]["hist"] = r2.json().get("data", [])[-2:] if r2.status_code == 200 else r2.text[:300]
(OUT / "fichas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
