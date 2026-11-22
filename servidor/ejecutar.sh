#!/usr/bin/env bash
# Ejecuta un colector en el servidor smpro-datos-1 con el código de main de GitHub.
#
#   servidor/ejecutar.sh <colector>      colector: cortos, cnmv, accionistas, letras, bonos, estres y los que sigan la convención
#
# Qué hace, en orden:
#   1. carga el entorno (/etc/smpro/entorno o $SMPRO_ENTORNO): ESPEC_DATOS_DIR, ESPEC_DATOS_BASE, GH_TOKEN
#      y, si el servidor usa un entorno virtual, SMPRO_PYTHON (el intérprete de ese entorno);
#   2. trae main de GitHub con avance rápido (si el servidor tuviera commits propios, avisa y sigue con lo que hay);
#   3. ejecuta el colector escribiendo en $ESPEC_DATOS_DIR/<colector>, fuera del git;
#   4. deja el estado de la pasada en $ESPEC_DATOS_DIR/estado/<colector>.json (público, para el Mapa de sistemas);
#   5. si falla, abre o comenta la incidencia <colector>-fallido en GitHub (servidor/avisar.sh); si va bien, la cierra.
# El registro de cada pasada queda en $ESPEC_DATOS_DIR/registro/<colector>-AAAA-MM-DD.log.
set -u
COLECTOR="${1:?Uso: servidor/ejecutar.sh <colector>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTORNO="${SMPRO_ENTORNO:-/etc/smpro/entorno}"
if [ -f "$ENTORNO" ]; then set -a; . "$ENTORNO"; set +a; fi
: "${ESPEC_DATOS_DIR:?Falta ESPEC_DATOS_DIR en $ENTORNO}"
: "${ESPEC_DATOS_BASE:?Falta ESPEC_DATOS_BASE en $ENTORNO}"
export ESPEC_DATOS_DIR ESPEC_DATOS_BASE
PYTHON="${SMPRO_PYTHON:-python3}"
mkdir -p "$ESPEC_DATOS_DIR/registro" "$ESPEC_DATOS_DIR/estado"
REGISTRO="$ESPEC_DATOS_DIR/registro/$COLECTOR-$(date -u +%F).log"
exec >>"$REGISTRO" 2>&1
echo "== $(date -u +'%F %T') UTC · $COLECTOR · inicio"
INICIO_ISO="$(date -u +'%FT%TZ')"

# Una pasada a la vez por colector (22/11/2026): si la anterior sigue en marcha (relleno de la CNMV, muchos PDF),
# esta se salta sin tocar nada. Dos pasadas a la vez leerían el mismo CSV y la última en escribir borraría lo
# que añadió la otra. Sin flock en el sistema, se sigue como antes.
if command -v flock >/dev/null 2>&1; then
  exec 9>"${TMPDIR:-/tmp}/smpro-$COLECTOR.lock"
  if ! flock -n 9; then
    echo "== $(date -u +'%F %T') UTC · $COLECTOR · la pasada anterior sigue en marcha: esta se salta"
    exit 0
  fi
fi

# estado <resultado> <codigo>: escribe $ESPEC_DATOS_DIR/estado/<colector>.json de forma atómica (sin rutas ni texto del registro).
estado() {
  local tmp="$ESPEC_DATOS_DIR/estado/.$COLECTOR.json.tmp"
  printf '{"colector":"%s","inicio":"%s","fin":"%s","resultado":"%s","codigo":%s,"commit":"%s"}\n' \
    "$COLECTOR" "$INICIO_ISO" "$(date -u +'%FT%TZ')" "$1" "$2" "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo desconocido)" >"$tmp" \
    && mv -f "$tmp" "$ESPEC_DATOS_DIR/estado/$COLECTOR.json"
}

cd "$REPO" || exit 2
if ! git pull --ff-only --quiet origin main; then
  echo "AVISO  git pull --ff-only ha fallado: el servidor no está en main limpio. Se ejecuta el código actual."
  "$REPO/servidor/avisar.sh" "$COLECTOR" abrir "git pull --ff-only ha fallado en el servidor: hay commits locales o conflicto. Código ejecutado: $(git rev-parse --short HEAD)." || true
fi
echo "código: $(git rev-parse --short HEAD) ($(git log -1 --format=%cd --date=short)) · intérprete: $PYTHON"

# Convención: el colector <nombre> vive en <nombre>/<nombre>.py y admite --salida (letras, bonos,
# estres y los que vengan). Las excepciones van explícitas.
case "$COLECTOR" in
  cortos)      ORDEN=("$PYTHON" cortos/rastreador.py) ;;
  cnmv)        ORDEN=("$PYTHON" cnmv/comunicados.py) ;;
  accionistas) ORDEN=("$PYTHON" accionistas/duenos.py --salida "$ESPEC_DATOS_DIR/accionistas") ;;
  opas|dividendos|ibex) echo "ERROR  $COLECTOR lee la API de BME sin licencia: no se ejecuta (P3 del catálogo)."; estado rechazado 3; exit 3 ;;
  *)
    if [ -f "$COLECTOR/$COLECTOR.py" ]; then
      ORDEN=("$PYTHON" "$COLECTOR/$COLECTOR.py" --salida "$ESPEC_DATOS_DIR/$COLECTOR")
    else
      echo "ERROR  colector desconocido: $COLECTOR (no existe $COLECTOR/$COLECTOR.py)"; estado desconocido 2; exit 2
    fi ;;
esac

if "${ORDEN[@]}"; then
  echo "== $(date -u +'%F %T') UTC · $COLECTOR · correcto"
  estado correcto 0
  "$REPO/servidor/avisar.sh" "$COLECTOR" cerrar "Pasada correcta el $(date -u +%F) a las $(date -u +%H:%M) UTC." || true
  exit 0
else
  CODIGO=$?
  echo "== $(date -u +'%F %T') UTC · $COLECTOR · FALLO (código $CODIGO)"
  estado fallo "$CODIGO"
  "$REPO/servidor/avisar.sh" "$COLECTOR" abrir "La pasada del $(date -u +%F) a las $(date -u +%H:%M) UTC ha fallado (código $CODIGO). Últimas líneas del registro $REGISTRO:
$(tail -n 15 "$REGISTRO" | sed 's/^/    /')" || true
  exit "$CODIGO"
fi
