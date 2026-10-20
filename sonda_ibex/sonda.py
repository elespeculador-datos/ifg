"""Sonda temporal 7: descubrir en la API de BME los precios de acciones y la composición del IBEX 35."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
res = {}

def prueba(nombre, url, params=None):
    try:
        r = requests.get(url, params=params, headers=H, timeout=60)
        res[nombre] = {"url": r.url, "status": r.status_code, "tipo": r.headers.get("content-type"), "muestra": r.text[:700]}
        if r.status_code == 200 and len(r.text) > 50:
            (OUT / (re.sub(r"[^A-Za-z0-9_]+", "_", nombre)[:60] + ".txt")).write_text(r.text[:400000], encoding="utf-8")
    except Exception as e:
        res[nombre] = {"url": url, "error": str(e)[:200]}

# 1) Precios históricos de una acción (Santander), por analogía con HistoricalIndicesPrices
for ep in ["HistoricalSharePrices", "HistoricalSharesPrices", "HistoricalPrices", "SharesHistoricalPrices"]:
    prueba(ep, A + ep, {"ISIN": "ES0113900J37", "from": "20261001", "to": "20261020", "page": 0, "pageSize": 0, "tradingSystem": "SIBE"})
# 2) Precios del día y fichas
for ep, p in [("SharesPrices", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0}),
              ("SharePrices", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0}),
              ("Shares", {"tradingSystem": "SIBE", "page": 0, "pageSize": 0}),
              ("ShareDetails", {"ISIN": "ES0113900J37"}),
              ("ShareDetail", {"ISIN": "ES0113900J37"}),
              ("CompanyDetails", {"companyKey": "13900"}),
              ("IndexPrices", {"ISIN": "ES0SI0000005"}),
              ("IndicesPrices", {}),
              ("IndexConstituents", {"ISIN": "ES0SI0000005"}),
              ("IndexShares", {"ISIN": "ES0SI0000005"}),
              ("IndexComposition", {"ISIN": "ES0SI0000005"}),
              ("IndicesShares", {"ISIN": "ES0SI0000005"})]:
    prueba(ep, A + ep, p)
# 3) Rutas que usa la web de BME: descargar las páginas y sus scripts y buscar "/Market/v1/..."
rutas = set()
paginas = ["https://www.bolsasymercados.es/bme-exchange/es/Mercados-y-Cotizaciones/Acciones/Mercado-Continuo/Precios/ibex-35-ES0SI0000005",
           "https://www.bolsasymercados.es/bme-exchange/es/Mercados-y-Cotizaciones/Indices/Familia/ibex-35",
           "https://www.bolsasymercados.es/bme-exchange/es/Mercados-y-Cotizaciones/Acciones/Mercado-Continuo/Ficha/BANCO-SANTANDER-ES0113900J37",
           "https://www.bolsasymercados.es/bme-exchange/es/Mercados-y-Cotizaciones/Acciones/Mercado-Continuo/Precios/mercado-continuo"]
scripts = set()
for u in paginas:
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        res["pagina " + u[-40:]] = {"status": r.status_code, "bytes": len(r.text)}
        for m in re.findall(r'<script[^>]+src="([^"]+)"', r.text):
            scripts.add(requests.compat.urljoin(u, m))
        rutas.update(re.findall(r'(?:Market|Publisher|Info)/v\d/[A-Za-z0-9_/\-{}$.]+', r.text))
    except Exception as e:
        res["pagina " + u[-40:]] = {"error": str(e)[:200]}
res["scripts"] = sorted(scripts)[:80]
for s in sorted(scripts)[:60]:
    try:
        r = requests.get(s, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        rutas.update(re.findall(r'(?:Market|Publisher|Info)/v\d/[A-Za-z0-9_/\-{}$.]+', r.text))
        for m in re.findall(r'["\']([^"\']*apiweb[^"\']*)["\']', r.text):
            rutas.add(m)
    except Exception:
        pass
res["rutas"] = sorted(rutas)
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: (v.get("status") if isinstance(v, dict) else len(v)) for k, v in res.items()}, ensure_ascii=False, indent=1))
