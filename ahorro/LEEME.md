# Rentabilidad real del ahorro (indicador 4)

Cada lunes a las 07:30 UTC, el servidor smpro-datos-1 (`servidor/ejecutar.sh ahorro`, ver `DESPLIEGUE.md`) junta tres fuentes y publica en `$ESPEC_DATOS_DIR/ahorro/` (https://datos.elespeculador.com/ahorro/):

- `fragmento-wp.html`: la lectura del mes (tipo de los depósitos, inflación y rentabilidad real, con racha y percentil desde 2003), la tabla de referencias (depósitos a la vista y a plazo de España y de la zona euro, euríbor a un año), las Letras a 12 meses como alternativa sin riesgo, un gráfico SVG de la rentabilidad real de los depósitos a plazo desde 2003 y el método, entre `<!-- ahorro:inicio HUELLA -->` y `<!-- ahorro:fin -->`;
- `index.html`: página propia de la salida;
- `datos/serie.csv` (mensual, formato largo: tipos, IPC, euríbor y rentabilidades reales), `datos/ultima.json` (resumen versionado, `version` 1.0.0) y `datos/euribor_boe.csv` (el euríbor acumulado mes a mes con la referencia del BOE de cada dato: es el estado que conserva el colector).

Pregunta del lector: ¿cuánto gana o pierde mi dinero en el banco después de la inflación?

Fuentes y licencias:
- **BCE**, estadísticas de tipos de interés de las IFM (conjunto MIR): tipo medio de los depósitos de los hogares a la vista (saldos vivos) y a plazo hasta un año (nuevas operaciones), España y zona euro, mensual desde 2003. Política de reutilización del SEBC verificada el 02/11/2026.
- **INE**, IPC general nacional, variación anual (API Tempus3, serie `IPC251856`; el script comprueba el nombre de la serie en cada pasada). CC BY 4.0 verificada el 02/11/2026; cita «Elaboración propia con datos extraídos del sitio web del INE: www.ine.es».
- **Banco de España a través del BOE**: euríbor a un año, media mensual, de la resolución mensual «por la que se publican determinados tipos de interés oficiales de referencia del mercado hipotecario», localizada en el sumario de los primeros días de cada mes con la API de datos abiertos del BOE y leída de su XML. Aviso legal del BOE verificado el 02/11/2026 (reutilización comercial y obras derivadas; cita «Basado en datos de la Agencia Estatal Boletín Oficial del Estado»). Así no se toca el euríbor diario de EMMI, que exige licencia.
- **Tesoro**: tipo marginal de la última subasta de Letras a 12 meses, reproducido de `letras/datos/ultima.json` si está al lado de la salida (o en la carpeta de `--tesoro`); si no está, el bloque no se publica.

Método: rentabilidad real = (1 + tipo) ÷ (1 + inflación) − 1, con el tipo y el IPC del mismo mes (el último mes en que las dos fuentes tienen dato); percentil «débil» desde 2003; racha de meses con el mismo signo; mejor y peor mes; variación del tipo a doce meses. La comparación de las Letras usa el último IPC publicado y se declara ilustrativa. Sin predicción ni recomendación.

Reglas: si una fuente no responde, cambia de forma, la serie del INE no se llama como debe, hay valores fuera de rango o el último mes común tiene más de 150 días, el script se para sin publicar y `servidor/ejecutar.sh` abre la incidencia `ahorro-fallido`. Pasados 75 días solo avisa. Si el euríbor del BOE no se encuentra, el bloque no se publica y se avisa (el resto sí). La dirección pública sale de `ESPEC_DATOS_BASE`.

Comprobaciones sin red: `python ahorro/pruebas_ahorro.py` (54 comprobaciones con datos simulados: lectura de las tres fuentes y paradas, búsqueda y lectura de la resolución del BOE, acumulación del euríbor, fórmula de Fisher, caso de control del percentil contra scipy, rachas, escritura sin reescritura).

Primera pasada en el servidor: `python ahorro/ahorro.py --salida $ESPEC_DATOS_DIR/ahorro --meses-atras 36` rellena tres años de euríbor del BOE (unas cuatro llamadas al sumario por mes); las pasadas siguientes solo buscan el mes anterior. Prueba local con respuestas ya descargadas: `--local carpeta` con `mir.csv`, `ipc_meta.json`, `ipc.json` y `euribor.csv`. El flujo de GitHub `ahorro-validacion` no tiene horario ni escribe en el repositorio: se lanza a mano para validar una rama con datos reales y deja las respuestas y la salida como artefacto.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/ahorro/fragmento-wp.html` (marcas `ahorro:inicio`/`ahorro:fin`), JSON `https://datos.elespeculador.com/ahorro/datos/ultima.json`; pasada semanal (lunes 07:30 UTC); hay dato nuevo cuando cambia la huella de la primera línea. Página de WordPress por crear (borrador): /rentabilidad-real-del-ahorro/. El texto pasa por Cumplimiento antes de publicar.
