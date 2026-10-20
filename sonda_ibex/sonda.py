"""Sonda temporal 6: listas oficiales del Impuesto sobre Transacciones Financieras (AEAT) en texto."""
import json, subprocess
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0"}
base = "https://sede.agenciatributaria.gob.es/static_files/Sede/Tema/Declaraciones_informativas/I_Transacciones_Financieras/"
res = {}
for nombre in ["RELACION_SOCIEDADES_EJERCICIO_2026.pdf", "RELACION_SOCIEDADES_EJER_2025.pdf", "RELACION_SOCIEDADES_EJERCICIO_2025.pdf",
               "RELACION_SOCIEDADES_EJER_2024.pdf", "RELACION_SOCIEDADES_EJERCICIO_2024.pdf", "RELACION_SOCIEDADES_EJERCICIO_2027.pdf"]:
    try:
        r = requests.get(base + nombre, headers=H, timeout=60)
        res[nombre] = {"status": r.status_code, "bytes": len(r.content), "tipo": r.headers.get("content-type")}
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            p = OUT / nombre; p.write_bytes(r.content)
            subprocess.run(["pdftotext", "-layout", str(p), str(p.with_suffix(".txt"))], check=False)
    except Exception as e:
        res[nombre] = {"error": str(e)[:200]}
# página de la AEAT con el índice de documentos del ITF
for u in ["https://sede.agenciatributaria.gob.es/Sede/impuestos-tasas/impuesto-sobre-transacciones-financieras.html"]:
    try:
        r = requests.get(u, headers=H, timeout=60); res[u] = {"status": r.status_code}
        (OUT / "itf_indice.html").write_text(r.text, encoding="utf-8")
    except Exception as e:
        res[u] = {"error": str(e)[:200]}
(OUT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
