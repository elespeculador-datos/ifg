# Despliegue: GitHub como fuente de verdad, ejecución en el servidor

Acordado entre Datos y el proyecto IFG el 17/11/2026, pendiente de que Federico lo autorice.

- **El código vive en `main` de GitHub.** Todo cambio entra por rama y PR; el servidor `smpro-datos-1` no lleva commits propios. Lo que hoy solo está en el servidor (8343add, 415cff2, cnmv/dividendos_cnmv.py, e53b063, 4e4b23b) entra en `main` por PR antes de pasar el servidor a `main`.
- **Los datos no van en el git del servidor.** Cada colector escribe su salida en su propia carpeta de datos (fuera del árbol del repositorio o ignorada por git), que es la que sirve `https://datos.elespeculador.com/<colector>/`. Así `git pull` nunca choca.
- **La dirección pública de cada salida es configurable** con la variable de entorno `ESPEC_DATOS_BASE` (siempre con barra final o sin ella; el código la normaliza):
  - sin variable: `https://elespeculador-datos.github.io/ifg/` (GitHub Pages, valor histórico);
  - en el servidor: `ESPEC_DATOS_BASE=https://datos.elespeculador.com/`.
  La variable solo cambia las direcciones que el colector escribe en sus propias salidas (enlaces de los fragmentos, `contentUrl` del marcado Dataset de JSON-LD y `ultima.json`). No cambia dónde se escribe en disco: eso lo fija `--salida`.
- **Las Actions de GitHub quedan desactivadas** mientras la ejecución esté en el servidor; se conservan como documentación del horario y de las dependencias de cada colector. GitHub Pages deja de ser la dirección de lectura de los escenarios de Make: los DIARIO y ARCHIVO 1 pasan a leer `datos.elespeculador.com`.

## Servidor smpro-datos-1: cómo se ejecutan los colectores

- Entorno en `/etc/smpro/entorno` (plantilla en `servidor/entorno.ejemplo`): `ESPEC_DATOS_DIR` (carpeta que sirve datos.elespeculador.com, fuera del git; en smpro-datos-1, `/var/www/datos`), `ESPEC_DATOS_BASE`, `SMPRO_PYTHON` (el intérprete del entorno virtual del servidor, `/home/smpro/venv/bin/python`) y `GH_TOKEN` (incidencias).
- El IFG escribe en la misma carpeta (`$ESPEC_DATOS_DIR/ifg/`) desde su propio `ifg-diario.sh`, sin commits en el git del servidor: el checkout de `/home/smpro/ifg` se queda siempre en `main` limpio, que es lo que `ejecutar.sh` exige para su `git pull --ff-only`.
- Cada pasada: `servidor/ejecutar.sh <colector>`. Trae `main` con avance rápido, ejecuta el colector escribiendo en `$ESPEC_DATOS_DIR/<colector>`, y abre, comenta o cierra la incidencia `<colector>-fallido` en GitHub con `servidor/avisar.sh`. Registro en `$ESPEC_DATOS_DIR/registro/<colector>-AAAA-MM-DD.log`.
- `opas`, `dividendos` e `ibex` no se ejecutan (API de BME sin licencia, P3); el script lo rechaza.
- Antes de la primera pasada, copiar los datos actuales de cada colector a `$ESPEC_DATOS_DIR/<colector>/` (cortos y cnmv leen su publicación anterior para calcular los cambios).
- Crontab del usuario que ejecuta los colectores, con las mismas horas que tenían las Actions (en UTC):

```
CRON_TZ=UTC
40 18 * * 1-5  /home/smpro/ifg/servidor/ejecutar.sh cortos
40 19 * * 1-5  /home/smpro/ifg/servidor/ejecutar.sh cortos
0  5  * * 2-6  /home/smpro/ifg/servidor/ejecutar.sh cortos
7  5-21 * * 1-5 /home/smpro/ifg/servidor/ejecutar.sh cnmv
30 12 * * 1-5  /home/smpro/ifg/servidor/ejecutar.sh letras
40 12 * * 1-5  /home/smpro/ifg/servidor/ejecutar.sh bonos
45 5  * * 2-6  /home/smpro/ifg/servidor/ejecutar.sh accionistas
20 11 * * 1-5  /home/smpro/ifg/servidor/ejecutar.sh estres
```

  Si el cron del servidor no admite `CRON_TZ`, se convierten las horas a la zona del servidor. El checkout está en `/home/smpro/ifg` (el mismo que usa `ifg-diario.sh`); el cron corre como el usuario dueño de ese checkout y de `$ESPEC_DATOS_DIR`.
- Dependencias de Python en el servidor: `pandas xlrd python-calamine requests openpyxl certifi numpy scipy` y el paquete del sistema `poppler-utils` (letras y bonos leen PDF).
