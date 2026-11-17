#!/bin/bash
# Ejecucion diaria del IFG en smpro-datos-1 (sustituye al flujo de GitHub Actions)
# Publica en datos.elespeculador.com solo la lista blanca, y solo si la estabilidad se verifica.
# Sin commits en el git del servidor (DESPLIEGUE.md): el checkout se queda en main. Los datos del dia
# se guardan en una copia comprimida en /home/smpro/respaldo/ifg-datos/ (ocupan menos de 1 MB).
cd /home/smpro/ifg || exit 1
source /home/smpro/venv/bin/activate
LOG=/home/smpro/logs/ifg-$(date +%F).log
COPIAS=/home/smpro/respaldo/ifg-datos
{
date
python backfill_gdelt.py --cada 7 --incremental
python esperar_datos.py
if python publicar_diario.py && python verificar_estabilidad.py; then
  for f in ifg.json ifg_serie_12m.json; do cp docs/$f /var/www/datos/ifg/$f.tmp && mv /var/www/datos/ifg/$f.tmp /var/www/datos/ifg/$f; done
  echo PUBLICADO-EN-DATOS
else
  echo FALLO-NO-SE-PUBLICA
fi
mkdir -p "$COPIAS"
if tar czf "$COPIAS/ifg-datos-$(date +%F).tgz" docs/*.json docs/*.csv docs/historico datos; then
  echo "COPIA-DATOS $COPIAS/ifg-datos-$(date +%F).tgz"
else
  echo "AVISO copia de datos fallida"
fi
echo FIN $(date)
} >> "$LOG" 2>&1
