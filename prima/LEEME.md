# Semáforo de la prima de riesgo (indicador 3)

Cada día hábil, a las 12:10 UTC, el servidor smpro-datos-1 (`servidor/ejecutar.sh prima`, ver `DESPLIEGUE.md`) lee de Eurostat los tipos de interés a largo plazo del criterio de convergencia (media mensual del rendimiento del bono a diez años en el mercado secundario; los datos los recoge el BCE de los bancos centrales nacionales) de España, Alemania, Italia y Francia, y publica en `$ESPEC_DATOS_DIR/prima/` (https://datos.elespeculador.com/prima/):

- `fragmento-wp.html`: semáforo y lectura del día, los cuatro bonos, los diferenciales, el pulso del Tesoro, los máximos de cada episodio de referencia y un gráfico SVG de tres años, entre `<!-- prima:inicio HUELLA -->` y `<!-- prima:fin -->`. La huella solo cambia si cambian los datos;
- `index.html`: página propia de la salida;
- `datos/serie.csv` (rendimientos en % y diferenciales en puntos básicos, mensual, formato largo) y `datos/ultima.json` (resumen versionado, `version` 1.0.0).

La pasada es diaria porque el pulso del Tesoro cambia con cada subasta; las medias mensuales de Eurostat llegan hacia el día 12 del mes siguiente. **Versión diaria pendiente**: el conjunto diario de Eurostat (`irt_lt_mcby_d`) dejó de difundirse (comprobado el 17/11/2026: «not available for dissemination»; el catálogo de Eurostat solo lista el anual, el trimestral y el mensual) y el portal del BCE no publica el rendimiento diario por país. La fuente natural es el Banco de España, cuyo aviso legal está por verificar a mano; cuando esté, el colector pasa a diario sin cambiar de método.

Pregunta del lector: ¿cómo está la deuda española frente a Alemania, Italia y Francia, y cómo van las subastas del Tesoro?

Fuente y licencia: Eurostat, conjunto `irt_lt_mcby_m` (EMU convergence criterion series, monthly data). Política de reutilización de Eurostat (leída el 17/11/2026): libre, también comercial, citando «Fuente: Eurostat» y declarando las modificaciones; los datos los recoge el BCE de los bancos centrales nacionales, y la política del SEBC (verificada el 02/11/2026) es igual de permisiva. Los rendimientos se reproducen sin modificar; los diferenciales, percentiles, variaciones y episodios son cálculos de El Especulador (CC BY 4.0). El pulso del Tesoro reproduce `letras/datos/ultima.json` y `bonos/datos/ultima.json` (D. G. del Tesoro y Política Financiera, aviso legal leído el 17/11/2026) si están al lado de la salida de este colector (o en la carpeta de `--tesoro`); si no están, el bloque no se publica.

Método: diferenciales solo en los meses en que los dos países tienen dato; percentil «débil» (porcentaje de meses con valor igual o inferior) sobre dos ventanas: los últimos tres años (36 meses), que mueven el semáforo (verde por debajo del percentil 50, ámbar entre 50 y 90, rojo desde 90), y desde enero de 2000, que da el contexto con los tramos de los percentiles 25, 50, 75 y 90; variaciones a 1, 3 y 12 meses; máximo mensual dentro de cada episodio de referencia (ventanas fijadas de antemano; es la media del mes, no el pico de un día). Sin predicción: el semáforo describe el presente frente al pasado.

Reglas: si Eurostat no responde, la respuesta cambia de forma, faltan países, hay rendimientos fuera de -3 % a 40 % o han pasado más de 100 días desde el fin del último mes con dato, el script se para sin publicar y `servidor/ejecutar.sh` abre una incidencia con la etiqueta `prima-fallido`. Pasados 50 días solo avisa. Si los países no comparten el último mes, cada ficha lleva el suyo y se avisa.

La dirección pública que el fragmento y el JSON-LD escriben sale de la variable de entorno `ESPEC_DATOS_BASE` (en el servidor, `https://datos.elespeculador.com/`; sin ella, GitHub Pages, valor histórico).

Comprobaciones sin red: `python prima/pruebas_prima.py` (67 comprobaciones con datos simulados de valores conocidos y un caso de control del percentil contra `scipy.stats.percentileofscore`).

Prueba local con una respuesta JSON-stat ya descargada: `python prima/prima.py --salida docs/prima --local eurostat.json --fecha 2026-11-17 --tesoro docs`. Si la huella no cambia, el script no reescribe nada; tras cambiar el código o las plantillas, `--forzar` regenera los ficheros. El flujo de GitHub `prima-validacion` no tiene horario ni escribe en el repositorio: se lanza a mano para validar una rama con datos reales y deja la salida como artefacto.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/prima/fragmento-wp.html` (marcas `prima:inicio`/`prima:fin`), JSON `https://datos.elespeculador.com/prima/datos/ultima.json`; pasada a las 12:10 UTC L-V; hay dato nuevo cuando cambia la huella de la primera línea. Página de WordPress por crear (borrador): /prima-de-riesgo-espana/. El texto pasa por Cumplimiento antes de publicar.
