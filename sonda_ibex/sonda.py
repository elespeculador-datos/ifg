"""Sonda temporal 12: cabeceras del fichero de posiciones cortas de la CNMV (¿a qué hora se actualiza?)."""
import json
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
res = {}
for u in ["https://www.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls",
          "https://www.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xlsx"]:
    for m in ("head", "get"):
        try:
            r = requests.request(m, u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, stream=True)
            res[f"{m} {u[-25:]}"] = {"status": r.status_code, **{k: r.headers.get(k) for k in ("Last-Modified", "Date", "ETag", "Content-Length", "Content-Type")}}
            r.close()
        except Exception as e:
            res[f"{m} {u[-25:]}"] = {"error": str(e)[:200]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
