"""Sonda temporal 48 (Bonos y Obligaciones: resultados de las últimas subastas, valores en emisión, convocatoria, tenedores 05/06 y tipos 12). 47: estadísticas y fiscalidad. Antes 44 (textos de procedimiento y fiscalidad de las Letras). 40: aviso legal, históricos y calendario de tesoro.es. (39b (cadena de certificados incompleta en tesoro.es: se completa con el intermedio del AIA): subastas de Letras del Tesoro en tesoro.es (páginas y archivos descargables)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 (El Especulador, datos abiertos)",
     "Accept-Language": "es-ES,es;q=0.9"}
URLS = ["https://www.tesoro.es/deuda-publica/subastas/resultado-ultimas-subastas/bonos-del-estado",
        "https://www.tesoro.es/deuda-publica/subastas/resultado-ultimas-subastas/obligaciones-del-estado",
        "https://www.tesoro.es/deuda-publica/subastas/resultado-ultimas-subastas/bonos-y-obligaciones-indexados",
        "https://www.tesoro.es/deuda-publica/subastas/resultados-subastas-anteriores",
        "https://www.tesoro.es/bonos-y-obligaciones-del-estado1",
        "https://www.tesoro.es/deuda-publica/los-valores-del-tesoro/bonos-y-obligaciones-del-estado",
        "https://www.tesoro.es/deuda-publica/mercado/mercado-primario/procedimiento-de-emision-y-subasta-de-los-valores-del-tesoro/convocatoria-de-la-subasta",
        "https://www.tesoro.es/deuda-publica/mercado/mercado-primario/procedimiento-de-emision-y-subasta-de-los-valores-del-tesoro/presentacion"]
def limpiar(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
import ssl, socket, certifi, subprocess, tempfile, sys
def bundle_con_intermedio(host):
    """Descarga el certificado intermedio que anuncia el servidor (AIA) y lo añade al almacén de certifi.
    La verificación TLS sigue activa: solo se completa la cadena que el servidor no envía."""
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, 443), timeout=30) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            der = ss.getpeercert(binary_form=True)
    pem_hoja = ssl.DER_cert_to_PEM_cert(der)
    t = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); t.write(pem_hoja); t.close()
    txt = subprocess.run(["openssl", "x509", "-in", t.name, "-noout", "-text"], capture_output=True, text=True).stdout
    aia = re.findall(r"CA Issuers - URI:(\S+)", txt)
    extra = ""
    for u in aia:
        d = requests.get(u, timeout=30).content
        if b"BEGIN CERTIFICATE" in d:
            extra += d.decode()
        else:
            extra += ssl.DER_cert_to_PEM_cert(d)
    b = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    b.write(open(certifi.where()).read() + "\n" + extra); b.close()
    return b.name, aia
res = {}
s = requests.Session(); s.headers.update(H)
s.verify, aia = bundle_con_intermedio("www.tesoro.es")
import io
for u in URLS:
    try:
        r = s.get(u, timeout=90)
        t = r.text
        enl = []
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
            h = html.unescape(m.group(1)); tx = limpiar(m.group(2))
            if re.search(r"/documents/|\.(xlsx?|csv|pdf)|subasta|fiscal|tributac|bonos|obligac|emisi|circulac|ejemplo", h + tx, re.I):
                enl.append([tx[:100], h[:240]])
        main = re.search(r"<main.*?</main>", t, re.S)
        res[u] = {"http": r.status_code, "final": r.url, "len": len(t), "enlaces": enl[:200],
                  "texto": limpiar(re.sub(r"<script.*?</script>|<style.*?</style>", " ", (main.group(0) if main else t), flags=re.S))[:25000],
                  "tablas_html": [x[:25000] for x in re.findall(r"<table.*?</table>", t, re.S)[:4]]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
# documentos de estadísticas mensuales: 05 y 06 (tenedores de Bonos y Obligaciones), 12 (tipos marginales)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "pandas"], check=True)
import pandas as pd
docs = {}
for n in ("05", "06", "12"):
    url = "https://www.tesoro.es/documents/d/tesoro/%s-xlsx" % n
    try:
        c = s.get(url, timeout=90).content
        xl = pd.ExcelFile(io.BytesIO(c))
        docs[url] = {"hojas": {h: xl.parse(h, header=None).head(60).fillna("").astype(str).values.tolist() for h in xl.sheet_names[:3]}}
    except Exception as e:  # noqa: BLE001
        docs[url] = {"error": str(e)[:200]}
# valores en emisión: buscar el enlace en la página de subastas
try:
    t = s.get("https://www.tesoro.es/deuda-publica/subastas", timeout=90).text
    m = re.search(r'href="([^"]*valores-en-emisi[^"]*)"', t)
    if m:
        u = m.group(1) if m.group(1).startswith("http") else "https://www.tesoro.es" + m.group(1)
        r = s.get(u, timeout=90)
        res["valores_en_emision"] = {"url": u, "http": r.status_code, "tablas_html": [x[:30000] for x in re.findall(r"<table.*?</table>", r.text, re.S)[:4]],
                                     "texto": limpiar(re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S))[-6000:]}
except Exception as e:  # noqa: BLE001
    res["valores_en_emision"] = {"error": str(e)[:200]}
(OUT / "tesoro.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
(OUT / "documentos.json").write_text(json.dumps(docs, ensure_ascii=False, indent=1))
print("ok", len(docs))
