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
- Cada pasada: `servidor/ejecutar.sh <colector>`. Trae `main` con avance rápido, ejecuta el colector escribiendo en `$ESPEC_DATOS_DIR/<colector>`, deja el estado de la pasada en `$ESPEC_DATOS_DIR/estado/<colector>.json` (público: lo pueden leer el Mapa de sistemas y los escenarios de Make) y abre, comenta o cierra la incidencia `<colector>-fallido` en GitHub con `servidor/avisar.sh`. Registro en `$ESPEC_DATOS_DIR/registro/<colector>-AAAA-MM-DD.log` (nginx no sirve `/registro/`: los registros no son públicos). Los `estado/colector-*.json` del envoltorio anterior (`/home/smpro/bin/colector.sh`) ya no se actualizan y se retiran.
- `git pull` es anónimo porque el repositorio es público; si pasara a privado, el checkout de los colectores necesitaría una clave de despliegue de solo lectura.
- `opas`, `dividendos` e `ibex` no se ejecutan (API de BME sin licencia, P3); el script lo rechaza.
- Antes de la primera pasada de un colector nuevo, copiar sus datos actuales a `$ESPEC_DATOS_DIR/<colector>/` si los tiene (cortos y cnmv leen su publicación anterior para calcular los cambios). `ahorro` rellena el euríbor del BOE con `python ahorro/ahorro.py --salida $ESPEC_DATOS_DIR/ahorro --meses-atras 36` (hecho el 17/11).
- Crontab del usuario `smpro`, **en hora de Madrid** (el cron del servidor no admite `CRON_TZ`; las fuentes de todos los colectores publican en hora peninsular, así que la hora local es la que conviene, y en verano todo sigue a la misma hora local). Equivalencias: cortos 19:40 y 20:40 L-V y 06:00 M-S; cnmv al minuto 7 de 06 a 22 L-V; letras 13:30; bonos 13:40; accionistas 06:45 M-S; estres 12:20; prima 14:10 (después de letras y bonos, para que el pulso del Tesoro lleve la subasta del día); ahorro lunes 08:30; agenda todos los días 06:20 (la semana nueva aparece el lunes; el escenario de Make la copia entre las 06:45 y las 08:30).

```
40 19 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
40 20 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
0  6  * * 2-6  /home/smpro/colectores-main/servidor/ejecutar.sh cortos
7  6-22 * * 1-5 /home/smpro/colectores-main/servidor/ejecutar.sh cnmv
30 13 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh letras
40 13 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh bonos
45 6  * * 2-6  /home/smpro/colectores-main/servidor/ejecutar.sh accionistas
20 12 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh estres
10 14 * * 1-5  /home/smpro/colectores-main/servidor/ejecutar.sh prima
30 8  * * 1    /home/smpro/colectores-main/servidor/ejecutar.sh ahorro
20 6  * * *    /home/smpro/colectores-main/servidor/ejecutar.sh agenda
```

- Dependencias de Python en el entorno virtual: `pandas xlrd python-calamine requests openpyxl certifi numpy scipy` (con `constraints` del `pip freeze` del servidor) y el paquete del sistema `poppler-utils` (letras y bonos leen PDF). `prima` y `ahorro` solo necesitan `requests pandas numpy scipy`; `agenda`, solo `requests` (y `zoneinfo`, de la biblioteca estándar desde Python 3.9).
- nginx sirve `$ESPEC_DATOS_DIR` con lista blanca de carpetas: al añadir un colector hay que añadir su carpeta (hecho para estres, prima y ahorro el 17/11; pendiente `agenda`, fusionada el 18/11). `agenda` lee las salidas de `letras/` y `bonos/` de la misma carpeta (`datos/proximas_subastas.csv`).
- Vuelta atrás: copias del traspaso en `/home/smpro/respaldo/*antes-traspaso-20261117-2054*` (crontab, tar de `/var/www/datos`, nginx, pip freeze); registro del traspaso en `/home/smpro/respaldo/traspaso-20261117.log`; la instalación anterior (`/home/smpro/apps/colectores`, `/home/smpro/bin/colector.sh`) se conserva sin uso.
