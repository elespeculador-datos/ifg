# Comunicados a la CNMV del IBEX 35

Cada hora (en el servidor smpro-datos-1, de 06:07 a 23:07 todos los días; ver `DESPLIEGUE.md`), el colector lee los dos canales RSS públicos de la CNMV, el de información privilegiada y el de otra información relevante, y pide una a una las fichas de los números de registro que falten (ver «Relleno por número de registro»). Cada canal solo muestra lo comunicado desde el cierre de la sesión anterior, así que el script acumula todo en `<salida>/cnmv/datos/comunicados.csv` y, a partir de ese histórico, publica:

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
- **OPAs**: ofertas públicas de adquisición que reciben o lanzan, incluidas las de exclusión (no las ofertas sobre bonos u otra deuda). Se publican en `listado-opas.html`, en las fichas y en `index.html`, pero **no se enlazan desde la web** mientras `opas` no esté en `EN_WEB`: hace falta antes el recuadro `opas_panel` en `/ibex-35/`, la página `/ibex-35/opas/` y añadir `opas` a los tipos del fragmento 42.

Lo demás (juntas, ratings, nombramientos…) se guarda en el histórico pero no sale en los recuadros.

## Duplicados

Dos comunicados distintos no se pisan nunca: cada uno tiene su número de registro en la CNMV. Lo que se agrupa es la **operación**: misma empresa, mismo tipo y, en resultados, mismo periodo. Así, los informes semanales de un programa de recompra, los dos comunicados de una misma ampliación o el anuncio de fecha y la publicación de unos resultados salen como una sola entrada, con el último comunicado y cuántos hay; en los listados y en las fichas, la entrada enlaza además cada comunicado por su número de registro, para que ningún hecho quede sin enlace. Una ampliación y un dividendo de la misma empresa son dos entradas, cada una en su recuadro.

Prueba local: `python cnmv/comunicados.py --local IP.xml OIR.xml`.

## En la web

La página del IBEX 35 (`/ibex-35/`, página de Elementor con el shortcode `espec_indice_bloques`) pinta los cuatro recuadros. El fragmento n.º 41 de Code Snippets («ESPEC: recuadros del IBEX 35 con comunicados de la CNMV»; copia en `cnmv/wordpress-snippet.php`) lee `cajas.html` de GitHub Pages, lo guarda en caché 20 minutos y sustituye con él el contenido de cada recuadro y su descripción. Si GitHub Pages no responde o el fichero no trae las marcas, no toca nada y los recuadros siguen como los deja el shortcode. Para volver a lo anterior basta con desactivar ese fragmento. Si `cajas.html` trae un recuadro que la página no tiene (hoy solo `opas`), el fragmento lo crea copiando el de «OPVs y ampliaciones» con su propio botón de abrir y cerrar; si no encuentra ese recuadro, no hace nada.

## Fichas de empresa

`<salida>/cnmv/empresas/<ficha>.html` trae, para cada empresa del IBEX 35, sus comunicados a la CNMV de los últimos doce meses (una línea por operación; los anuncios de dividendo, también). **Sin datos de BME** desde el 21/11/2026: el colector ya no lee el calendario de dividendos de BME ni publica importes, rentabilidades ni precios (antes lo hacía si encontraba `docs/dividendos/datos/`; esos ficheros se retiraron del repositorio el 16/11 y el código que los leía se ha quitado para que no puedan volver). Los importes y fechas de cada dividendo saldrán de los propios comunicados de la CNMV (`cnmv/dividendos_cnmv.py`, prototipo). Lo pinta en `/ibex35/<ficha>/` el fragmento n.º 50 de Code Snippets «ESPEC: fichas del IBEX 35 con comunicados de la CNMV y dividendos (vista previa)» (copia en `cnmv/wordpress-fichas.php`), que además sustituye la lista fija de «Noticias relacionadas» por una automática. Desde el 31/10/2026 `ESPEC_FICHAS_CNMV_PUBLICO` es `true`: lo ve cualquier lector. Para volver a la vista previa, ponerlo a `false`.

## Relleno por número de registro (21/11/2026)

El RSS de la CNMV no deja recuperar lo pasado: lo que se publica mientras el colector no corre se pierde. Pasó del 07/11 al 15/11/2026 (los flujos de GitHub se pararon el 07/11 y el servidor arrancó el 16/11): faltaban 118 números de otra información relevante y 12 de información privilegiada, 13 de ellos de empresas del IBEX 35. El RSS tampoco trae los comunicados de los fondos de titulización.

Desde el 21/11, cada pasada busca los números de registro que faltan en cada canal entre el primer comunicado de los últimos 45 días (`DIAS_HUECOS`) y el último conocido, y pide su ficha pública (`https://www.cnmv.es/portal/Otra-Informacion-Relevante/Resultado-OIR?nreg=N` y `…/Informacion-Privilegiada/Resultado-IP?nreg=N`), de los más recientes a los más antiguos, hasta 200 por pasada (`MAX_RELLENO`) y con medio segundo entre una y otra. De la ficha salen los mismos campos que da el RSS (emisor, categoría, texto y enlace iguales; la hora, sin segundos). Es lo mismo que ya hacía el colector de WordPress (fragmento 64).

- Un número que la CNMV no enseña («No se han encontrado datos disponibles») se anota en `datos/numeros_sin_registro.csv` y se vuelve a preguntar una sola vez, otro día.
- Un fallo de red o de la CNMV no anota nada: el número se pide en la pasada siguiente; con cinco fallos seguidos, el relleno se deja para la pasada siguiente.
- Si las fichas dejan de tener la forma conocida (la mitad o más de las leídas, y al menos tres), el colector publica lo que tiene y sale con error, para que `servidor/ejecutar.sh` abra la incidencia `cnmv-fallido`.
- `datos/ultima.json` lleva `huecos_pendientes` por canal.
- `--sin-relleno` lo desactiva; `--relleno-max N` cambia el límite. Con `--local` no se rellena.

Prueba con la CNMV real (21/11/2026, desde el entorno de Datos, sobre una copia del histórico del servidor): 203 números pedidos, 203 comunicados recuperados, ningún hueco pendiente, 3 min 22 s; la segunda pasada no pide nada.

## Paridad con el colector de WordPress (21/11/2026)

Comparadas una a una las 35 fichas de la web (fragmento 50 con los datos del fragmento 64, 21/11 a las 00:46) con las del servidor (20/11 a las 20:07): 22 iguales y 13 con 17 comunicados de menos en el servidor. 13 eran del hueco del 07/11 al 13/11 y 4 estaban en el histórico pero sin clasificar: la regla de resultados no reconocía «nueve primeros meses» (Aena 43360, Cellnex 3408 y 3409, Ferrovial 3372). Con el relleno y la regla corregida (también «seis/tres primeros meses» y «primeros nueve/seis/tres meses», con su periodo), las 35 fichas tienen los mismos comunicados y las mismas etiquetas que la web.

Pruebas: `python cnmv/pruebas_cnmv.py` (68 comprobaciones sin red desde el 22/11; 40 en esta entrega, con fichas reales de la CNMV en `pruebas_cnmv/`, el histórico y la clasificación del servidor del 21/11 y la instantánea de las 35 fichas de la web): lectura de fichas y de números inexistentes, huecos, reintentos y límites del relleno, regla de resultados (con el histórico real solo cambian esas cuatro clasificaciones del IBEX 35), paridad de las 35 fichas y ausencia de BME. Seis mutaciones del código hacen fallar alguna.

Antes de pasar los fragmentos 41, 42 y 50 al servidor: cinco días hábiles de comparación diaria de las 35 fichas (Datos) y permiso de Federico; ese día, Tecnología revisa las fichas y desactiva el fragmento 64.

## Relleno hacia atrás: doce meses de histórico (22/11/2026)

Las fichas de empresa (contrato 1.0 con Tecnología) muestran el registro oficial de doce meses, pero el histórico del colector empezaba el 19/10/2026 (primera pasada de GitHub). Desde el 22/11, cada pasada completa también el histórico **hacia atrás**, número a número, desde el primer número conocido de cada canal hasta el primer comunicado anterior a hoy − 400 días (`DIAS_HISTORICO`): primero IP (unos 500 números al año) y luego OIR (unos 6.500), hasta 300 fichas por pasada (`MAX_ATRAS`, `--atras-max N`; 0 lo desactiva). En el servidor, con una pasada por hora, el año entero tarda un día y medio. Si una ficha falla (red, CNMV), ese canal se para y la pasada siguiente sigue por el mismo número: no deja huecos. Los números que la CNMV no enseña se anotan en `numeros_sin_registro.csv` y no se repiten. Si cambia la forma de las fichas, publica lo que tiene y sale con error (incidencia). `datos/ultima.json` lleva `historico`: por canal, desde qué fecha hay datos y si ya cubre los 400 días.

## Dividendos leídos de los comunicados (22/11/2026)

`cnmv/dividendos_cnmv.py` (el prototipo del IFG del 17/11, puesto en producción) lee el importe bruto por acción, su moneda y las fechas ex, de registro y de pago de cada comunicado de dividendo del IBEX 35 (caja «dividendos» de `datos/ibex35.csv`): abre su ficha en la CNMV, descarga el PDF, lo pasa a texto con `pdftotext` y busca con patrones estrictos sobre el texto compacto, con el título del registro delante (a veces el importe solo está en el título, como en IAG). `comunicados.py` lo llama al final de cada pasada, hasta 20 comunicados nuevos (`--dividendos-max N`; 0 lo desactiva), y si falla publica igual y sale con error.

- Salida: `datos/dividendos.csv` (`canal`, `nreg`, `fecha_comunicado`, `isin`, `empresa`, `tipo`, `importe_bruto`, `moneda`, `fecha_ex`, `fecha_registro`, `fecha_pago`, `extraccion`, `intentos`, `enlace`). La lee la ficha integrada (`empresas/`).
- `extraccion`: `completa` (importe con moneda, fecha ex y fecha de pago), `parcial` (solo lo que se lee con seguridad), `flexible: ver comunicado` (dividendo flexible: el efectivo depende de la opción del accionista; no se descarga), `sin documento` (se vuelve a pedir hasta tres veces) o `sin datos`.
- Reglas: un importe sin moneda escrita junto a la cifra no se publica (los de ArcelorMittal van en dólares); fechas fuera de [fecha del comunicado, 31/12 del año siguiente] o con la ex posterior al pago se descartan; nada se completa a mano.
- Caché de PDF y textos en `$ESPEC_CACHE_DIR/cnmv/` (por defecto `cache/cnmv/` del repositorio, ignorado por git y fuera de lo que sirve el servidor).
- Comprobado a mano el 22/11/2026 con los doce comunicados de dividendo del histórico del servidor: los ocho que se leen coinciden con el PDF (Mapfre 0,080 €, Redeia 0,2040 €, Unicaja 6,42 céntimos, CaixaBank 0,1844 €, IAG 0,053 €, Enagás 0,4 €, con sus fechas; Repsol 0,56 € y Grifols 0,15 € parciales porque no dicen la fecha ex con su etiqueta); los tres flexibles (Iberdrola y Ferrovial) no se leen. Esos ocho textos reales están en `pruebas_cnmv/dividendos/` y son parte de las pruebas.
