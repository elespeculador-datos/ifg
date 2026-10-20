# Calendario de dividendos

Cada día hábil, a las 17:10 UTC, el flujo `dividendos-diario` descarga de la API pública de BME los dividendos del mercado continuo (la API da el último año y los ya anunciados) y publica en `docs/dividendos/`:

- `index.html`: los próximos dividendos con fecha ex, importe bruto, tipo y fecha de pago, y lo repartido por cada empresa en los últimos doce meses;
- `datos/*.csv` y `ultima.json`: los mismos datos en abierto, con licencia CC BY 4.0;
- `fragmento-wp.html`: las tablas entre `<!-- dividendos:inicio … -->` y `<!-- dividendos:fin -->`, que un escenario de Make copia en la página «Calendario de dividendos» de elespeculador.com.

Como BME solo guarda un año, el script va acumulando el histórico en `docs/dividendos/datos/dividendos.csv`.

Es independiente del IFG, de los cortos y del IBEX: solo lee y escribe `dividendos/` y `docs/dividendos/`. Si BME no responde o cambia el formato, el flujo abre una incidencia con la etiqueta `dividendos-fallido`.

Prueba local: `python dividendos/calendario.py --local respuesta_bme.json`.
