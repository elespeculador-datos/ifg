# Reloj del ciclo (indicador 20d)

Cada día hábil a las 11:45 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh ciclo`, ver `DESPLIEGUE.md`) lee del API SDMX de la OCDE los indicadores compuestos adelantados y publica en `$ESPEC_DATOS_DIR/ciclo/` (https://datos.elespeculador.com/ciclo/):

- `fragmento-wp.html`: frase del mes, tabla de trece zonas con su fase, el reloj de España (último año), la serie desde 1985 y el método, entre `<!-- ciclo:inicio HUELLA -->` y `<!-- ciclo:fin -->`;
- `index.html`: página propia de la salida;
- `datos/serie.csv` (mes, zona, valor de la OCDE sin tocar, cambio en el mes y fase) y `datos/ultima.json` (versión 1.0.0).

Pregunta del lector: ¿en qué fase del ciclo están España, sus vecinos europeos, las grandes economías y México, Brasil y Turquía, según el indicador adelantado de la OCDE, y desde cuándo?

## Fuente y licencia

OCDE, «Composite leading indicators» (conjunto `DSD_STES@DF_CLI`, versión 4.1): serie principal `LI`, ajustada en amplitud (`AA`), metodología armonizada (`H`), mensual. Consulta: `https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/ESP+G4E+DEU+FRA+ITA+GBR+USA+JPN+CHN+MEX+BRA+TUR+G7.M.LI...AA...H?startPeriod=1955-01` con `Accept: application/vnd.sdmx.data+csv`. Zonas: España (desde 1985), cuatro grandes economías europeas (agregado de la OCDE), Alemania, Francia, Italia, Reino Unido, Estados Unidos, Japón, China, México, Brasil, Turquía y G7.

Licencia verificada el 22/11/2026: [términos y condiciones de oecd.org](https://www.oecd.org/en/about/terms-conditions.html) (última actualización, 1 de julio de 2024): los datos se pueden usar para cualquier fin, también comercial, reconociendo a la OCDE con la cita del conjunto; algunos datos pueden llevar restricciones de terceros (los metadatos de este conjunto no declaran ninguna). La página cita a la OCDE con el conjunto y la fecha de consulta, dice que los datos no se modifican y que la OCDE no la respalda, y enlaza a oecd.org en otra ventana. Las fases, los meses en fase, el reparto y los gráficos son de El Especulador (CC BY 4.0).

## Método

1. Fase de cada mes, con las cuatro de la OCDE («Interpreting OECD Composite Leading Indicators», octubre de 2020: «expansion, downturn, slowdown and recovery»): expansión (por encima de 100 y subiendo), desaceleración (por encima de 100 y bajando), enfriamiento (por debajo de 100 y bajando) y recuperación (por debajo de 100 y subiendo). Dirección = cambio frente al mes anterior; un cambio exactamente nulo conserva la dirección del mes anterior; tras un hueco, el mes siguiente no tiene fase.
2. Por zona: último valor, cambio en el mes y en seis meses, fase, meses en la fase y desde cuándo, meses seguidos en la misma dirección, desde cuándo está del mismo lado de 100 y reparto de todos los meses por fases.
3. Reloj: los últimos trece meses de España, con la distancia a 100 en el eje horizontal y el cambio del mes en el vertical; en un ciclo completo, el indicador recorre los cuadrantes en el sentido de las agujas del reloj.
4. Lo que dice la OCDE de su indicador, en la página: información cualitativa, más por la dirección que por la cifra; no mide cuánto crecerá el PIB; la distancia a 100 no mide cuánto está la economía por encima o por debajo de su tendencia; los niveles no se comparan entre países; se revisa cada mes; en la pandemia dio señales a la vez que la actividad; los giros de la actividad han llegado de media de cuatro a ocho meses después de la señal (metadatos del conjunto).

## Reglas

- Si el CSV no trae las columnas de la OCDE, hay un valor no numérico o fuera de 70-130, España trae menos de 400 meses o su último dato tiene más de cinco meses de desfase: `::error::ciclo`, código 1, incidencia `ciclo-fallido` y no se publica nada nuevo. Con más de tres meses de desfase, una zona que falta o una zona con otro mes: aviso.
- La huella cambia con cualquier valor de cualquier zona (la OCDE revisa meses anteriores cada mes) o con la versión. Sin cambio de huella no se reescribe nada; `--forzar` regenera.
- Sin predicción ni recomendación: la fase describe dónde está el indicador, no lo que hará la economía ni la bolsa.

## Comprobaciones

`python ciclo/pruebas_ciclo.py`: 53 comprobaciones sin red con el fichero real del 22/11/2026 recortado (`ciclo/pruebas_ciclo/cli_20261122.csv`), una serie simulada con diez ciclos conocidos, paradas y avisos, textos, gráficos, huella, escritura, descarga simulada, línea de órdenes y un control con pandas y numpy (fase de cada mes, meses en la fase y reparto).

## Validación con datos reales (22/11/2026)

**Octubre de 2026, España: 99,35**, −0,05 en el mes: por debajo de 100 desde junio de 2026 y bajando desde enero (diez meses): **enfriamiento** («slowdown»), cinco meses en la fase. Las otras doce zonas, salvo China, están por encima de 100: expansión en las cuatro grandes europeas, Alemania, Francia, Reino Unido, Estados Unidos, Brasil, Turquía y G7; desaceleración en Italia, Japón y México; enfriamiento en China (once meses). Desde 1985, España ha pasado el 32,5 % de los meses en expansión, el 22,4 % en desaceleración, el 23,0 % en enfriamiento y el 22,2 % en recuperación. Verificado sobre el dato, no estimado.

## Entrega a Tecnología

- Fragmento: `https://datos.elespeculador.com/ciclo/fragmento-wp.html` (marcas `ciclo:inicio` / `ciclo:fin`); muestra en `ciclo/ejemplos/fragmento-wp.html`.
- JSON: `https://datos.elespeculador.com/ciclo/datos/ultima.json`; CSV: `datos/serie.csv`.
- Pasada: 11:45 de lunes a viernes. Dato nuevo: cambia la huella de la primera línea.
- Página destino: `/reloj-del-ciclo-economico/` (Economía), en borrador. Escenario DIARIO de Make inactivo hasta que el servidor sirva `/ciclo/`.
- Dependencias: `requests` (las pruebas, además, `pandas` y `numpy`).
