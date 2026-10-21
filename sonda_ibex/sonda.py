"""Sonda temporal 50: páginas de tesoro.es sobre cómo comprar y vender Letras, Bonos y Obligaciones (particulares)."""
import json, re, subprocess, sys
from pathlib import Path
OUT = Path("sonda_ibex/resultado"); OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.rglob("*"):
    if f.is_file():
        f.unlink()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "certifi", "requests", "pandas"], check=True)
sys.path.insert(0, "bonos")
import bonos as B
s = B.sesion()
INICIO = ["https://www.tesoro.es/deuda-publica/subastas", "https://www.tesoro.es/tramites", "https://www.tesoro.es/deuda-publica/preguntas-frecuentes"]
PATRON = re.compile(r"compra|venta|cuenta|puntos-de-venta|comision|ejemplo|pregunta|reinversi|amortizaci|segunda-vuelta|pago-del-nominal|puesta-en-circulacion|ventaja|letras-del-tesoro|bonos-y-obligaciones-del-estado1|tramite|certificado|fondtesoro|calendario-de-dias", re.I)
EXCLUIR = re.compile(r"creadores-de-mercado|sociedades|no-residentes|patrimonio|ingles|/en/|/ca/|/gl/|/eu/|\.pdf|\.xlsx|segregables|strips|repo|blanqueo|sandbox|hipotec", re.I)
vistos, cola, res = set(), list(INICIO), {}
while cola and len(res) < 40:
    u = cola.pop(0)
    if u in vistos:
        continue
    vistos.add(u)
    try:
        r = s.get(u, timeout=90)
    except Exception as e:  # noqa: BLE001
        res[u] = {"error": str(e)[:200]}
        continue
    t = r.text
    cuerpo = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<header.*?</header>|<footer.*?</footer>", " ", t, flags=re.S)
    main = re.search(r'<div[^>]+class="[^"]*journal-content-article[^"]*".*', cuerpo, re.S)
    texto = B._limpiar(main.group(0) if main else cuerpo)
    i = texto.find("Suscríbete al boletín")
    texto = texto[i + 21:] if i >= 0 else texto
    j = texto.find("Enlaces legales")
    texto = texto[:j] if j > 0 else texto
    res[u] = {"http": r.status_code, "texto": texto[:15000],
              "documentos": sorted(set(re.findall(r'href="([^"]*/documents/[^"]*)"', t)))[:30]}
    for h in re.findall(r'href="([^"#?]+)"', t):
        h = h if h.startswith("http") else ("https://www.tesoro.es" + h if h.startswith("/") else "")
        if h.startswith("https://www.tesoro.es/") and PATRON.search(h) and not EXCLUIR.search(h) and h not in vistos and h not in cola:
            cola.append(h)
(OUT / "comprar.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok", len(res))
