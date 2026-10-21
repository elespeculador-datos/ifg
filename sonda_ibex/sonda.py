"""Sonda temporal 30: el IBEX 35 en las sesiones de vencimiento trimestral de MEFF (tercer viernes de marzo, junio,
septiembre y diciembre) frente al resto de sesiones, con los cierres, máximos y mínimos oficiales de BME."""
import json, statistics as st, time
from datetime import date, timedelta
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Origin": "https://www.bolsasymercados.es"}
API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/HistoricalIndicesPrices"
filas = []
for a, b in [("20201001", "20221231"), ("20230101", "20251231"), ("20260101", "20261231")]:
    r = requests.get(API, params={"pageSize": 0, "page": 0, "ISIN": "ES0SI0000005", "from": a, "to": b, "type": "V"}, headers=H, timeout=90)
    filas += r.json().get("data", [])
    time.sleep(2)
d = sorted({f["date"]: f for f in filas}.values(), key=lambda f: f["date"])
ses = [(date(int(f["date"][:4]), int(f["date"][4:6]), int(f["date"][6:])), float(f["close"]), float(f.get("high") or 0), float(f.get("low") or 0)) for f in d if f.get("close")]
fechas = [s[0] for s in ses]
def tercer_viernes(y, m):
    x = date(y, m, 15)
    while x.weekday() != 4:
        x += timedelta(days=1)
    return x
def sesion_vto(y, m):
    x = tercer_viernes(y, m)
    while x not in fechas and x > date(y, m, 1):
        x -= timedelta(days=1)
    return x if x in fechas else None
filas_out, normales = [], []
idx = {f: i for i, f in enumerate(fechas)}
vtos_trim, vtos_mens = set(), set()
for y in range(2020, 2027):
    for m in range(1, 13):
        v = sesion_vto(y, m)
        if v:
            (vtos_trim if m in (3, 6, 9, 12) else vtos_mens).add(v)
for i in range(1, len(ses)):
    f, c, h, l = ses[i]
    pc = ses[i - 1][1]
    var = (c / pc - 1) * 100
    rango = (h - l) / pc * 100 if h and l else None
    tipo = "trimestral" if f in vtos_trim else ("mensual" if f in vtos_mens else "normal")
    filas_out.append({"fecha": f.isoformat(), "cierre": c, "var_pct": round(var, 2), "rango_pct": None if rango is None else round(rango, 2), "tipo": tipo, "dia": f.weekday()})
def resumen(lst):
    v = [x["var_pct"] for x in lst]; r = [x["rango_pct"] for x in lst if x["rango_pct"] is not None]
    return {"n": len(v), "var_media": round(st.mean(v), 3), "var_mediana": round(st.median(v), 3), "abs_media": round(st.mean(abs(x) for x in v), 3),
            "subidas": sum(1 for x in v if x > 0), "bajadas": sum(1 for x in v if x < 0), "rango_medio": round(st.mean(r), 3) if r else None}
desde = "2021-10-01"
sel = [x for x in filas_out if x["fecha"] >= desde]
res = {"desde": sel[0]["fecha"], "hasta": sel[-1]["fecha"],
       "trimestral": resumen([x for x in sel if x["tipo"] == "trimestral"]),
       "mensual": resumen([x for x in sel if x["tipo"] == "mensual"]),
       "viernes_normales": resumen([x for x in sel if x["tipo"] == "normal" and x["dia"] == 4]),
       "todas_las_sesiones": resumen(sel),
       "detalle_trimestral": [x for x in sel if x["tipo"] == "trimestral"],
       "proximos": {"2026-12": sesion_vto(2026, 12) and sesion_vto(2026, 12).isoformat(),
                    "tercer_viernes_2027": [tercer_viernes(2027, m).isoformat() for m in range(1, 13)]}}
(OUT / "hora_bruja.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "detalle_trimestral"}, ensure_ascii=False))
