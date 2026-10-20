"""Sonda temporal 3: histórico completo del IBEX 35 desde la API de BME."""
import json
from pathlib import Path
import pandas as pd
import requests

OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/HistoricalIndicesPrices"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}
res = {}
filas = []
for a in range(1989, 2027, 5):
    p = {"pageSize": 0, "page": 0, "ISIN": "ES0SI0000005", "from": f"{a}0101", "to": f"{min(a + 4, 2026)}1231", "type": "V"}
    try:
        r = requests.get(API, params=p, headers=H, timeout=60)
        j = r.json()
        res[str(a)] = {"status": r.status_code, "total": j.get("totalResults"), "mas": j.get("hasMoreResults"), "n": len(j.get("data", []))}
        filas += j.get("data", [])
    except Exception as e:
        res[str(a)] = {"error": str(e)[:300]}
# Sin cabeceras, para saber si hacen falta
try:
    r = requests.get(API, params={"pageSize": 0, "page": 0, "ISIN": "ES0SI0000005", "from": "20261001", "to": "20261020", "type": "V"}, timeout=60)
    res["sin_cabeceras"] = {"status": r.status_code, "n": len(r.json().get("data", []))}
except Exception as e:
    res["sin_cabeceras"] = {"error": str(e)[:300]}
df = pd.DataFrame(filas).drop_duplicates("date").sort_values("date")
df.to_csv(OUT / "ibex_bme.csv", index=False)
res["primera"] = df["date"].iloc[0] if len(df) else None
res["ultima"] = df["date"].iloc[-1] if len(df) else None
res["filas"] = len(df)
claves = ["19891229", "19921005", "20071108", "20241231", "20251231", "20260804", "20260811", "20260813", "20261016"]
res["control"] = df[df["date"].isin(claves)].to_dict("records")
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
