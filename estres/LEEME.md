# Estrés financiero de España (indicador 2)

Cada día hábil, a las 11:20 UTC, el servidor smpro-datos-1 (`servidor/ejecutar.sh estres`, ver `DESPLIEGUE.md`) lee del portal de datos del BCE el indicador compuesto de estrés sistémico (CISS) de España, la zona euro, Alemania, Francia e Italia y el CISS soberano de España, Alemania, Francia e Italia, y publica en `$ESPEC_DATOS_DIR/estres/` (https://datos.elespeculador.com/estres/):

- `fragmento-wp.html`: la lectura del día, la comparación con la zona euro y las grandes economías, el estrés soberano, los máximos de cada episodio de referencia y un gráfico SVG de tres años, entre `<!-- estres:inicio HUELLA -->` y `<!-- estres:fin -->`. La huella solo cambia si cambian los datos;
- `index.html`: página propia de la salida;
- `datos/serie.csv` (todas las series, formato largo) y `datos/ultima.json` (resumen versionado, `version` 1.0.0).

Pregunta del lector: ¿hay tensión en el sistema financiero español y cómo estamos frente a 2008, 2012 y 2020?

Fuente y licencia: BCE, portal de datos, conjunto CISS (clave `D.ES+U2+DE+FR+IT.Z0Z.4F.EC.SS_CIN+SOV_CIN.IDX`). Política de reutilización de las estadísticas del SEBC: gratuita, citando la fuente y sin modificar las series; los cálculos propios se declaran. Los cálculos de El Especulador (percentil histórico con definición «débil», variaciones a 1, 4 y 13 semanas, máximo dentro de cada episodio de referencia, última vez igual o mayor sin contar seis meses) se publican con licencia CC BY 4.0.

Reglas: sin predicción; percentiles y tramos describen el presente frente al pasado. Si el portal no responde, el CSV cambia de forma, hay valores fuera de 0-1 o el último dato tiene más de 45 días, el script se para sin publicar y `servidor/ejecutar.sh` abre una incidencia con la etiqueta `estres-fallido`. Con más de 10 días de desfase solo avisa.

La dirección pública que el fragmento y el JSON-LD escriben sale de la variable de entorno `ESPEC_DATOS_BASE` (en el servidor, `https://datos.elespeculador.com/`; sin ella, GitHub Pages, valor histórico). El flujo de GitHub `estres-diario` no tiene horario ni escribe en el repositorio: se lanza a mano para validar una rama con datos reales y deja la salida como artefacto.

Comprobaciones sin red: `python estres/pruebas_estres.py` (32 comprobaciones, con un caso de control contra `scipy.stats.percentileofscore`).

Prueba local con un CSV del portal ya descargado: `python estres/estres.py --salida docs/estres --local ciss.csv --fecha 2026-11-02`. Si la huella no cambia, el script no reescribe nada (así no hay un commit diario por la hora de comprobación); tras cambiar el código o las plantillas, `--forzar` regenera los ficheros.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/estres/fragmento-wp.html` (marcas `estres:inicio`/`estres:fin`), JSON `https://datos.elespeculador.com/estres/datos/ultima.json`; pasada a las 11:20 UTC L-V; hay dato nuevo cuando cambia la huella de la primera línea. Página de WordPress por crear (borrador): /estres-financiero-espana/. El texto pasa por Cumplimiento antes de publicar. Lo que hay en `docs/estres/` es la foto de la validación del 02/11/2026, no se actualiza.
