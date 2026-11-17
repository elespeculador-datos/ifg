#!/bin/bash
# Ejecucion diaria del IFG en smpro-datos-1 (sustituye al flujo de GitHub Actions)
# Publica en datos.elespeculador.com solo la lista blanca, y solo si la estabilidad se verifica.
cd /home/smpro/ifg || exit 1
source /home/smpro/venv/bin/activate
LOG=/home/smpro/logs/ifg-$(date +%F).log
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
git add -A docs datos
git commit -qm "IFG $(date +%F)" || echo 'sin cambios'
echo FIN $(date)
} >> "$LOG" 2>&1
