#!/usr/bin/env bash
# Abre, comenta o cierra la incidencia <colector>-fallido en GitHub desde el servidor (regla 10 del catálogo:
# cada fallo abre una incidencia; el silencio no es un estado válido). Sustituye a lo que hacían las Actions.
#
#   servidor/avisar.sh <colector> abrir  "<texto>"   abre la incidencia o comenta la que ya esté abierta
#   servidor/avisar.sh <colector> cerrar "<texto>"   comenta y cierra la incidencia abierta, si la hay
#
# Necesita GH_TOKEN (token de GitHub con permiso de incidencias sobre el repositorio) en el entorno.
# Sin token, escribe el aviso en la salida estándar y termina sin error: el registro de la pasada lo conserva.
set -u
COLECTOR="${1:?}"; ACCION="${2:?abrir|cerrar}"; TEXTO="${3:-}"
REPO_GH="${ESPEC_REPO_GH:-elespeculador-datos/ifg}"
ETIQUETA="$COLECTOR-fallido"
API="https://api.github.com/repos/$REPO_GH"
if [ -z "${GH_TOKEN:-}" ]; then
  echo "AVISO  sin GH_TOKEN: no se puede $ACCION la incidencia $ETIQUETA. Texto: $TEXTO"
  exit 0
fi
# -f: un error HTTP (403, 404, 422) hace fallar a curl; sin él, un token sin permiso parecería un éxito.
gh_api() { curl -sS -f --max-time 30 -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" "$@"; }
json_texto() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
ABIERTA="$(gh_api "$API/issues?state=open&labels=$ETIQUETA&per_page=1" | python3 -c 'import json,sys
d=json.load(sys.stdin); print(d[0]["number"] if isinstance(d,list) and d else "")' 2>/dev/null || true)"
case "$ACCION" in
  abrir)
    if [ -n "$ABIERTA" ]; then
      gh_api -X POST "$API/issues/$ABIERTA/comments" -d "{\"body\": $(json_texto "$TEXTO")}" >/dev/null && echo "incidencia #$ABIERTA comentada" || echo "AVISO  no se pudo comentar la incidencia #$ABIERTA (¿token sin permiso?)"
    else
      gh_api -X POST "$API/labels" -d "{\"name\": \"$ETIQUETA\", \"color\": \"b60205\", \"description\": \"El colector $COLECTOR ha fallado en el servidor\"}" >/dev/null 2>&1 || true
      TITULO="El colector $COLECTOR ha fallado en el servidor el $(date -u +%F)"
      gh_api -X POST "$API/issues" -d "{\"title\": $(json_texto "$TITULO"), \"body\": $(json_texto "$TEXTO"), \"labels\": [\"$ETIQUETA\"]}" \
        | python3 -c 'import json,sys; print("incidencia abierta #%s" % json.load(sys.stdin).get("number","?"))'
    fi ;;
  cerrar)
    if [ -n "$ABIERTA" ]; then
      gh_api -X POST "$API/issues/$ABIERTA/comments" -d "{\"body\": $(json_texto "$TEXTO Se cierra.")}" >/dev/null
      gh_api -X PATCH "$API/issues/$ABIERTA" -d '{"state": "closed"}' >/dev/null && echo "incidencia #$ABIERTA cerrada" || echo "AVISO  no se pudo cerrar la incidencia #$ABIERTA (¿token sin permiso?)"
    fi ;;
  *) echo "acción desconocida: $ACCION"; exit 2 ;;
esac
