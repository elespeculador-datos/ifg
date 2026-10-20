"""Sonda temporal 17: ¿cuándo aparece el cierre del día del IBEX 35 en la API de BME?"""
import json, time
from datetime import datetime, timezone
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {"hora_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
for nombre, ep, params in [
    ("hist", "HistoricalIndicesPrices", {"pageSize": 0, "page": 0, "ISIN": "ES0SI0000005", "from": "20261014", "to": "20261031", "type": "V"}),
    ("last", "LastHistoricalIndicesPrices", {"ISIN": "ES0SI0000005"}),
    ("last_isin", "LastHistoricalIndicesPrices", {"isin": "ES0SI0000005"}),
    ("last_tipo", "LastHistoricalIndicesPrices", {"ISIN": "ES0SI0000005", "type": "V"}),
    ("acc_hist", "HistoricalSharesPrices", {"isin": "ES0144580Y14", "from": "20261014", "to": "20261031"}),
    ("acc_last", "LastHistoricalSharesPrices", {"isin": "ES0144580Y14"}),
]:
    try:
        r = requests.get(A + ep, params=params, headers=H, timeout=60)
        try:
            j = r.json()
        except ValueError:
            j = {"texto": r.text[:300]}
        d = j.get("data") if isinstance(j, dict) else j
        res[nombre] = {"status": r.status_code, "filas": [{k: x.get(k) for k in ("date", "close", "previous", "diff")} for x in (d or [])][-6:] if isinstance(d, list) else j}
    except Exception as e:
        res[nombre] = {"error": str(e)[:200]}
    time.sleep(0.5)
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
