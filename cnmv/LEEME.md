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

## En la web

La página del IBEX 35 (`/ibex-35/`, página de Elementor con el shortcode `espec_indice_bloques`) pinta los cuatro recuadros. El fragmento n.º 41 de Code Snippets («ESPEC: recuadros del IBEX 35 con comunicados de la CNMV»; copia en `cnmv/wordpress-snippet.php`) lee `cajas.html` de GitHub Pages, lo guarda en caché 20 minutos y sustituye con él el contenido de cada recuadro y su descripción. Si GitHub Pages no responde o el fichero no trae las marcas, no toca nada y los recuadros siguen como los deja el shortcode. Para volver a lo anterior basta con desactivar ese fragmento.

## Fichas de empresa

`docs/cnmv/empresas/<ficha>.html` trae, para cada empresa del IBEX 35, sus comunicados a la CNMV de los últimos doce meses (una línea por operación) y sus dividendos (el próximo anunciado, lo pagado en doce meses con su rentabilidad y los últimos pagos, con datos de BME del calendario de dividendos). Lo pinta en `/ibex35/<ficha>/` el fragmento «ESPEC: fichas del IBEX 35 con comunicados de la CNMV y dividendos» (copia en `cnmv/wordpress-fichas.php`), que además sustituye la lista fija de «Noticias relacionadas» por una automática. Mientras `ESPEC_FICHAS_CNMV_PUBLICO` sea `false`, solo lo ven los editores con sesión iniciada.
