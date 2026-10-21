"""Sonda temporal 41: estructura de los históricos de subastas del Tesoro (xlsx) y del calendario 2026 (pdf)."""
import json, re, ssl, socket, subprocess, tempfile, io
from pathlib import Path
import requests, certifi
import pandas as pd
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 (El Especulador, datos abiertos)"}
def bundle(host):
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, 443), timeout=30) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            der = ss.getpeercert(binary_form=True)
    t = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); t.write(ssl.DER_cert_to_PEM_cert(der)); t.close()
    txt = subprocess.run(["openssl", "x509", "-in", t.name, "-noout", "-text"], capture_output=True, text=True).stdout
    extra = ""
    for u in re.findall(r"CA Issuers - URI:(\S+)", txt):
        d = requests.get(u, timeout=30).content
        extra += d.decode() if b"BEGIN CERTIFICATE" in d else ssl.DER_cert_to_PEM_cert(d)
    b = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); b.write(open(certifi.where()).read() + "\n" + extra); b.close()
    return b.name
s = requests.Session(); s.headers.update(H); s.verify = bundle("www.tesoro.es")
BASE = "https://www.tesoro.es/documents/d/tesoro/"
res = {}
for nombre in ["historico_subastas-xlsx", "historico_t-marg-xlsx", "historico_t-int-medio-xlsx", "01-xlsx", "02-xlsx", "03-xlsx", "04-xlsx", "05-xlsx", "06-xlsx"]:
    try:
        r = s.get(BASE + nombre, timeout=90)
        info = {"http": r.status_code, "tipo": r.headers.get("content-type"), "len": len(r.content)}
        if r.status_code == 200:
            (OUT / (nombre + ".xlsx")).write_bytes(r.content)
            xl = pd.ExcelFile(io.BytesIO(r.content))
            info["hojas"] = {}
            for h in xl.sheet_names[:8]:
                df = xl.parse(h, header=None, nrows=40)
                info["hojas"][h] = {"forma": list(df.shape), "filas": df.fillna("").astype(str).values.tolist()[:40]}
        res[nombre] = info
    except Exception as e:  # noqa: BLE001
        res[nombre] = {"error": str(e)[:300]}
try:
    r = s.get(BASE + "calendario-tesoro-publico-2026-espanol-12-pdf", timeout=90)
    p = OUT / "calendario2026.pdf"; p.write_bytes(r.content)
    txt = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
    res["calendario2026"] = {"http": r.status_code, "len": len(r.content), "texto": txt[:8000]}
except Exception as e:  # noqa: BLE001
    res["calendario2026"] = {"error": str(e)[:300]}
(OUT / "tesoro_hist.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
