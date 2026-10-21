"""Sonda temporal 24: variación en el año de cada cotizada con precios ajustados frente al annualDifference de BME,
y última sesión con cotización (para detectar valores suspendidos)."""
import json, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}
B = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
lista = requests.get(B + "ListedCompanies", params={"tradingSystem": "SIBE", "page": 0, "pageSize": 0}, headers=H, timeout=90).json()["data"]
res, crudo = [], {}
for c in lista:
    filas, err = [], None
    for intento in range(3):
        try:
            r = requests.get(B + "HistoricalSharesPrices", params={"isin": c["isin"], "from": "20251201", "to": "20261031", "pageSize": 0, "page": 0}, headers=H, timeout=60)
            if r.status_code == 200:
                filas = r.json().get("data", []); err = None; break
            err = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            err = str(e)
        time.sleep(3)
    if c["isin"] in ("ES0115002018", "ES0125220311", "ES0114400007"):
        crudo[c["isin"]] = filas[:3] + filas[-3:]
    f25 = [f for f in filas if str(f.get("date", "")).startswith("2025")]
    f26 = [f for f in filas if str(f.get("date", "")).startswith("2026")]
    def cierre(f):
        for k in ("close", "closePrice", "price", "last"):
            if f.get(k) not in (None, 0):
                return float(f[k])
        return None
    c25 = cierre(f25[-1]) if f25 else None
    c26 = cierre(f26[-1]) if f26 else None
    res.append({"isin": c["isin"], "nombre": c.get("shareName"), "annualDifference": c.get("annualDifference"),
                "cap": c.get("capitalisation"), "ultima_sesion": f26[-1].get("date") if f26 else None,
                "sesiones_2026": len(f26), "cierre_2025": c25, "ultimo": c26,
                "ytd_ajustado": round(c26 / c25 - 1, 4) if c25 and c26 else None, "error": err})
    time.sleep(0.4)
(OUT / "variacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=0))
(OUT / "crudo.json").write_text(json.dumps(crudo, ensure_ascii=False, indent=1))
print(len(res), sum(1 for r in res if r["error"]))
