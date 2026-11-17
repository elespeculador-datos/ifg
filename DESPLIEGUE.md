# Despliegue: GitHub como fuente de verdad, ejecución en el servidor

Acordado entre Datos y el proyecto IFG el 17/11/2026, pendiente de que Federico lo autorice.

- **El código vive en `main` de GitHub.** Todo cambio entra por rama y PR; el servidor `smpro-datos-1` no lleva commits propios. Lo que hoy solo está en el servidor (8343add, 415cff2, cnmv/dividendos_cnmv.py, e53b063, 4e4b23b) entra en `main` por PR antes de pasar el servidor a `main`.
- **Los datos no van en el git del servidor.** Cada colector escribe su salida en su propia carpeta de datos (fuera del árbol del repositorio o ignorada por git), que es la que sirve `https://datos.elespeculador.com/<colector>/`. Así `git pull` nunca choca.
- **La dirección pública de cada salida es configurable** con la variable de entorno `ESPEC_DATOS_BASE` (siempre con barra final o sin ella; el código la normaliza):
  - sin variable: `https://elespeculador-datos.github.io/ifg/` (GitHub Pages, valor histórico);
  - en el servidor: `ESPEC_DATOS_BASE=https://datos.elespeculador.com/`.
  La variable solo cambia las direcciones que el colector escribe en sus propias salidas (enlaces de los fragmentos, `contentUrl` del marcado Dataset de JSON-LD y `ultima.json`). No cambia dónde se escribe en disco: eso lo fija `--salida`.
- **Las Actions de GitHub quedan desactivadas** mientras la ejecución esté en el servidor; se conservan como documentación del horario y de las dependencias de cada colector. GitHub Pages deja de ser la dirección de lectura de los escenarios de Make: los DIARIO y ARCHIVO 1 pasan a leer `datos.elespeculador.com`.
