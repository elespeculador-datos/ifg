"""Sonda temporal 5: dividendos de BME en un rango amplio (para probar el calendario)."""
import json
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/Dividends"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bolsasymercados.es/"}
res = {}
todo = []
for desde, hasta in [("20210101", "20231231"), ("20240101", "20251231"), ("20260101", "20271231")]:
    r = requests.get(API, params={"companyKey": "", "from": desde, "to": hasta, "page": 0, "pageSize": 0, "tradingSystem": "SIBE", "listingType": "All"}, headers=H, timeout=90)
    j = r.json(); res[desde] = {"status": r.status_code, "total": j.get("totalResults"), "mas": j.get("hasMoreResults"), "n": len(j.get("data", []))}
    todo += j.get("data", [])
(OUT / "dividendos.json").write_text(json.dumps(todo, ensure_ascii=False), encoding="utf-8")
r = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/CompanySearch", params={"search": "", "complete": "false", "tradingSystem": "SIBE", "page": 0, "pageSize": 0, "mtfSegment": ""}, headers=H, timeout=60)
(OUT / "empresas.json").write_text(r.text, encoding="utf-8")
# composición del IBEX 35 si existe un endpoint
for u in ["https://apiweb.bolsasymercados.es/Market/v1/EQ/IndexComponents?ISIN=ES0SI0000005",
          "https://apiweb.bolsasymercados.es/Market/v1/EQ/IndicesComponents?ISIN=ES0SI0000005",
          "https://apiweb.bolsasymercados.es/Market/v1/EQ/IndexValues?ISIN=ES0SI0000005"]:
    try:
        rr = requests.get(u, headers=H, timeout=60); res[u] = {"status": rr.status_code, "muestra": rr.text[:400]}
    except Exception as e:
        res[u] = {"error": str(e)[:200]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
