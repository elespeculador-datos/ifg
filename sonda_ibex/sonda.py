"""Sonda temporal 8: rutas de la API que usan los scripts de la web de BME (fichas, explorador de acciones, índices)."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0"}
scripts = [
 "https://www.bolsasymercados.es/etc.clientlibs/bme/clientlibs/clientlib-site.min.ACSHASH617b9eedf499783f395d1de693753e55.js",
 "https://www.bolsasymercados.es/etc.clientlibs/bme/components/dynamic/index-ticker/clientlibs.min.ACSHASH2e0cf17fad790c04f6ef7a73d980fda6.js",
 "https://www.bolsasymercados.es/etc.clientlibs/bme/components/dynamic/market-activity/clientlibs.min.ACSHASHc7f709e6c56ae41a12d18e0af11c41de.js",
 "https://www.bolsasymercados.es/etc.clientlibs/bme/components/dynamic/share-details/clientlibs.min.ACSHASH6578360742099df01e9899a2fda039f4.js",
 "https://www.bolsasymercados.es/etc.clientlibs/bme/components/dynamic/shares-explorer/clientlibs.min.ACSHASHf6e046f0ac5f93cda8327ab06474b2bc.js",
 "https://www.bolsasymercados.es/etc.clientlibs/bme/clientlibs/clientlib-base.min.ACSHASH86b9d387dd6a9ac638344b5a4522ed15.js",
]
res = {}
for s in scripts:
    try:
        r = requests.get(s, headers=H, timeout=60)
        t = r.text
        nombre = s.split("/components/")[-1].split("/clientlibs")[0] if "/components/" in s else s.split("/")[-1][:40]
        hall = set(re.findall(r'["\'`/](EQ/[A-Za-z0-9_/]+)', t)) | set(re.findall(r'["\'`]([A-Za-z]+/v\d/[A-Za-z0-9_/]+)', t))
        ctx = []
        for m in re.finditer(r'EQ/[A-Za-z0-9_]+', t):
            ctx.append(t[max(0, m.start() - 160): m.end() + 220])
        res[nombre] = {"status": r.status_code, "bytes": len(t), "rutas": sorted(hall), "contexto": ctx[:40]}
    except Exception as e:
        res[s] = {"error": str(e)[:200]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v.get("rutas") for k, v in res.items()}, ensure_ascii=False, indent=1))
