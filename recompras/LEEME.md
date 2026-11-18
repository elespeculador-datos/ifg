# Recompras del IBEX 35 (indicador 17), fase 0: viabilidad

Pregunta del lector: ¿qué empresas del IBEX 35 están recomprando acciones propias esta semana, cuánto y a qué precio medio, y cuánto llevan ejecutado de su programa?

Estado: **fase 0 cerrada el 19/11/2026, viable**. La fase 1 (colector semanal con fragmento y JSON) está por hacer; esta carpeta tiene el lector de filas probado con datos reales, su batería de pruebas y la sonda de GitHub que lo valida contra los documentos de la CNMV.

## Qué se ha comprobado

Fuente: los informes semanales que las empresas envían a la CNMV como «Otra Información Relevante» en cumplimiento del art. 5 del Reglamento (UE) 596/2014 y de los arts. 2.2 y 2.3 del Reglamento Delegado (UE) 2016/1052. El colector `cnmv` ya los identifica (caja `recompras` de `cnmv/datos/ibex35.csv`: 40 comunicados de 12 empresas en el listado del 18/11/2026) y cada página `Resultado-OIR.aspx?nreg=N` enlaza un PDF (`webservices/verdocumento/ver?t={guid}`). Licencia: nota legal de la CNMV ya verificada para el colector `cnmv` (reproducción fiel citando la fuente; si entra en un producto de pago, decir que el dato es gratis en cnmv.es).

Sonda del 18/11/2026 (flujo `recompras-validacion`, ejecución 44420762376) sobre el último informe de ocho empresas:

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

Siete de ocho maquetas se leen con un único lector sin reglas por empresa (confirmado con los PDF descargados en GitHub el 19/11/2026, ejecución 44422466552 del flujo); en las cinco que declaran total, la suma de acciones coincide y el precio medio ponderado también (CaixaBank al cuarto decimal). BBVA incrusta la tabla como imagen: para esa empresa solo se puede leer el importe acumulado y el porcentaje del programa que figuran en el texto, o pasar el PDF por OCR (no previsto en fase 1).

## Cómo lee `filas.py`

Toda fila de operaciones comparte tres señas, sea cual sea el orden de columnas: una fecha (`dd/mm/aaaa` o `dd-Mon-aa`), un centro de negociación (código MIC o abreviatura: XMAD, CEUX, TQEX, AQEU, XLON, LON, MAD…, o el texto «Centros de negociación estadounidenses» → EEUU) y al menos dos cifras, de las que la primera es el número de acciones (entero) y la segunda el precio medio. El estilo numérico lo fija la fecha de la línea: con fecha española el punto separa miles y la coma decimales; con fecha inglesa, al revés. Un símbolo de moneda delante del precio (£, $, €) fija la moneda; por defecto, euros.

Solo se lee la primera tabla del documento (el resumen por día y centro): el texto se corta en la primera línea que empieza por «Anexo», «Se acompaña», «Detalle de/sobre las/cada», «Transaction details» o «Individual trade», porque los anexos repiten cada operación individual (con hora) y duplicarían la suma. Si antes de esa marca no hay filas, se lee todo y se descartan las filas con hora. Las líneas «Total» del documento se extraen aparte (`totales_declarados`) para contrastar la suma.

`resumen(filas)` devuelve acciones compradas, precio medio ponderado por moneda, fechas, días y centros del documento.

## Pruebas

`python recompras/pruebas_recompras.py`: 37 comprobaciones con textos simulados en la maquetación real de Repsol, IAG, CaixaBank, Ferrovial y ACS (estilos numéricos, centro en texto, corte del anexo, filas con hora, ventas, fechas imposibles, totales declarados) y un caso de control de la media ponderada frente a `numpy.average`.

El flujo `recompras-validacion` (solo a mano, sin horario ni escritura) descarga los últimos informes de hasta ocho empresas, imprime las primeras líneas de cada PDF y el resultado del lector, y dice si la suma coincide con el total declarado.

## Fase 1 (pendiente de encargo): diseño propuesto

- Frecuencia: semanal, martes a las 08:00 de Madrid (las empresas publican el informe el lunes o el martes por la mañana), más una pasada el jueves para rezagados. Lee `cnmv/datos/ibex35.csv` (caja `recompras`), toma los comunicados nuevos desde la última pasada, descarga el PDF, aplica `filas.py` y guarda cada fila en `datos/operaciones.csv` (empresa, ISIN, nreg, fecha, centro, acciones, precio, moneda) con memoria de los `nreg` ya leídos.
- Del texto de cada informe se extraen, cuando constan, el importe acumulado del programa y el porcentaje ejecutado («asciende a X euros, que representa el Y % del importe máximo»), con el patrón visto en Sabadell, BBVA y CaixaBank (Cellnex da en cambio las acciones totales del programa y su porcentaje del capital).
- Salida: `fragmento-wp.html` (`recompras:inicio`/`recompras:fin`) con la tabla de la semana (empresa, días, acciones, precio medio, importe estimado = acciones × precio medio, marcado como estimación, y porcentaje del programa si consta) y la lista de programas activos; `datos/semana.json` versionado; `index.html`.
- Reglas: si un PDF no da filas (caso BBVA), la empresa sale con «sin detalle legible» y el importe acumulado si consta; si la suma no coincide con el total declarado, la fila se marca `a verificar` y se avisa (`::warning::`); sin filas en ninguna empresa durante tres semanas, `DatosRaros`.
- Marco educativo: «históricamente, los programas de recompra…»; nunca «sostendrá la cotización». Sin personas físicas (los firmantes de los informes no se guardan).
- Esfuerzo: ~6 horas de Datos; 0 horas de Federico salvo revisar el fragmento en borrador. Página destino: nueva página de datos `/recompras-ibex/`, en borrador hasta su visto bueno.

Horas de Federico en la fase 0: 0.
