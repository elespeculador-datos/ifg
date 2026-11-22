# Despliegue: GitHub como fuente de verdad, ejecución en el servidor

Acordado entre Datos y el proyecto IFG el 17/11/2026 y autorizado por Federico ese día; el traspaso del servidor se hizo el 17/11 a las 20:54 (hora de Madrid).

- **El código vive en `main` de GitHub.** Todo cambio entra por rama y PR; el servidor `smpro-datos-1` no lleva commits propios.
- **Los datos no van en el git del servidor.** Cada colector escribe su salida en su propia carpeta de datos, fuera del árbol del repositorio, que es la que sirve `https://datos.elespeculador.com/<colector>/`. Así `git pull` nunca choca.
- **La dirección pública de cada salida es configurable** con la variable de entorno `ESPEC_DATOS_BASE` (siempre con barra final o sin ella; el código la normaliza):
  - sin variable: `https://elespeculador-datos.github.io/ifg/` (GitHub Pages, valor histórico);
  - en el servidor: `ESPEC_DATOS_BASE=https://datos.elespeculador.com/`.
  La variable solo cambia las direcciones que el colector escribe en sus propias salidas (enlaces de los fragmentos, `contentUrl` del marcado Dataset de JSON-LD y `ultima.json`). No cambia dónde se escribe en disco: eso lo fija `--salida`.
- **Las Actions de GitHub con horario quedan desactivadas** mientras la ejecución esté en el servidor; se conservan como documentación del horario y de las dependencias de cada colector. Los flujos `*-validacion` se lanzan solo a mano y no escriben en el repositorio. GitHub Pages deja de ser la dirección de lectura de los escenarios de Make: los DIARIO y ARCHIVO 1 leen `datos.elespeculador.com`.

## Servidor smpro-datos-1: cómo se ejecutan los colectores

- **Dos checkouts, a propósito.** Los colectores corren desde `/home/smpro/colectores-main`, que `ejecutar.sh` trae a `main` en cada pasada (`git pull --ff-only`): cualquier fusión en `main` entra en producción de los colectores en la siguiente pasada. El IFG corre desde `/home/smpro/ifg`, que solo se actualiza cuando el proyecto IFG despliega una versión: sus reglas están congeladas y versionadas y no deben cambiar por una fusión ajena. Ninguno de los dos checkouts lleva commits locales ni datos.
- Usuario del cron: `smpro`, dueño de los dos checkouts y de `$ESPEC_DATOS_DIR`.
- Entorno en `/etc/smpro/entorno` (plantilla en `servidor/entorno.ejemplo`; `root:smpro`, 640): `ESPEC_DATOS_DIR=/var/www/datos` (carpeta que sirve datos.elespeculador.com, fuera del git), `ESPEC_DATOS_BASE=https://datos.elespeculador.com/`, `SMPRO_PYTHON=/home/smpro/venv/bin/python` y `GH_TOKEN` (token de grano fino con permiso de incidencias sobre `elespeculador-datos/ifg`; lo escribe Federico directamente en el servidor; mientras falte, `avisar.sh` solo deja el aviso en el registro).
- El IFG escribe en la misma carpeta (`$ESPEC_DATOS_DIR/ifg/`) desde su propio `ifg-diario.sh`, sin commits en el git del servidor, y guarda una copia diaria de sus datos en `/home/smpro/respaldo/ifg-datos/`.
- Cada pasada: `servidor/ejecutar.sh <colector>`. Trae `main` con avance rápido, ejecuta el colector escribiendo en `$ESPEC_DATOS_DIR/<colector>`, deja el estado de la pasada en `$ESPEC_DATOS_DIR/estado/<colector>.json` (público: lo pueden leer el Mapa de sistemas y los escenarios de Make) y abre, comenta o cierra la incidencia `<colector>-fallido` en GitHub con `servidor/avisar.sh`. Registro en `$ESPEC_DATOS_DIR/registro/<colector>-AAAA-MM-DD.log` (nginx no sirve `/registro/`: los registros no son públicos). Los `estado/colector-*.json` del envoltorio anterior (`/home/smpro/bin/colector.sh`) ya no se actualizan y se retiran. **Una pasada a la vez por colector** (desde el 22/11/2026): `ejecutar.sh` toma un cerrojo (`flock` sobre `/tmp/smpro-<colector>.lock`); si la pasada anterior del mismo colector sigue en marcha, la nueva lo anota en el registro y termina sin tocar nada (código 0, sin estado nuevo ni incidencia). Sin `flock` en el sistema, sigue como antes.
- `git pull` es anónimo porque el repositorio es público; si pasara a privado, el checkout de los colectores necesitaría una clave de despliegue de solo lectura.
- `opas`, `dividendos` e `ibex` no se ejecutan (API de BME sin licencia, P3); el script lo rechaza.
- Antes de la primera pasada de un colector nuevo, copiar sus datos actuales a `$ESPEC_DATOS_DIR/<colector>/` si los tiene (cortos y cnmv leen su publicación anterior para calcular los cambios). `ahorro` rellena el euríbor del BOE con `python ahorro/ahorro.py --salida $ESPEC_DATOS_DIR/ahorro --meses-atras 36` (hecho el 17/11).
- Crontab del usuario `smpro`, **en hora de Madrid** (el cron del servidor no admite `CRON_TZ`; las fuentes de todos los colectores publican en hora peninsular, así que la hora local es la que conviene, y en verano todo sigue a la misma hora local). Equivalencias: cortos 19:40 y 20:40 L-V y 06:00 M-S; cnmv al minuto 7 de 06 a 23 todos los días (desde el 21/11/2026: la CNMV también registra comunicados por la noche y en fin de semana, como el de ACS del sábado 07/11, y el colector de WordPress que sustituye los publicaba a la hora siguiente; cada pasada rellena además por número de registro lo que el RSS no trae); letras 13:30; bonos 13:40; accionistas 06:45 M-S; estres 12:20; prima 14:10 (después de letras y bonos, para que el pulso del Tesoro lleve la subasta del día); ahorro lunes 08:30; agenda todos los días 06:20 (la semana nueva aparece el lunes; el escenario de Make la copia entre las 06:45 y las 08:30). directivos 07:10 L-S (relee los últimos 21 días y rellena el histórico hacia 2018 a razón de 300 PDF por pasada; la primera tarda unos minutos). divisas 16:40 L-V (el BCE fija los tipos de referencia hacia las 16:00 CET). expectativas 11:30 L-V (una petición; la encuesta del BCE sale una vez al mes). cot sábados y lunes 07:00 (la CFTC publica el viernes a las 15:30 de Washington; el lunes recoge retrasos). empresas 07:40 L-S y 21:10 L-V (la ficha integrada solo lee las salidas de los demás colectores de `$ESPEC_DATOS_DIR`: después de directivos por la mañana y de cortos por la noche). recompras martes y jueves 08:30 (las empresas envían el informe semanal el lunes o el martes por la mañana; el jueves recoge rezagados; lee el listado de `cnmv/` de la misma carpeta).

```
40 19 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
40 20 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
0  6  * * 2-6  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
7  6-23 * * *   /home/smpro/colectores-main/servidor/ejecutar.sh cnmv
30 13 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh letras
40 13 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh bonos
45 6  * * 2-6  /home/smpro/colectores-main/servidor/ejecutar.sh accionistas
20 12 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh estres
10 14 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh prima
30 8  * * 1    /home/smpro/colectores-main/servidor/ejecutar.sh ahorro
20 6  * * *    /home/smpro/colectores-main/servidor/ejecutar.sh agenda
10 7  * * 1-6  /home/smpro/colectores-main/servidor/ejecutar.sh directivos
40 16 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh divisas
30 11 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh expectativas
0 7   * * 1,6  /home/smpro/colectores-main/servidor/ejecutar.sh cot
50 8,19 * * 1-5 /home/smpro/colectores-main/servidor/ejecutar.sh ofertas
40 7  * * 1-6  /home/smpro/colectores-main/servidor/ejecutar.sh empresas
10 21 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh empresas
30 8  * * 2,4  /home/smpro/colectores-main/servidor/ejecutar.sh recompras
37 6-23 * * *  /home/smpro/colectores-main/servidor/ejecutar.sh calendario
```

- Dependencias de Python en el entorno virtual: `pandas xlrd python-calamine requests openpyxl certifi numpy scipy` (con `constraints` del `pip freeze` del servidor) y el paquete del sistema `poppler-utils` (letras y bonos leen PDF). `prima` y `ahorro` solo necesitan `requests pandas numpy scipy`; `agenda`, solo `requests` (y `zoneinfo`, de la biblioteca estándar desde Python 3.9). `directivos` necesita `requests` y `poppler-utils` (`pdftotext`). `divisas`, `expectativas` y `cot`, `requests pandas`. `empresas` no necesita nada fuera de la biblioteca estándar. `recompras`, `requests` y `poppler-utils`.
- `ofertas` (OPAs desde el registro oficial de la CNMV, indicador 11; PR de la rama `opas-cnmv`): 08:50 y 19:50 de lunes a viernes. La primera vez, una pasada a mano con `--max 300` carga el histórico entero (252 OPAs desde 1998, unos diez minutos); si no, se completa solo en cinco pasadas. Solo `requests`. Carpeta `ofertas` en la lista blanca de nginx. No confundir con `opas` (BME), que el script rechaza.
- nginx sirve `$ESPEC_DATOS_DIR` con lista blanca de carpetas: al añadir un colector hay que añadir su carpeta (hecho para estres, prima y ahorro el 17/11; pendientes `agenda`, fusionada el 18/11, `directivos`, PR #94, `divisas`, PR #95, `expectativas`, PR #96, `cot`, PR #98, `empresas`, PR #101, y `recompras`, PR #99). `agenda` lee las salidas de `letras/` y `bonos/` de la misma carpeta (`datos/proximas_subastas.csv`).
- `calendario` (calendario de dividendos del IBEX 35, indicador 11; PR de la rama `calendario-dividendos`): al minuto 37 de 06 a 23, todos los días, media hora después de cada pasada de `cnmv`. No descarga nada: lee `cnmv/datos/dividendos.csv` e `ibex35.csv` de la misma carpeta, que solo existen desde que `cnmv` pasa con la PR #111; antes de eso se para sin publicar y abre la incidencia `calendario-fallido`. Por eso, primero la #111 y su primera pasada, después la línea del cron. Solo biblioteca estándar. Carpeta `calendario` en la lista blanca de nginx.
- Vuelta atrás: copias del traspaso en `/home/smpro/respaldo/*antes-traspaso-20261117-2054*` (crontab, tar de `/var/www/datos`, nginx, pip freeze); registro del traspaso en `/home/smpro/respaldo/traspaso-20261117.log`; la instalación anterior (`/home/smpro/apps/colectores`, `/home/smpro/bin/colector.sh`) se conserva sin uso.
