"""Sonda temporal 43: prueba real del script de Letras del Tesoro."""
import subprocess, sys
from pathlib import Path
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "certifi"], check=False)
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
r = subprocess.run([sys.executable, "sonda_ibex/letras.py", "--salida", str(OUT / "letras")], capture_output=True, text=True)
(OUT / "registro.txt").write_text(f"codigo={r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr[-6000:]}\n", encoding="utf-8")
print(r.stdout[-3000:])
