#!/bin/bash
# Ejecucion diaria del IFG en smpro-datos-1 (sustituye al flujo de GitHub Actions)
# Publica en datos.elespeculador.com solo la lista blanca, y solo si la estabilidad se verifica.
# Desde el 25/11/2026 (Oscilador Geopolitico 0.10.1): despues de publicar /ifg/, oscilador.py
# escribe la misma serie con el nombre y los tramos nuevos y se publica en /oscilador-geo/.
# Si el Oscilador falla, /ifg/ ya esta publicado y no se toca (FALLO-OSCILADOR en el log).
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
  if python oscilador.py; then
    ok=1
    for f in oscilador-geo_serie_12m.json oscilador-geo.json; do
      cp docs/oscilador-geo/$f /var/www/datos/oscilador-geo/$f.tmp && mv /var/www/datos/oscilador-geo/$f.tmp /var/www/datos/oscilador-geo/$f || ok=0
    done
    if [ "$ok" = 1 ]; then echo PUBLICADO-OSCILADOR; else echo FALLO-OSCILADOR-COPIA; fi
  else
    echo FALLO-OSCILADOR
  fi
else
  echo FALLO-NO-SE-PUBLICA
fi
git add -A docs datos
git commit -qm "IFG $(date +%F)" || echo 'sin cambios'
echo FIN $(date)
} >> "$LOG" 2>&1
