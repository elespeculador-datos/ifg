#!/usr/bin/env bash
#
# Genera el PDF de la metodología a partir de METODOLOGIA.md.
#
# POR QUÉ ESTO ES UN SCRIPT Y NO UN PDF SUBIDO A MANO. El documento de
# metodología es citable: tiene que poder regenerarse desde su fuente, y la
# fuente tiene que ser el Markdown versionado en el repositorio, no un binario
# que nadie puede auditar ni diferenciar. Si el PDF y el Markdown llegaran a
# separarse, el Markdown manda.
#
# POR QUÉ NO SE USA LaTeX. Sería la opción tipográfica natural, pero la
# instalación disponible está incompleta (falta lmodern.sty) y no hay forma de
# completarla sin red hacia CTAN. La ruta pandoc -> HTML -> wkhtmltopdf da un
# resultado perfectamente presentable y, de paso, deja el control de la
# tipografía en una hoja de estilo que se puede leer y versionar.
#
# Requiere pandoc y wkhtmltopdf.
#
# Uso:
#   ./construir_metodologia_pdf.sh
#   ./construir_metodologia_pdf.sh docs/metodologia-ifg-0.10.0.pdf

set -euo pipefail

FUENTE="METODOLOGIA.md"
CSS="recursos/metodologia.css"
VERSION=$(python3 -c "import config; print(config.VERSION)")
SALIDA="${1:-docs/metodologia-ifg-${VERSION}.pdf}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

for f in "$FUENTE" "$CSS"; do
  [ -f "$f" ] || { echo "No encuentro $f. Ejecuta esto desde la raíz del repositorio." >&2; exit 1; }
done
command -v pandoc      >/dev/null || { echo "Falta pandoc." >&2; exit 1; }
command -v wkhtmltopdf >/dev/null || { echo "Falta wkhtmltopdf." >&2; exit 1; }

mkdir -p "$(dirname "$SALIDA")"

# El Markdown empieza con su propio H1 y dos líneas de cabecera. En el PDF esa
# cabecera se sustituye por una portada con formato, así que se recorta de la
# fuente y se inyecta aparte. Así el .md sigue legible en GitHub por su cuenta
# y el PDF no repite el título dos veces.
python3 - "$FUENTE" "$TMP/cuerpo.md" <<'PY'
import sys
origen, destino = sys.argv[1], sys.argv[2]
lineas = open(origen, encoding="utf-8").read().split("\n")
# Se descartan las líneas hasta la primera regla horizontal, que es donde
# acaba el bloque de título del documento.
for i, l in enumerate(lineas):
    if l.strip() == "---" and i > 0:
        lineas = lineas[i + 1:]
        break
open(destino, "w", encoding="utf-8").write("\n".join(lineas).lstrip("\n"))
PY

# El aviso del estado del índice va en la portada: es lo primero que un lector
# tiene que ver, no algo que se encuentre en la página cuatro.
ESTADO=$(python3 - "$FUENTE" <<'PY'
import re, sys
txt = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"^> \*\*(Estado del índice[^*]*)\*\*", txt, re.M)
print(m.group(1).strip() if m else "")
PY
)

pandoc "$TMP/cuerpo.md" \
  --from=markdown \
  --to=html5 \
  --standalone \
  --toc --toc-depth=2 \
  --metadata title="IFG" \
  -o "$TMP/cuerpo.html"

# Portada propia y hoja de estilo INCRUSTADA, no enlazada: wkhtmltopdf
# resuelve las rutas relativas respecto al HTML, que vive en un directorio
# temporal, así que un <link href="../recursos/..."> no encuentra nada y el
# PDF sale sin estilo ninguno. Pasó en el primer intento.
python3 - "$TMP/cuerpo.html" "$VERSION" "$ESTADO" "$CSS" <<'PY'
import sys, datetime
ruta, version, estado, css = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
html = open(ruta, encoding="utf-8").read()
hoja = open(css, encoding="utf-8").read()
html = html.replace("</head>", f"<style>\n{hoja}\n</style>\n</head>", 1)
hoy = datetime.date.today().strftime("%d/%m/%Y")
portada = f"""<div class="portada">
  <div class="marca">el especulador.com &nbsp;·&nbsp; Documento de metodología</div>
  <h1>Índice de Fricción Global</h1>
  <p class="sub">Versión {version} &nbsp;·&nbsp; {hoy}</p>
</div>
<blockquote><p><strong>{estado}</strong></p></blockquote>
"""
html = html.replace("<body>", "<body>\n" + portada, 1)
open(ruta, "w", encoding="utf-8").write(html)
PY

# Sin pies de página ni objeto "toc": este wkhtmltopdf viene sin parchear y
# los ignora. El índice se genera con pandoc dentro del propio HTML, que
# además es más fiable y se puede dar estilo desde la hoja CSS.
wkhtmltopdf \
  --quiet \
  --enable-local-file-access \
  --page-size A4 \
  --margin-top 20mm --margin-bottom 18mm \
  --margin-left 20mm --margin-right 20mm \
  "$TMP/cuerpo.html" "$SALIDA"

echo "PDF generado: $SALIDA"
python3 -c "
from pypdf import PdfReader
r = PdfReader('$SALIDA')
print(f'  paginas: {len(r.pages)}')
" 2>/dev/null || true
ls -la "$SALIDA"
