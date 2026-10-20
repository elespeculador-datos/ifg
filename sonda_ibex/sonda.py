"""Sonda temporal 10: cierre y capitalización (ShareDetailsInfo de BME) de las empresas con dividendo en el último año."""
import csv, io, json, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
u = requests.get("https://elespeculador-datos.github.io/ifg/dividendos/datos/ultimos_12m.csv", timeout=60).text
isins = sorted({r["isin"] for r in csv.DictReader(io.StringIO(u))})
res, t0 = {}, time.time()
for i in isins:
    try:
        x = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/ShareDetailsInfo", params={"isin": i}, headers=H, timeout=30)
        res[i] = x.json() if x.status_code == 200 else {"status": x.status_code, "texto": x.text[:200]}
        if isinstance(res[i], dict):
            res[i].pop("otherShares", None); res[i].pop("otherSharesFromIssuer", None)
    except Exception as e:
        res[i] = {"error": str(e)[:200]}
    time.sleep(0.2)
(OUT / "cotizaciones.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(isins), "isins en", round(time.time() - t0, 1), "s;", sum(1 for v in res.values() if "lastClosePrice" in v), "con cierre")
