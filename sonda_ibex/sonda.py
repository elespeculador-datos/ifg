"""Sonda temporal 14: ¿hasta dónde llega el histórico de las operaciones societarias de BME si se pide año a año?"""
import json, time
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}
for ep in ["CorporateActions/Dividends", "CorporateActions/Delistings", "CorporateActions/NewListings", "CorporateActions/Splits",
           "CorporateActions/CapitalIncreases", "CorporateActions/PublicOfferings", "CorporateActions/Mergers"]:
    res[ep] = {}
    for anio in [2025, 2020, 2015, 2010, 2005, 2000]:
        try:
            r = requests.get(A + ep, params={"from": f"{anio}0101", "to": f"{anio}1231", "page": 0, "pageSize": 0}, headers=H, timeout=60)
            j = r.json() if r.status_code == 200 else {}
            res[ep][anio] = {"status": r.status_code, "total": j.get("totalResults"), "params": j.get("params"),
                             "muestra": (j.get("data") or [None])[0]}
        except Exception as e:
            res[ep][anio] = {"error": str(e)[:150]}
        time.sleep(0.3)
# composición del IBEX con coeficientes (PDF de BME) y ficha con pesos
for nombre, u in [("composicion", "https://www.bolsasymercados.es/dam/descargas/indices/composicion-ibex-35-es-en.pdf"),
                  ("factsheet", "https://www.bolsasymercados.es/dam/descargas/indices/factsheet-ibex-35-es.pdf")]:
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        res[nombre] = {"status": r.status_code, "bytes": len(r.content), "tipo": r.headers.get("content-type"), "last_modified": r.headers.get("Last-Modified")}
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            p = OUT / f"{nombre}.pdf"; p.write_bytes(r.content)
            import subprocess
            subprocess.run(["pdftotext", "-layout", str(p), str(p.with_suffix(".txt"))], check=False)
    except Exception as e:
        res[nombre] = {"error": str(e)[:150]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
