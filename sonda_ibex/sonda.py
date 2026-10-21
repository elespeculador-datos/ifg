"""Sonda temporal 23: ranking de capitalización con datos reales de BME (no publica nada; solo deja el resultado en esta rama)."""
import subprocess, sys
from pathlib import Path
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    f.unlink()
r = subprocess.run([sys.executable, "capitalizacion/ranking.py", "--salida", str(OUT)], capture_output=True, text=True)
(OUT / "log.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr)
print(r.stdout, r.stderr)
