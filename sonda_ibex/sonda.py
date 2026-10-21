"""Sonda temporal 49: ejecución real de bonos/bonos.py contra tesoro.es y texto de la página de emisiones indexadas."""
import json, re, html, subprocess, sys
from pathlib import Path
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "certifi", "requests", "pandas"], check=True)
r = subprocess.run([sys.executable, "bonos/bonos.py", "--salida", str(OUT / "bonos")], capture_output=True, text=True)
(OUT / "ejecucion.txt").write_text(f"codigo={r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr[-6000:]}\n")
sys.path.insert(0, "bonos")
import bonos as B
s = B.sesion()
res = {}
for u in ["https://www.tesoro.es/deuda-publica/valores-del-tesoro/emisiones-indexadas"]:
    try:
        t = s.get(u, timeout=90).text
        res[u] = B._limpiar(re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))[-9000:]
    except Exception as e:  # noqa: BLE001
        res[u] = "ERROR " + str(e)[:200]
(OUT / "textos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok", r.returncode)
