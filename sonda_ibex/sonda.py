"""Sonda temporal 22: ¿trae ya el histórico de BME el cierre del IBEX del 20/10/2026? (hora de la ejecución en UTC)."""
import json, datetime
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}
r = requests.get("https://apiweb.bolsasymercados.es/Market/v1/EQ/HistoricalIndicesPrices",
                 params={"pageSize": 0, "page": 0, "ISIN": "ES0SI0000005", "from": "20261014", "to": "20261021", "type": "V"}, headers=H, timeout=90)
d = r.json().get("data", []) if r.status_code == 200 else []
res = {"hora_utc": datetime.datetime.utcnow().isoformat(timespec="seconds"), "http": r.status_code,
       "filas": [{k: x.get(k) for k in ("date", "close", "high", "low")} for x in d]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False))
