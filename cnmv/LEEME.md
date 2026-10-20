# Comunicados a la CNMV del IBEX 35

Cada hora de los días hábiles (de 7:07 a 23:07, hora de Madrid en verano), el flujo `cnmv-horario` lee los dos canales RSS públicos de la CNMV, el de información privilegiada y el de otra información relevante. Cada canal solo muestra lo comunicado desde el cierre de la sesión anterior, así que el script acumula todo en `docs/cnmv/datos/comunicados.csv` y, a partir de ese histórico, publica:

- `cajas.html`: los cuatro recuadros de la página del IBEX 35 de elespeculador.com (resultados, dividendos, recompras, OPVs y ampliaciones), entre `<!-- cnmv:inicio … -->` y `<!-- cnmv:fin -->`. La web los lee de GitHub Pages y sustituye con ellos el contenido de los recuadros;
- `index.html`: página propia con los mismos datos de los últimos 60 días;
- `datos/ibex35.csv`: los comunicados del IBEX 35 con su tipo y su operación, y `datos/ultima.json`.

## Clasificación

Solo entran las empresas del IBEX 35 de `dividendos/ibex35.csv` (la misma composición que usa el calendario de dividendos), reconocidas por el nombre con que firman en la CNMV según `cnmv/empresas.csv`. **Tras cada revisión del IBEX hay que actualizar los dos ficheros y la fecha `IBEX35_VALIDA_HASTA` de `comunicados.py`**; si vence, el flujo se para en vez de publicar con una composición vieja.

El tipo sale de la categoría oficial de la CNMV y del texto del comunicado, con reglas fijas (`clasificar`):

- **Recompras**: programas de recompra y autocartera (no los contratos de liquidez).
- **Dividendos**: dividendos, pagos a cuenta, devoluciones de prima y dividendos flexibles (ampliaciones liberadas).
- **OPVs y ampliaciones**: ampliaciones de capital, OPV, salidas a bolsa y colocaciones de acciones (no las emisiones de deuda).
- **Resultados**: publicación de resultados y anuncios de la fecha en que se publicarán.

Lo demás (juntas, ratings, nombramientos…) se guarda en el histórico pero no sale en los recuadros.

## Duplicados

Dos comunicados distintos no se pisan nunca: cada uno tiene su número de registro en la CNMV. Lo que se agrupa es la **operación**: misma empresa, mismo tipo y, en resultados, mismo periodo. Así, los informes semanales de un programa de recompra, los dos comunicados de una misma ampliación o el anuncio de fecha y la publicación de unos resultados salen como una sola entrada, con el último comunicado y cuántos hay. Una ampliación y un dividendo de la misma empresa son dos entradas, cada una en su recuadro.

Prueba local: `python cnmv/comunicados.py --local IP.xml OIR.xml`.
