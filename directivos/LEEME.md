# Compras y ventas de directivos (indicador 10)

Cada día a las 07:10 (hora de Madrid, lunes a sábado), el servidor smpro-datos-1 (`servidor/ejecutar.sh directivos`, ver `DESPLIEGUE.md`) lee el registro público de la CNMV de notificaciones de operaciones de administradores, directivos y personas vinculadas (artículo 19 del Reglamento (UE) 596/2014; formulario del Reglamento de Ejecución (UE) 2016/523) y publica en `$ESPEC_DATOS_DIR/directivos/` (https://datos.elespeculador.com/directivos/):

- `fragmento-wp.html`: lectura de las últimas 13 semanas (compras y ventas discrecionales, proporción de compras y, cuando haya un año de serie, su percentil), las empresas con más compra y más venta neta, las notificaciones de los últimos 30 días (sin nombres, con enlace a cada notificación oficial), el mes anterior en conjunto y el método, entre `<!-- directivos:inicio HUELLA -->` y `<!-- directivos:fin -->`;
- `resumen-mensual.html`: un párrafo con el agregado del mes anterior, sin empresas: el anzuelo gratuito (el detalle por empresa es la parte premium, según la decisión de Federico del 18/11/2026);
- `index.html`: página propia de la salida;
- `datos/ultima.json` (versión 1.0.0), `datos/operaciones.csv` (todas las operaciones leídas: estado del colector), `datos/serie_semanal.csv`, `datos/cobertura.json` (tramo del registro ya leído) y `datos/pendientes.csv` (notificaciones cuyo PDF no se pudo leer; se reintentan hasta cinco veces).

Pregunta del lector: ¿están comprando o vendiendo acciones de su propia empresa quienes mejor la conocen, y en qué empresas?

## Fuente y licencia

CNMV, «Notificaciones de los directivos y personas vinculadas» (https://www.cnmv.es/portal/consultas/directivos-consulta). El listado se consulta por fechas con `directivos-resultado.aspx?fechad=dd/mm/aaaa&fechah=dd/mm/aaaa&page=N` (diez notificaciones por página) y cada notificación es un PDF con el formulario estándar europeo, que se lee con `pdftotext -layout`. Nota legal de la CNMV verificada el 02/11/2026: reproducción fiel, cálculos derivados permitidos; si la información entra en un producto de pago hay que decir al comprador, antes de pagar y en cada entrega, que es gratuita en cnmv.es.

**Datos personales**: el colector no guarda el nombre del declarante ni su cargo literal. De cada notificación conserva el emisor (nombre, NIF, LEI), el motivo (persona con responsabilidad de dirección o persona estrechamente vinculada), un tipo de cargo (consejero, directivo o persona vinculada, deducido del cargo), las filas de operaciones (ISIN, instrumento, operación, fecha, lugar, volumen, precio, divisa), si es una modificación, el texto de «otra información» recortado a 300 caracteres y el enlace al documento público. Revisado por Cumplimiento por diseño el 18/11/2026.

## Método

- **Discrecional**: compra o venta de acciones (no derechos, opciones ni otros derivados) en un centro de negociación (el lugar no es «fuera de un centro de negociación», XOFF ni XXXX) y cuya notificación no atribuye la operación a un plan de retribución, incentivos o compra para empleados (palabras clave en «otra información» y en la naturaleza de la operación: entrega, ejercicio, canje, permuta). Herencias, donaciones, préstamos, pignoraciones y suscripciones en ampliaciones se guardan como «otro». El criterio está en el código (`_tipo_operacion`) y en la página.
- **Modificaciones**: una notificación marcada como modificación sustituye a la inicial del mismo emisor cuando repite sus filas (mismo ISIN, fecha, volumen y precio, registrada en los 90 días anteriores); la inicial queda marcada `sustituida` y fuera de los cálculos. Caso real: Puig, registros 2026140993 (compra) y 2026141576 (modificación: venta).
- **Importes**: volumen por precio, solo en euros; las operaciones en otra divisa cuentan en número pero no en euros.
- **Ventana**: 13 semanas por empresa (compras, ventas, neto, tipos de cargo, última operación). **Serie semanal** (semanas de lunes) con compras, ventas, euros, neto y proporción de compras (compras sobre compras más ventas, en número). **Percentil** de la proporción a 13 semanas frente a todas las ventanas anteriores, «débil» (porcentaje de ventanas con valor igual o inferior), solo con 52 ventanas anteriores, es decir, 65 semanas de serie; caso de control contra `scipy.stats.percentileofscore(kind="weak")`.
- **Relleno del histórico**: cada pasada relee los últimos 21 días (las notificaciones se registran con retraso) y, si queda registro por leer hacia atrás hasta el 1 de mayo de 2018, sigue en tramos de 45 días hasta 300 PDF por pasada (unos 0,7 s entre peticiones). El registro completo, unas 8.000 notificaciones, se termina en un mes de pasadas sin tocar nada.
- **Por sector** (versión 1.1.0): compras, ventas, euros, neto, empresas y proporción de compras de las 13 semanas y del mes anterior por sector, con la clasificación propia de El Especulador (`cortos/sectores.csv`, ocho sectores por la actividad declarada de cada empresa; `cortos/sectores.py`). Los emisores que no están en la tabla se agregan como «sin sector» y abren aviso (`::warning::`), no incidencia. Si la tabla no está, el agregado no se publica y lo demás no cambia. El resumen mensual (anzuelo gratuito) añade el sector con más compra neta y el de más venta neta del mes.
- Sin predicción ni recomendación: «describe lo que han hecho, no lo que hará la acción».

## Reglas

Si la CNMV no responde en el tramo reciente, el script se para sin publicar y `servidor/ejecutar.sh` abre la incidencia `directivos-fallido`; si falla un tramo del relleno, se deja para otra pasada y se avisa. Un PDF que no se puede leer va a `pendientes.csv` con su motivo y se reintenta; una notificación sin filas legibles se anota en `cobertura.json` (`sin_operaciones`) y no se vuelve a bajar. Sin cambios de huella (operaciones, ventana actual, semana) no se reescribe nada; `--forzar` regenera.

## Comprobaciones sin red

`python directivos/pruebas_directivos.py`: 92 comprobaciones con el formato real del listado y del PDF (lector del listado sin nombres, lector del PDF con una y varias filas y con el recurso al total agregado, números con punto de miles, clasificación de 16 casos, recogida con estado en tres pasadas, tope de documentos y cobertura, modificaciones que sustituyen, tramos del relleno, serie semanal, ventana de 13 semanas, percentil contra scipy, huella, fragmento, resumen mensual, JSON, CSV).

Validado con datos reales el 18/11/2026 (flujo `directivos-validacion`, ejecución 44387103652, 60 PDF de los últimos 21 días): 102 líneas, 82 discrecionales, 0 PDF fallidos, 1 notificación sin filas legibles; las trece semanas dieron 55 compras y 26 ventas discrecionales (68 % compras), 3,70 millones comprados y 4,96 vendidos; detectada y corregida la doble cuenta de una modificación (Puig). Verificado sobre el dato, no estimado.

## Entrega a Tecnología

Fragmento `https://datos.elespeculador.com/directivos/fragmento-wp.html` (marcas `directivos:inicio`/`directivos:fin`), resumen `https://datos.elespeculador.com/directivos/resumen-mensual.html`, JSON `https://datos.elespeculador.com/directivos/datos/ultima.json`; pasada diaria 07:10 L-S; dato nuevo cuando cambia la huella de la primera línea. Página de WordPress en borrador: /compras-y-ventas-de-directivos/. Dependencias: `requests` y `poppler-utils` (ya en el servidor para letras y bonos).

- **1.1.2 (27/11/2026)**: la nota de método decía «solo se publica con al menos 52 semanas de serie», y el aviso de la cabecera, «cuando la serie tenga 65 semanas completas». Lo correcto es lo segundo: el percentil compara la ventana de 13 semanas con al menos 52 ventanas anteriores, así que hacen falta 65 semanas de serie. La nota lo dice ahora así. No cambia ningún dato.
- **1.1.1 (25/11/2026)**: la serie semanal y el percentil empiezan en el primer lunes con el registro de la CNMV ya leído (`cobertura.desde`), salvo que el registro esté completo desde 2018. Antes, la serie arrancaba en la primera operación notificada (junio de 2025) y las semanas anteriores a la lectura, casi vacías (solo notificaciones tardías), entraban en la comparación: el percentil publicado (39) no era válido. Con el registro leído desde el 21/03/2026, el percentil se publicará cuando haya 65 semanas completas. La cabecera dice desde cuándo está leído el registro, y los importes en otra divisa salen a la española («12.100 × 215,90 MXN»).
