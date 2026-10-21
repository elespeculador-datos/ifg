"""Sonda temporal 51: preguntas frecuentes completas de tesoro.es y páginas de la sede (tesoropublico.gob.es) sobre compra y venta de valores."""
import json, re, subprocess, sys
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "certifi", "requests", "pandas"], check=True)
sys.path.insert(0, "bonos")
import bonos as B
res = {}
def texto(t):
    cuerpo = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<header.*?</header>|<footer.*?</footer>", " ", t, flags=re.S)
    x = B._limpiar(cuerpo)
    i = x.find("Suscríbete al boletín")
    x = x[i + 21:] if i >= 0 else x
    j = x.find("Enlaces legales")
    return x[:j] if j > 0 else x
s = B.sesion()
for u in ["https://www.tesoro.es/deuda-publica/preguntas-frecuentes"]:
    try:
        r = s.get(u, timeout=120); res[u] = {"http": r.status_code, "texto": texto(r.text)}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
s2 = requests.Session(); s2.headers.update(B.CAB)
try:
    s2.verify = B._almacen_con_intermedio("www.tesoropublico.gob.es")
except Exception as e:  # noqa: BLE001
    res["_aia_sede"] = str(e)[:300]
for u in ["https://www.tesoropublico.gob.es/w/servicios/compra-y-venta-de-valores",
          "https://www.tesoropublico.gob.es/"]:
    try:
        r = s2.get(u, timeout=120); res[u] = {"http": r.status_code, "final": r.url, "texto": texto(r.text)[:20000],
                                             "enlaces": sorted(set(re.findall(r'href="([^"]*(?:compra|venta|valores|cuenta|suscrip|reinver)[^"]*)"', r.text, re.I)))[:60]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
(OUT / "comprar2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
