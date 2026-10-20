# Rastreador de posiciones cortas

Cada día hábil, a las 16:20 de Madrid, el flujo `cortos-diario` descarga el fichero oficial de la CNMV con las posiciones cortas netas publicadas sobre acciones españolas (`NetShortPositions.xls`) y genera:

- `docs/cortos/index.html`: la página del rastreador (suma publicada por emisor, cambios del día y todas las posiciones);
- `docs/cortos/datos/*.csv` y `ultima.json`: los datos abiertos, con licencia CC BY 4.0 citando a El Especulador y a la CNMV.
- `docs/cortos/fragmento-wp.html`: las mismas tablas en HTML limpio, entre las marcas `<!-- cortos:inicio … -->` y `<!-- cortos:fin -->`. Un escenario de Make lo copia cada tarde en la página «Posiciones cortas en la bolsa española hoy» de elespeculador.com, sustituyendo solo lo que hay entre esas marcas.

Es independiente del IFG: solo lee y escribe `cortos/` y `docs/cortos/`. Si el fichero de la CNMV cambia de forma, el script se para sin publicar y el flujo abre una incidencia con la etiqueta `cortos-fallido`.

Prueba local con un fichero ya descargado: `python cortos/rastreador.py --local NetShortPositions.xls`.

Rehacer solo el fragmento con los CSV ya publicados: `python cortos/rastreador.py --solo-fragmento`.
