# Morosidad bancaria en España (indicador 20g, «Morosidad y crédito»)

Cada día hábil a las 10:50 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh morosidad`, ver `DESPLIEGUE.md`) lee tres cuadros del Boletín Estadístico del Banco de España y publica en `$ESPEC_DATOS_DIR/morosidad/` (https://datos.elespeculador.com/morosidad/):

- `fragmento-wp.html`: frase del mes, tabla y gráfico por segmentos, serie desde 1980, episodios y método, entre `<!-- morosidad:inicio HUELLA -->` y `<!-- morosidad:fin -->`;
- `index.html`: página propia de la salida;
- `datos/serie.csv` (mensual desde 1962: crédito, dudosos y ratio de dudosidad), `datos/segmentos.csv` (trimestral desde 1998: crédito, dudosos y tasa por segmento) y `datos/ultima.json` (versión 1.0.0).

Pregunta del lector: ¿qué parte del crédito a hogares y empresas está en dudas de cobro, cómo está frente a su historia y en qué segmentos (vivienda, consumo, construcción, hostelería…) pesa más?

## Fuente y licencia

Banco de España, Boletín Estadístico, ficheros CSV públicos (`https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/<cuadro>.csv`, codificación ISO-8859-15):

- `be0403` (cuadro 4.3), mensual: crédito a otros sectores residentes (`D_BEEA1000`), dudosos (`D_BEEA1600`) y ratio de dudosidad (`D_BEEA2020`, desde diciembre de 1980);
- `be0413` (cuadro 4.13) y `be0418` (cuadro 4.18), trimestrales desde diciembre de 1998: crédito y dudosos por finalidad (hogares: vivienda, consumo, otros fines) y por rama de actividad (empresas y empresarios individuales).

Licencia verificada el 22/11/2026 (catálogo, licencias): [términos de uso de las estadísticas del Banco de España](https://www.bde.es/wbe/es/estadisticas/recursos/terminos/terminos-de-uso.html) (sin licencia con nombre; acceso y uso libres y gratuitos; sin alterar la información ni sus metadatos; cita obligatoria «Fuente: Sitio web del Banco de España (www.bde.es)» o, con datos tratados, «Fuente: Elaboración propia con datos extraídos del sitio web del Banco de España (www.bde.es)»; fecha de la última actualización si el original la da; sin sugerir que el Banco de España participa o respalda; no se aplica a datos de terceros) y [aviso legal de bde.es](https://www.bde.es/wbe/es/pie/aviso-legal/) (enlaces a bde.es en otra ventana; en productos de pago, avisar de que la información es gratuita en bde.es). Las tres series son del propio Banco de España (estados de supervisión), no de terceros. La página cumple las condiciones: las dos fórmulas de cita, la fecha `Last-Modified` de cada fichero, la frase de no respaldo, el aviso de gratuidad y `target="_blank"` en los enlaces. Los cálculos de El Especulador, CC BY 4.0.

## Método

1. Tasa del mes: la ratio de dudosidad tal como la publica el Banco de España (dudosos / crédito × 100, a dos decimales; el colector comprueba que cuadra en los últimos 36 meses y para si no). Variaciones en puntos a uno y doce meses; variación interanual de dudosos y crédito.
2. Percentil histórico desde diciembre de 1980 (porcentaje de meses con una tasa igual o inferior; definición «débil», la de `scipy.stats.percentileofscore(kind="weak")`) y tramo por percentiles 25, 50, 75 y 90, los mismos que el indicador de estrés financiero.
3. Periodos en que la tasa estuvo igual o por debajo de la actual; «la más baja desde» o «la más alta desde» solo si hace al menos doce meses que no estaba así; máximo y mínimo de la serie.
4. Episodios con ventanas fijadas de antemano (años ochenta, 1993, mínimo anterior a 2008, crisis financiera y del euro): el valor es el que da el dato.
5. Segmentos: tasa calculada por El Especulador (dudosos / crédito de cada finalidad o rama) en el último trimestre común a los cuadros 4.13 y 4.18, la del mismo trimestre un año antes y el máximo de cada serie desde 1998. El total por finalidades coincide con la ratio mensual del mismo mes (diferencia máxima de 0,01 puntos en los 111 trimestres, por redondeo).
6. Definiciones tomadas de las notas del capítulo 4 del Boletín Estadístico y del glosario del Banco de España (leídos el 22/11/2026): dudoso = dudas razonables sobre su reembolso total; los morosos (algún importe vencido hace más de tres meses) son una parte; «otros sectores residentes» = residentes que no son administraciones públicas ni entidades de crédito.

## Reglas

- Si un fichero no empieza por «CÓDIGO DE LA SERIE», falta una serie, hay un valor no numérico o una fila que no es un mes, la ratio no cuadra, hay menos de 400 meses o de 40 trimestres, o el último dato tiene más de 6 meses (mensual) o 10 (trimestral) de desfase: `::error::morosidad`, código 1, incidencia `morosidad-fallido` y no se publica nada nuevo. Con más de 4 y 7 meses de desfase, aviso.
- Lo publicado solo se reescribe si cambia la huella (todos los datos de las tres tablas, también revisiones de meses antiguos, y la versión) o si falta algún fichero; `--forzar` regenera.
- Sin predicción ni recomendación, sin entidades concretas; contenido informativo y educativo.

## Comprobaciones

`python morosidad/pruebas_morosidad.py`: 72 comprobaciones sin red con los ficheros reales del 22/11/2026 recortados a las series que se usan (`morosidad/pruebas_morosidad/`), casos simulados con valores conocidos, paradas, descarga simulada, textos, huella, escritura, línea de órdenes y controles con scipy y pandas (percentil, tasas de dos segmentos sobre el CSV y periodos).

## Validación con datos reales (22/11/2026)

Descarga real de los tres ficheros (cuadro 4.3 actualizado por el Banco de España el 26/10/2026; 4.13 y 4.18, el 25/09/2026). **Agosto de 2026: 2,53 %** (31.540 millones de euros dudosos de 1,25 billones), +0,02 puntos en un mes y -0,40 en un año; dudosos -10,9 % y crédito +3,1 % en un año. Percentil 23 desde 1980 (tramo «bajo»): solo estuvo igual o por debajo entre junio de 1998 y agosto de 2008 y en julio de 2026. Máximo, 13,62 % (diciembre de 2013); mínimo, 0,72 % (diciembre de 2006). Junio de 2026 por segmentos: compra de vivienda 1,42 %, consumo 4,04 %, construcción 6,07 % (máximo de 34,27 % en 2013), actividades inmobiliarias 1,51 % (38,04 % en 2014), intermediación financiera no bancaria 0,43 %. La ratio publicada es dudosos / crédito en los 549 meses. Verificado sobre el dato, no estimado.

## Entrega a Tecnología

- Fragmento: `https://datos.elespeculador.com/morosidad/fragmento-wp.html` (marcas `morosidad:inicio` / `morosidad:fin`); muestra en `morosidad/ejemplos/fragmento-wp.html`.
- JSON: `https://datos.elespeculador.com/morosidad/datos/ultima.json`; CSV: `datos/serie.csv` y `datos/segmentos.csv`.
- Pasada: 10:50 de lunes a viernes (el Banco de España sube estos ficheros por la mañana; el del cuadro 4.3, el 26/10/2026 a las 09:58). Dato nuevo: cambia la huella de la primera línea.
- Página destino: `/morosidad-bancaria-espana/` (Economía › Banca), en borrador. Escenario DIARIO de Make inactivo hasta que el servidor sirva `/morosidad/`.
- Dependencias: `requests` (las pruebas, además, `pandas` y, si está, `scipy`).
