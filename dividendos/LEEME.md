# Calendario de dividendos

Cada día hábil, a las 17:10 UTC, el flujo `dividendos-diario` descarga de la API pública de BME los dividendos del mercado continuo (la API da el último año y los ya anunciados) y publica en `docs/dividendos/`:

- `index.html`: los próximos dividendos con fecha ex, importe bruto, tipo y fecha de pago, lo repartido por cada empresa en los últimos doce meses y la rentabilidad por dividendo sobre el último cierre (las 15 mayores y las diez mayores del IBEX 35);
- `datos/*.csv` y `ultima.json`: los mismos datos en abierto, con licencia CC BY 4.0;
- `fragmento-wp.html`: las tablas entre `<!-- dividendos:inicio … -->` y `<!-- dividendos:fin -->`, que un escenario de Make copia en la página «Calendario de dividendos» de elespeculador.com.

Como BME solo guarda un año, el script va acumulando el histórico en `docs/dividendos/datos/dividendos.csv`.

Es independiente del IFG, de los cortos y del IBEX: solo lee y escribe `dividendos/` y `docs/dividendos/`. Si BME no responde o cambia el formato, el flujo abre una incidencia con la etiqueta `dividendos-fallido`.

Prueba local: `python dividendos/calendario.py --local respuesta_bme.json`.

## Rentabilidad por dividendo

- Es lo pagado por acción con fecha ex en los últimos doce meses dividido entre el último cierre de la ficha de BME (`ShareDetailsInfo`). La «ordinaria», que ordena las tablas, no cuenta los dividendos extraordinarios; los flexibles cuentan por el importe para quien elige efectivo.
- Solo se calcula si el cierre es de los últimos diez días y en la misma moneda que el dividendo (las acciones que pagan en dos monedas se quedan sin dato). Si las fichas de BME no responden, el calendario se publica igual, sin la rentabilidad.
- La tabla del IBEX 35 usa `dividendos/ibex35.csv`. **Hay que actualizarlo tras cada revisión del Comité Asesor Técnico** y mover la fecha `IBEX35_VALIDA_HASTA` de `calendario.py`; pasada esa fecha, la tabla del IBEX deja de publicarse (nunca sale con una composición vieja).

