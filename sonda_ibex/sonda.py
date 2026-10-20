"""Sonda temporal 11: ¿siguen cotizando las 61 acciones de la lista del ITF de 2026? (ficha de BME)"""
import json, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
ISINS = ["ES0148396007", "ES0113900J37", "ES0144580Y14", "ES0113211835", "ES0140609019", "ES0105046017", "ES0130670112", "ES0109067019", "ES0116870314", "ES0177542018", "ES0167050915", "ES0178430E18", "ES0173516115", "ES0105066007", "ES0113860A34", "ES0124244E34", "ES0113679I37", "ES0127797019", "ES0125220311", "ES0173093024", "ES0118594417", "ES0105025003", "ES0105563003", "ES0180907000", "ES0171996087", "ES0171996095", "ES0116920333", "ES0122060314", "ES0137650018", "ES0105027009", "ES0130960018", "ES0105630315", "ES0139140174", "ES0157261019", "ES0182870214", "ES0132105018", "ES0183746314", "ES0112501012", "ES0157097017", "ES0105777017", "ES0129743318", "ES0184262212", "ES0105884011", "ES0178165017", "ES0165386014", "ES0105079000", "ES0117360117", "ES0121975009", "ES0105251005", "ES0126775008", "ES0105122024", "ES0105223004", "ES0176252718", "ES0105836003", "ES0175438003", "ES0134950F36", "ES0173908015", "ES0169501022", "ES0105546008", "ES0109427734", "ES0105287009"]
res = {}
for i in ISINS:
    try:
        x = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/ShareDetailsInfo", params={"isin": i}, headers=H, timeout=30)
        j = x.json() if x.status_code == 200 else {}
        res[i] = {"status": x.status_code, **{k: j.get(k) for k in ("name", "active", "lastClosePrice", "lastClosePriceDate", "capitalisation", "tradingSystem", "market")}}
    except Exception as e:
        res[i] = {"error": str(e)[:200]}
    time.sleep(0.2)
r = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/Delistings", params={"from": "20251201", "to": "20261020", "page": 0, "pageSize": 0}, headers=H, timeout=60)
(OUT / "exclusiones.json").write_text(r.text, encoding="utf-8")
r = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/CorporateActions/TakeoverBids", params={"from": "20200101", "to": "20261020", "page": 0, "pageSize": 0}, headers=H, timeout=60)
(OUT / "opas.json").write_text(r.text, encoding="utf-8")
(OUT / "itf_estado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: (v.get("active"), v.get("lastClosePriceDate")) for k, v in res.items()}))
