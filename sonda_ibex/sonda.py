"""Sonda temporal 15: fichas de empresa de la web (páginas, contenido, robots) y datos de BME para un bloque por empresa."""
import json, time, csv
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
res = {}
# ---------------------------------------------------------------- web: todas las páginas publicadas
W = "https://elespeculador.com/wp-json/wp/v2/pages"
UA = {"User-Agent": "Mozilla/5.0 (El Especulador, sonda de datos)"}
paginas = []
for n in range(1, 10):
    try:
        r = requests.get(W, params={"per_page": 100, "page": n, "_fields": "id,slug,parent,link,title,modified,template,yoast_head_json"}, headers=UA, timeout=60)
    except Exception as e:
        res[f"paginas_{n}"] = str(e)[:200]; break
    if r.status_code != 200:
        res[f"paginas_{n}"] = r.status_code; break
    j = r.json()
    if not j:
        break
    for p in j:
        y = p.get("yoast_head_json") or {}
        paginas.append({"id": p["id"], "slug": p["slug"], "parent": p["parent"], "link": p["link"], "title": (p.get("title") or {}).get("rendered"),
                        "modified": p.get("modified"), "template": p.get("template"), "robots": y.get("robots"), "yoast_title": y.get("title"),
                        "canonical": y.get("canonical")})
    time.sleep(0.5)
(OUT / "paginas.json").write_text(json.dumps(paginas, ensure_ascii=False, indent=1), encoding="utf-8")
res["paginas"] = len(paginas)
padres = {}
for p in paginas:
    padres.setdefault(p["parent"], 0); padres[p["parent"]] += 1
res["por_padre"] = padres
# contenido de dos fichas de muestra (IBEX y DAX) y de la página madre
def contenido(pid, nombre):
    try:
        r = requests.get(f"{W}/{pid}", params={"_fields": "id,slug,content,meta"}, headers=UA, timeout=60)
        (OUT / f"{nombre}.json").write_text(r.text, encoding="utf-8")
        return r.status_code
    except Exception as e:
        return str(e)[:150]
ibex = [p for p in paginas if p["parent"] == 8258]
res["ibex_fichas"] = len(ibex)
muestra = next((p for p in ibex if p["slug"] == "iberdrola"), ibex[0] if ibex else None)
if muestra:
    res["muestra_ibex"] = contenido(muestra["id"], "ficha_ibex")
res["madre_ibex"] = contenido(8258, "madre_ibex")
otros = sorted(((k, v) for k, v in padres.items() if k not in (0, 8258) and v >= 20), key=lambda x: -x[1])
res["otros_padres_grandes"] = otros
if otros:
    hijo = next(p for p in paginas if p["parent"] == otros[0][0])
    res["muestra_dax"] = contenido(hijo["id"], "ficha_dax")
    res["madre_dax"] = contenido(otros[0][0], "madre_dax")
# HTML público de la ficha de muestra (para ver qué lee un rastreador)
if muestra:
    try:
        r = requests.get(muestra["link"], headers=UA, timeout=60)
        (OUT / "ficha_ibex_publica.html").write_text(r.text, encoding="utf-8")
        res["html_publico"] = [r.status_code, len(r.text)]
    except Exception as e:
        res["html_publico"] = str(e)[:150]
# ---------------------------------------------------------------- BME: formas de pedir el histórico de precios
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)", "Referer": "https://www.bolsasymercados.es/", "Accept": "application/json, text/plain, */*"}
A = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
ISIN = "ES0144580Y14"  # Iberdrola
pruebas = {}
for nombre, ep, params in [
    ("hist_a", "HistoricalSharesPrices", {"isin": ISIN, "from": "20211001", "to": "20261020"}),
    ("hist_b", "HistoricalSharesPrices", {"isin": ISIN, "from": "2021-10-01", "to": "2026-10-20"}),
    ("hist_c", "HistoricalSharesPrices", {"isin": ISIN}),
    ("last", "LastHistoricalSharesPrices", {"isin": ISIN}),
    ("ficha", "ShareDetailsInfo", {"isin": ISIN}),
    ("listed_a", "ListedCompanies", {"tradingSystem": "SIBE"}),
    ("listed_b", "ListedCompanies", {}),
]:
    try:
        r = requests.get(A + ep, params=params, headers=H, timeout=90)
        try:
            j = r.json()
        except ValueError:
            j = r.text[:500]
        (OUT / f"bme_{nombre}.json").write_text(json.dumps(j, ensure_ascii=False)[:2_000_000], encoding="utf-8")
        if isinstance(j, dict):
            d = j.get("data") if isinstance(j.get("data"), list) else None
            pruebas[nombre] = {"status": r.status_code, "claves": list(j.keys())[:20], "n": len(d) if d is not None else None,
                               "primera": d[0] if d else None, "ultima": d[-1] if d else None}
        elif isinstance(j, list):
            pruebas[nombre] = {"status": r.status_code, "n": len(j), "primera": j[0] if j else None, "ultima": j[-1] if j else None}
        else:
            pruebas[nombre] = {"status": r.status_code, "texto": str(j)[:300]}
    except Exception as e:
        pruebas[nombre] = {"error": str(e)[:200]}
    time.sleep(0.5)
res["bme"] = pruebas
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("ok")
