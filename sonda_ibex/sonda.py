"""Sonda temporal 26: ranking de capitalización revisado, con datos reales de BME (no publica nada)."""
import subprocess, sys
from pathlib import Path
OUT = Path("sonda_ibex/resultado")
if OUT.exists():
    subprocess.run(["rm", "-rf", str(OUT)])
OUT.mkdir(parents=True)
r = subprocess.run([sys.executable, "capitalizacion/ranking.py", "--salida", str(OUT)], capture_output=True, text=True)
(OUT / "log.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr + f"\nexit {r.returncode}")
print(r.stdout, r.stderr)
