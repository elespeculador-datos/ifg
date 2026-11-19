# Recompras del IBEX 35 (indicador 17)

Pregunta del lector: ¿qué empresas del IBEX 35 están recomprando acciones propias esta semana, cuántas, a qué precio medio y cuánto llevan ejecutado de su programa?

Estado: **colector completo (1.0.0) en rama `recompras`**, pendiente de fusión y de despliegue. La fase 0 (viabilidad, 18-19/11/2026) está documentada más abajo.

## Fuente y licencia

Los informes que las empresas con programa de recompra envían a la CNMV como «Otra Información Relevante» en cumplimiento del art. 5 del Reglamento (UE) 596/2014 y del art. 2 del Reglamento Delegado (UE) 2016/1052: una tabla por día y centro de negociación con el número de acciones y el precio medio ponderado, más el acumulado del programa en el texto cuando la empresa lo declara. El colector `cnmv` ya los identifica (caja `recompras` de `cnmv/datos/ibex35.csv`; 40 comunicados de 12 empresas en el listado del 18/11/2026); cada página `Resultado-OIR.aspx?nreg=N` enlaza su PDF (`webservices/verdocumento/ver?t={guid}`).

Licencia: nota legal de la CNMV, verificada el 02/11/2026 (reproducción fiel citando la fuente; si entra en un producto de pago, decir que el dato es gratuito en cnmv.es). Personas físicas: no se guarda quién firma el informe; solo cifras. Sin predicción ni recomendación: «históricamente, los programas de recompra reducen el número de acciones en circulación», nunca «sostendrá la cotización».

## Qué hace `recompras.py`

1. Lee el listado (`--cnmv`, por defecto `<datos>/cnmv/datos/ibex35.csv`, donde `--datos` es la carpeta madre de `--salida`; admite URL) y se queda con la caja `recompras`.
2. Para cada comunicado que no haya leído (memoria en `datos/informes.csv`), abre su página en la CNMV, descarga hasta tres documentos `verdocumento`, pasa cada PDF por `pdftotext -layout` y se queda con el primero que tenga filas. Hasta 40 comunicados por pasada (`--max`), con un segundo de pausa entre peticiones; un error de red se reintenta en las pasadas siguientes hasta tres veces.
3. `filas.py` lee la tabla diaria (fecha, centro, acciones, precio; ver fase 0) y `resumen_programa()` extrae del texto el porcentaje ejecutado del importe máximo, el importe acumulado en euros, las acciones acumuladas, el porcentaje del capital y si el programa ha terminado (patrones vistos en Sabadell, BBVA, CaixaBank, Cellnex y Ferrovial; lo que no consta queda vacío).
4. Cada informe queda en `datos/informes.csv` con su estado: `leido` (con filas), `sin_filas` (tabla como imagen: solo el acumulado del texto; caso BBVA), `sin_texto` (sin documento) o `error`. La suma de acciones se contrasta con el total que declara el documento (`coincide`); si no coincide, la fila sale «a verificar» y el flujo avisa (`::warning::`). Las filas diarias van a `datos/operaciones.csv`.
5. Cálculo (`datos/ultima.json`): **semana** = último informe de cada empresa comunicado en los últimos siete días (acciones, precio medio ponderado, importe estimado = acciones × precio medio, periodo, programa ejecutado); **en curso** = último informe de cada empresa en 45 días, con los programas terminados aparte; **serie semanal** del IBEX (`datos/semanal.csv`, semanas ISO por su lunes: empresas, acciones, importe estimado de las filas en euros), con percentil débil de la última semana completa cuando haya 52 (hasta entonces el fragmento lo dice). Si una empresa compra en varias monedas (IAG: libras en Londres y euros en Madrid), el importe estimado solo suma las filas en euros y la tabla lo marca «(solo euros)».
6. Salida: `fragmento-wp.html` entre `<!-- recompras:inicio HUELLA -->` y `<!-- recompras:fin -->` (frase de la semana, tabla de comunicados de siete días, programas en curso, ritmo semanal, cómo se lee, JSON-LD Dataset), `index.html` y `datos/ultima.json`. La huella (SHA-256, 12 caracteres) no depende de la fecha de la pasada ni de los bordes de la ventana: solo cambia con comunicados u operaciones nuevos, así la página no se reescribe cada día. El estado (`informes.csv`, `operaciones.csv`, `semanal.csv`) se guarda en cada pasada.

Reglas: sin listado o sin comunicados de recompra en él, `DatosRaros` y el script se para sin escribir (`servidor/ejecutar.sh` abre la incidencia `recompras-fallido`); si ningún comunicado se ha podido leer nunca, también. Un comunicado sin documento o con tabla ilegible no para nada: sale con su estado.

## Pruebas y validación

`python recompras/pruebas_recompras.py`: 91 comprobaciones sin red. Fase 0: el lector de filas con textos en la maquetación real de Repsol, IAG, CaixaBank, Ferrovial y ACS, control de la media ponderada frente a `numpy.average`. Fase 1: acumulado del programa con los textos reales de Sabadell, BBVA, CaixaBank y Cellnex; documentos de la página del comunicado; registro de cada informe (documento elegido, importe estimado, coincidencia, estados); pendientes y reintentos; serie semanal (control frente a `pandas`, periodos W-SUN); cálculo, huella estable y fragmento; pasada completa sin red con `--local` y escritura solo con cambios.

Pasada local sin red: `python recompras/recompras.py --salida /tmp/recompras --local CARPETA --fecha AAAA-MM-DD`, con `ibex35.csv` y un `<nreg>.txt` (salida de `pdftotext -layout`) por comunicado en CARPETA. Con los ocho textos de la sonda del 18/11: 7 leídos, 1 sin filas (BBVA), 5 de 5 coinciden con el total declarado, semana de 13.809.506 acciones y 198,7 M€ estimados; la segunda pasada no reescribe nada.

El flujo `recompras-validacion` (solo a mano, sin horario ni escritura en el repositorio) hace una pasada completa con el listado real servido por `datos.elespeculador.com` y los PDF reales de la CNMV, y deja el fragmento en el registro y la salida como artefacto.

## Despliegue y entrega a Tecnología

- Servidor: `servidor/ejecutar.sh recompras` (convención genérica: `recompras/recompras.py --salida $ESPEC_DATOS_DIR/recompras`; el listado se lee de `$ESPEC_DATOS_DIR/cnmv/datos/ibex35.csv`). Cron propuesto: martes y jueves a las 08:30 de Madrid (las empresas envían el informe el lunes o el martes por la mañana; el jueves recoge rezagados). Necesita `requests` y `poppler-utils` (ya en el servidor). Carpeta `recompras` en la lista blanca de nginx. La primera pasada lee los 40 comunicados del listado (unos dos minutos).
- Fragmento: `https://datos.elespeculador.com/recompras/fragmento-wp.html` (marcas `recompras:inicio`/`recompras:fin`); JSON `https://datos.elespeculador.com/recompras/datos/ultima.json`. Dato nuevo = cambia la huella de la primera línea (normalmente martes). Página de WordPress: `/recompras-ibex-35/`, en borrador hasta la regla de 48 horas.
- Ficha integrada (indicador 16): cuando este colector esté en el servidor, `empresas/<ISIN>.json` podrá añadir el bloque `recompra.ejecutado` (acciones y precio medio de la semana) leyendo `recompras/datos/informes.csv`.

Horas de Federico: 0 (fusionar; pasar al chat del IFG la línea de cron y la carpeta de nginx).

## Fase 0 (18-19/11/2026): viabilidad, cerrada

Sonda (flujo `recompras-validacion`, ejecuciones 44420762376 y 44422466552) sobre el último informe de ocho empresas con programa en marcha:

| Empresa | Maqueta del PDF | Lector genérico | Control |
|---|---|---|---|
| Repsol | fecha+ticker con un espacio, Compra, centro, acciones, precio; anexo con cada operación | 20 filas (5 días × 4 centros) | sin total declarado; filas = días × centros |
| IAG | fecha `09-Nov-26`, LON/MAD, miles con coma, `£ 4.448` / `€ 5.340`; anexo en inglés | 9 filas, medio por moneda | 5.110.635 acciones = «Total» del anexo |
| ACS | fecha, ACS.MA, centro, acciones, precio con tres decimales, intermediario | 3 filas | sin total declarado |
| Cellnex | fecha, CLNX, COMPRAR, centro, acciones, precio; línea «TOTAL:» | 20 filas | 492.309 = TOTAL declarado; medio 26,6982 (declara 26,70) |
| Banco Sabadell | fecha, SAB, COMPRA, centro, títulos, precio; «Total…»; anexo bilingüe | 10 filas | 3.305.308 = Total declarado |
| Ferrovial | centro «Centros de negociación estadounidenses», precio con dos decimales, total en estilo inglés | 6 filas | 330.000 = Total declarado; medio 54,6133 (declara 54.61) |
| BBVA | la tabla diaria no sale como texto (`pdftotext` solo devuelve el preámbulo y el importe acumulado) | 0 filas | no legible sin OCR |
| CaixaBank | instrumento, fecha, Compra, acciones, precio, importe, centro; «TOTAL»; anexo con hora | 16 filas | 743.453 = TOTAL declarado; medio 11,5934 exacto |

Siete de ocho maquetas se leen con un único lector sin reglas por empresa; en las cinco que declaran total, la suma coincide. BBVA incrusta la tabla como imagen: solo se lee el acumulado del texto (OCR no previsto).

Cómo lee `filas.py`: toda fila comparte tres señas, sea cual sea el orden de columnas: una fecha (`dd/mm/aaaa` o `dd-Mon-aa`), un centro de negociación (código MIC o abreviatura: XMAD, CEUX, TQEX, AQEU, XLON, LON, MAD…, o el texto «Centros de negociación estadounidenses» → EEUU) y al menos dos cifras, de las que la primera es el número de acciones (entero) y la segunda el precio medio. El estilo numérico lo fija la fecha de la línea (española: punto de miles y coma decimal; inglesa: al revés). Un símbolo de moneda delante del precio (£, $, €) fija la moneda; por defecto, euros. Solo se lee la primera tabla del documento: el texto se corta en la primera línea que empieza por «Anexo», «Se acompaña», «Detalle de/sobre las/cada», «Transaction details» o «Individual trade», porque los anexos repiten cada operación individual (con hora) y duplicarían la suma; si antes de esa marca no hay filas, se lee todo y se descartan las filas con hora. Las líneas «Total» se extraen aparte (`totales_declarados`) para contrastar la suma.
