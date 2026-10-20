"""Sonda temporal 16: todas las cotizadas del SIBE (capitalización, índices) y cinco años de cierres de las 35 del IBEX."""
import json, time, csv
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}
def todas(ep, params):
    filas, pagina, info = [], 0, []
    while pagina < 200:
        p = dict(params, page=pagina, pageSize=params.get("pageSize", 0))
        r = requests.get(A + ep, params=p, headers=H, timeout=90)
        j = r.json()
        d = j.get("data") or []
        filas += d
        info.append({"page": pagina, "n": len(d), "total": j.get("totalResults"), "mas": j.get("hasMoreResults"), "eco": j.get("params")})
        if not j.get("hasMoreResults") or not d:
            break
        pagina += 1
        time.sleep(0.3)
    return filas, info
cot, info = todas("ListedCompanies", {"tradingSystem": "SIBE"})
res["listed"] = {"n": len(cot), "paginas": info[:3] + info[-1:]}
(OUT / "cotizadas.json").write_text(json.dumps(cot, ensure_ascii=False), encoding="utf-8")
isins = [f["isin"] for f in csv.DictReader(open("dividendos/ibex35.csv", encoding="utf-8"))]
hist, resumen = {}, {}
for isin in isins:
    try:
        filas, info = todas("HistoricalSharesPrices", {"isin": isin, "from": "20210901", "to": "20261031"})
        hist[isin] = [[f["date"], f["close"], f.get("facMult"), f.get("facDivi")] for f in filas]
        fac = [x for x in hist[isin] if (x[2] or x[3])]
        resumen[isin] = {"n": len(filas), "paginas": len(info), "primera": filas[-1]["date"] if filas else None,
                         "ultima": filas[0]["date"] if filas else None, "con_factor": fac[:6]}
    except Exception as e:
        resumen[isin] = {"error": str(e)[:200]}
    time.sleep(0.3)
res["historicos"] = resumen
(OUT / "historicos.json").write_text(json.dumps(hist), encoding="utf-8")
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
