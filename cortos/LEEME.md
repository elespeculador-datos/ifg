# Rastreador de posiciones cortas

Cada día hábil, por la noche (18:40 y 19:40 UTC, con una pasada más a las 05:00 UTC), el flujo `cortos-diario` descarga el fichero oficial de la CNMV con las posiciones cortas netas publicadas sobre acciones españolas (`NetShortPositions.xls`) y genera:

- `docs/cortos/index.html`: la página del rastreador (suma publicada por emisor, cambios del día y todas las posiciones);
- `docs/cortos/datos/*.csv` y `ultima.json`: los datos abiertos, con licencia CC BY 4.0 citando a El Especulador y a la CNMV.
- `docs/cortos/fragmento-wp.html`: las mismas tablas en HTML limpio, entre las marcas `<!-- cortos:inicio … -->` y `<!-- cortos:fin -->`. Un escenario de Make lo copia cada noche (y a primera hora, si hiciera falta) en la página «Posiciones cortas en la bolsa española hoy» de elespeculador.com, sustituyendo solo lo que hay entre esas marcas.

Es independiente del IFG: solo lee y escribe `cortos/` y `docs/cortos/`. Si el fichero de la CNMV cambia de forma, el script se para sin publicar y el flujo abre una incidencia con la etiqueta `cortos-fallido`.

Prueba local con un fichero ya descargado: `python cortos/rastreador.py --local NetShortPositions.xls`.

Rehacer solo el fragmento con los CSV ya publicados: `python cortos/rastreador.py --solo-fragmento`.

Comprobaciones, sin red: `python cortos/pruebas_rastreador.py`.

La hoja «Última» de la CNMV no garantiza una sola fila por (ISIN, tenedor): el mismo tenedor puede aparecer dos veces sobre el mismo valor cuando el fichero recoge a la vez una posición y la comunicación con la que cruza el 0,5 %. Para los cambios del día y la suma por emisor se usa la comunicación de `fecha_posicion` más reciente, y el registro de la ejecución lo avisa. La tabla de todas las posiciones sí las muestra las dos: son dos comunicaciones reales.
