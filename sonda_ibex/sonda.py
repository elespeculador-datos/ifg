"""Sonda temporal 31: cómo publica la CNMV las participaciones significativas de un emisor (Iberdrola)."""
import json, re
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "Accept-Language": "es-ES,es;q=0.9"}
URLS = [
    "https://www.cnmv.es/Portal/Consultas/EE/ParticipacionesSignificativas.aspx?nif=A48010615",
    "https://www.cnmv.es/portal/Consultas/EE/ParticipacionesSignificativas.aspx?nif=A48010615&lang=es",
    "https://www.cnmv.es/Portal/Consultas/DatosEntidad.aspx?nif=A48010615",
    "https://www.cnmv.es/portal/Consultas/Busqueda.aspx?id=29&nif=A48010615",
    "https://www.cnmv.es/Portal/Consultas/EE/DerechosVoto.aspx?nif=A48010615",
]
res = {}
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=60)
        t = r.text
        tablas = re.findall(r"<table.*?</table>", t, re.S)
        res[u] = {"http": r.status_code, "final": r.url, "len": len(t), "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:150],
                  "n_tablas": len(tablas), "tabla0": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", tablas[0]))[:1500] if tablas else None,
                  "enlaces": sorted(set(re.findall(r'href="([^"]*(?:Participac|DerechosVoto|nif=)[^"]*)"', t)))[:30]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)}
(OUT / "cnmv_ps.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False)[:2500])
