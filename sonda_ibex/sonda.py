"""Sonda temporal 63: scrip de Viscofan de noviembre-diciembre de 2026 (Viscofan, CNMV y BORME) para la pieza 8613."""
import json, re, html, subprocess, datetime
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (El Especulador, datos abiertos)"}
limpia = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
res = {}
def pdf_txt(url, clave):
    try:
        r = requests.get(url, headers=H, timeout=90)
        res[clave] = {"http": r.status_code, "ct": r.headers.get("content-type", "")}
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            p = OUT / (clave + ".pdf"); p.write_bytes(r.content)
            t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
            p.unlink()
            res[clave]["texto"] = t[:20000]
        else:
            res[clave]["texto"] = limpia(r.text)[:6000]
    except Exception as e:
        res[clave] = {"error": str(e)}
pdf_txt("https://public.viscofan.com/investor-relations/financialinformation/es/OIR%20Calendario%20estimado%202026%20Dic.pdf", "viscofan_calendario")
pdf_txt("https://public.viscofan.com/investor-relations/financialinformation/es/OIR%20Documento%20Informativo%202026.pdf", "viscofan_documento")
pdf_txt("https://www.cnmv.es/webservices/verdocumento/ver?t=%7Bdc88b4d3-cb82-441d-998c-fc8cfeb8ba85%7D", "cnmv_doc")
# BORME: sumarios del 12 al 23 de noviembre de 2026, anuncios de la sección C con VISCOFAN
borme = []
d = datetime.date(2026, 11, 12)
while d <= datetime.date(2026, 11, 23):
    u = f"https://www.boe.es/datosabiertos/api/borme/sumario/{d:%Y%m%d}"
    try:
        r = requests.get(u, headers={**H, "Accept": "application/xml"}, timeout=60)
        for m in re.finditer(r"<item>(.*?)</item>", r.text, re.S):
            it = m.group(1)
            if "VISCOFAN" in it.upper():
                ident = re.search(r"<identificador>(.*?)</identificador>", it)
                tit = re.search(r"<titulo>(.*?)</titulo>", it, re.S)
                borme.append({"fecha": str(d), "id": ident.group(1) if ident else None, "titulo": limpia(tit.group(1)) if tit else None})
    except Exception as e:
        borme.append({"fecha": str(d), "error": str(e)})
    d += datetime.timedelta(days=1)
res["borme"] = borme
for b in borme:
    if b.get("id"):
        r = requests.get("https://www.boe.es/diario_borme/txt.php?id=" + b["id"], headers=H, timeout=60)
        m = re.search(r'<div id="textoxslt".*?</div>\s*</div>', r.text, re.S)
        b["texto"] = limpia(m.group(0) if m else r.text)[:8000]
(OUT / "viscofan.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
