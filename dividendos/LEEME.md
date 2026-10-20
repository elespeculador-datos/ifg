# Calendario de dividendos (pendiente de decisión: gratis o Premium)

Rama sin fusionar. Cada día hábil, `dividendos/calendario.py` descargaría de la API pública de BME los dividendos del mercado continuo (la API da el último año y los ya anunciados) y publicaría en `docs/dividendos/` los próximos dividendos con fecha ex, importe bruto, tipo y fecha de pago, y lo repartido por cada empresa en los últimos doce meses, en página, CSV y JSON, además del fragmento para WordPress entre `<!-- dividendos:inicio … -->` y `<!-- dividendos:fin -->`.

Como BME solo guarda un año, el script va acumulando el histórico en `docs/dividendos/datos/dividendos.csv`.

Prueba local: `python dividendos/calendario.py --local respuesta_bme.json`.
