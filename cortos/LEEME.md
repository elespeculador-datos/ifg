# Rastreador de posiciones cortas

Cada día hábil, por la noche (18:40 y 19:40 UTC, con una pasada más a las 05:00 UTC), el flujo `cortos-diario` descarga el fichero oficial de la CNMV con las posiciones cortas netas publicadas sobre acciones españolas (`NetShortPositions.xls`) y genera:

- `docs/cortos/index.html`: la página del rastreador (suma publicada por emisor, cambios del día y todas las posiciones);
- `docs/cortos/datos/*.csv` y `ultima.json`: los datos abiertos, con licencia CC BY 4.0 citando a El Especulador y a la CNMV.
- `docs/cortos/fragmento-wp.html`: las mismas tablas en HTML limpio, entre las marcas `<!-- cortos:inicio … -->` y `<!-- cortos:fin -->`. Un escenario de Make lo copia cada noche (y a primera hora, si hiciera falta) en la página «Posiciones cortas en la bolsa española hoy» de elespeculador.com, sustituyendo solo lo que hay entre esas marcas.

Es independiente del IFG: solo lee y escribe `cortos/` y `docs/cortos/`. Si el fichero de la CNMV cambia de forma, el script se para sin publicar y el flujo abre una incidencia con la etiqueta `cortos-fallido`.

Prueba local con un fichero ya descargado: `python cortos/rastreador.py --local NetShortPositions.xls`.

Rehacer solo el fragmento con los CSV ya publicados: `python cortos/rastreador.py --solo-fragmento`.

## Lo nuevo del indicador 1 (presión bajista): sector, evolución y semana

Desde la versión del 19/11/2026 el fragmento y `ultima.json` añaden tres bloques, calculados con lo que ya publica la CNMV:

- **Presión bajista por sector** (`datos/sectores.csv`): con la clasificación propia de `sectores.csv`, por sector: emisores con cortos publicados, suma de las sumas publicadas de sus emisores, media por emisor, tenedores y el emisor con más suma. Mide dónde se concentran las apuestas en contra, no un porcentaje del sector. Los emisores sin fila en `sectores.csv` van a «sin sector» y abren aviso; sin la tabla sectorial el bloque no se publica y lo demás no cambia.
- **Evolución de la suma publicada** (`datos/evolucion.csv`): para los quince emisores con más suma hoy, la suma vigente hace 4, 13 y 52 semanas, reconstruida con la serie histórica de notificaciones de la CNMV (hojas «Serie» y «Anteriores»): en cada fecha cuenta la última notificación de cada tenedor y se suman las iguales o superiores al 0,5 %.
- **Entradas y salidas de la semana** (`semana` en `ultima.json`): posiciones nuevas y posiciones que dejan de publicarse en los últimos siete días, con recuento de subidas y bajadas, a partir de `historial_cambios.csv`.

La huella del fragmento sigue siendo la fecha de publicación de la CNMV. Comprobaciones nuevas en `pruebas_rastreador.py` (sector, `suma_en`, evolución, semana y fragmento con y sin los bloques). Sin predicción: «describe cómo ha cambiado la presión, no hacia dónde irá».

Comprobaciones, sin red: `python cortos/pruebas_rastreador.py` (cálculos) y `python cortos/pruebas_descarga.py` (descarga).

La hoja «Última» de la CNMV no garantiza una sola fila por (ISIN, tenedor): el mismo tenedor puede aparecer dos veces sobre el mismo valor cuando el fichero recoge a la vez una posición y la comunicación con la que cruza el 0,5 %. Para los cambios del día y la suma por emisor se usa la comunicación de `fecha_posicion` más reciente, y el registro de la ejecución lo avisa. La tabla de todas las posiciones sí las muestra las dos: son dos comunicaciones reales.

La CNMV cierra la conexión sin responder de vez en cuando (seis ejecuciones entre el 21 y el 31 de octubre de 2026). La descarga lo intenta siete veces, con esperas de 10 a 120 segundos, y cada intento fallido queda en el registro de la ejecución. Si falla igualmente, el flujo abre o comenta la incidencia `cortos-fallido` y las otras dos pasadas del día vuelven a intentarlo.

## Clasificación sectorial propia (`sectores.csv`, `sectores.py`)

Para el agregado por sector de los cortos (lo nuevo del indicador 1) y de las compras y ventas de directivos (indicador 10), El Especulador usa una clasificación propia de ocho sectores, asignada a mano por Datos a partir de la actividad que declara cada empresa (web corporativa e informe anual), sin usar la clasificación de BME ni la de la CNMV: energía y utilities; industria y construcción; consumo (incluye medios y ocio); financiero y seguros; inmobiliario; tecnología y telecomunicaciones; salud y farmacia; turismo y transporte.

`sectores.csv` (19/11/2026): 59 emisores, todo el IBEX 35 más los emisores con posiciones cortas publicadas desde noviembre de 2025 en los datos del repositorio. Cada fila lleva ISIN, emisor, sector, actividad, fuente, fecha de asignación y nota (los casos discutibles, como Amadeus, Logista, Fluidra, Ence o Viscofan, explican por qué se han clasificado así). Un emisor que no esté en la tabla se agrega como «sin sector» y abre aviso (`::warning::`), no incidencia; se añade a la tabla en la siguiente pasada de mantenimiento.

`sectores.py`: `cargar()` (para si hay un sector desconocido o un ISIN repetido), `sector_de(isin, tabla)`, `sin_sector(isines, tabla)` y `agregar(filas, tabla)` (suma por sector con recuento de emisores). Comprobaciones: `python cortos/pruebas_sectores.py` (26, cobertura del IBEX 35 y de los cortos recientes incluida). Todavía no lo usa ningún colector en producción; el rastreador de cortos no cambia con esta entrega.
