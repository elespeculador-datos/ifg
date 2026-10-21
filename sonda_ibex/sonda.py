"""Sonda temporal 44 (textos de procedimiento y fiscalidad de las Letras). 40: aviso legal, históricos y calendario de tesoro.es. (39b (cadena de certificados incompleta en tesoro.es: se completa con el intermedio del AIA): subastas de Letras del Tesoro en tesoro.es (páginas y archivos descargables)."""
import json, re, html
from pathlib import Path
import requests
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 (El Especulador, datos abiertos)",
     "Accept-Language": "es-ES,es;q=0.9"}
URLS = ["https://www.tesoro.es/deuda-publica/mercado/mercado-primario/procedimiento-de-emision-y-subasta-de-los-valores-del-tesoro/la-subasta",
        "https://www.tesoro.es/deuda-publica/mercado/mercado-primario/procedimiento-de-emision-y-subasta-de-los-valores-del-tesoro/presentacion-de-peticiones",
        "https://www.tesoro.es/deuda-publica/mercado/mercado-primario/procedimiento-de-emision-y-subasta-de-los-valores-del-tesoro/publicacion-de-resultados-de-la-subasta",
        "https://www.tesoro.es/deuda-publica/mercado/mercado-primario/instrumentos/letras-del-tesoro",
        "https://www.tesoro.es/deuda-publica/los-valores-del-tesoro/fiscalidad/residentes/impuesto-sobre-la-renta-de-las-personas-fisicas/tributacion-de-las-letras-del-tesoro"]
def limpiar(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
import ssl, socket, certifi, subprocess, tempfile
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
try:
    s.verify, aia = bundle_con_intermedio("www.tesoro.es")
    res["_aia"] = aia
except Exception as e:  # noqa: BLE001
    res["_aia_error"] = str(e)[:300]
for u in URLS:
    try:
        r = s.get(u, timeout=60)
        t = r.text
        enl = []
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
            h = html.unescape(m.group(1)); tx = limpiar(m.group(2))
            if re.search(r"/documents/|\.(xlsx?|csv|pdf)|reutiliz", h + tx, re.I):
                enl.append([tx[:80], h[:220]])
        main = re.search(r"<main.*?</main>", t, re.S)
        res[u] = {"http": r.status_code, "final": r.url, "len": len(t), "enlaces": enl[:80],
                  "texto": limpiar(re.sub(r"<script.*?</script>|<style.*?</style>", " ", (main.group(0) if main else t), flags=re.S))[:20000], "tablas": [limpiar(x)[:1500] for x in re.findall(r"<table.*?</table>", t, re.S)[:3]]}
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:300]}
(OUT / "tesoro.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok")
