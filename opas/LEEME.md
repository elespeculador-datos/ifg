# Registro de OPAs

Cada día hábil, a las 17:25 UTC, el flujo `opas-diario` descarga de la API pública de BME (`CorporateActions/TakeoverBids`) todas las ofertas públicas de adquisición sobre sociedades que cotizan en sus mercados desde 2000 (mercado continuo, corros, BME Growth y Latibex) y, **solo si el registro ha cambiado**, publica en `docs/opas/`:

- `index.html`: OPAs por año y tabla detallada desde 2015 (sociedad, oferente, precio o canje, plazo de aceptación, aceptación y resultado);
- `datos/opas.csv` (todas desde 2000), `datos/por_anio.csv` y `ultima.json`, con licencia CC BY 4.0;
- `fragmento-wp.html`: las tablas entre `<!-- opas:inicio … -->` y `<!-- opas:fin -->`, que un escenario de Make copia en la página «OPAs en la bolsa española» de elespeculador.com.

Notas sobre los datos:

- La aceptación es `acciones adquiridas / acciones a las que se dirige la oferta`. En las OPAs negativas BME anota 0 acciones adquiridas, así que no se calcula. Por encima del 100 % es una oferta parcial sobresuscrita, con prorrateo.
- BME corta los nombres de los oferentes a 35 caracteres: los que salen en la tabla se completan en `OFERENTES` (`opas.py`). Cuando el oferente coincide con la sociedad se muestra «La propia sociedad» (recompras y exclusiones).
- Las contraprestaciones en acciones se copian tal como las anota BME, entre comillas; la relación exacta está en el folleto de la CNMV.

Es independiente del IFG, de los cortos, del IBEX y de los dividendos. Si BME no responde o cambia el formato, el flujo abre una incidencia con la etiqueta `opas-fallido`.

Prueba local: `python opas/opas.py --local respuesta_bme.json`.
