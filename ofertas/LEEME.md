# OPAs desde el registro de la CNMV (indicador 11, segunda parte)

Dos veces cada día hábil, a las 08:50 y a las 19:50 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh ofertas`, ver `DESPLIEGUE.md`) lee el registro oficial de OPAs de la CNMV y publica en `$ESPEC_DATOS_DIR/ofertas/` (https://datos.elespeculador.com/ofertas/):

- `fragmento-wp.html`: frase del día, OPAs en marcha (presentadas y pendientes de autorización; autorizadas sin resultado), OPAs por año y todas las OPAs desde 2015, entre `<!-- opas:inicio HUELLA -->` y `<!-- opas:fin -->`, las mismas marcas que la página 8588 (/opas-bolsa-espanola/);
- `index.html`: página propia de la salida;
- `datos/opas.csv` (una OPA autorizada por fila; es también la memoria del colector), `datos/presentadas.csv` y `datos/ultima.json` (versión 1.0.0).

Pregunta del lector: ¿qué OPAs hay en marcha sobre empresas españolas cotizadas, en qué condiciones, y cómo acabaron las anteriores?

Sustituye, con una fuente con licencia, al registro de BME de /opas-bolsa-espanola/ (8588), congelado desde el 21/10/2026 porque la API de BME no tiene licencia de uso (P3 del catálogo, riesgo A). El colector `opas` (BME) no se ejecuta; este se llama `ofertas` para no confundirse con él.

## Fuente y licencia

CNMV, registro oficial de OPAs (Real Decreto 1066/2007), en línea desde 1998:

- `https://www.cnmv.es/portal/Consultas/Folletos/ListaOPAS?fechaDesde=01/01/1998&fechaHasta=<hoy>`: OPAs presentadas y pendientes de autorización, y autorizadas con su número de registro oficial (252 el 22/11/2026, del 180 al 431);
- `opa.aspx?numReg=N&vista=0`: tipo de OPA, valores afectados, contraprestación, volumen, calendario (autorización, plazo de aceptación, prórroga, desistimiento) y observaciones;
- `opa.aspx?numReg=N&vista=2`: resultado (positivo o negativo), fecha de publicación y aceptaciones (% OPA, coeficiente de prorrateo).

Nota legal de la CNMV leída el 02/11/2026 (catálogo, fuentes): uso no privado autorizado con reproducción fiel, sin alterar contenidos; cálculos derivados permitidos y difundibles; en productos de pago, avisar de que la información es gratis en cnmv.es. Es el sustituto de P3 que preveía el inventario de fuentes («OPAs → folletos de OPAs del registro de la CNMV»). La selección y las tablas son de El Especulador (CC BY 4.0).

## Método

1. Cada pasada pide el listado completo (una petición) y, como mucho, 60 fichas (dos peticiones cada una, medio segundo entre peticiones), por este orden: las OPAs autorizadas que siguen abiertas (sin resultado ni desistimiento), las nuevas de la más reciente a la más antigua y las resueltas hace menos de 45 días (una vez al día, por si la CNMV corrige algo). El histórico entero se carga en cinco pasadas, o en una con `--max 300`.
2. Situación de cada OPA autorizada: resultado positivo o negativo (el de la CNMV), desistida (con fecha; o, con el plazo ya terminado, cuando solo lo dicen las observaciones de la CNMV, como en Applus 413), autorizada con el plazo por empezar, en plazo de aceptación (el último día cuenta; la prórroga manda sobre el plazo inicial), plazo terminado con el resultado pendiente (hasta 30 días después) o «sin resultado en el registro de la CNMV» (más de 30 días después sin resultado: pasa en siete OPAs antiguas, de 2001 a 2017, cuya pestaña de resultado está vacía; no son OPAs en marcha).
3. Aceptación = «% OPA» de la CNMV: la parte de los valores a los que se dirigía la oferta que acudió; en una oferta parcial con prorrateo puede pasar del 100 % y se dice.
4. Contraprestación tal como la registra la CNMV («3,510 Euros por acción» → «3,510 € por acción»). Si la OPA se modificó, vale la de la última modificación y se dice la inicial (Applus 413: 10,650 €, la inicial era 9,500 €). Si es un canje o tiene condiciones («*» en el registro), la casilla enlaza con la ficha de la CNMV.
5. Oferentes: los que son entidades, tal como los nombra la CNMV; uno solo igual a la sociedad, «La propia sociedad». **Las personas físicas no se guardan ni se publican**: se cuenta cuántas hay («y 1 persona física»). Es entidad lo que reconoce la regla del colector de accionistas (`accionistas/duenos.py`, `persona_juridica`), lo que lleva una forma o palabra de sociedad que esa regla no recoge (`OTRAS_ENTIDADES`: AKTIENGESELLSCHAFT, COMPAGNIE, SGPS, LDA, SEC, BIDCO…) y cualquier nombre de una sola palabra. Con el registro entero del 22/11/2026, la regla de accionistas sola dejaba fuera a siete oferentes, seis de ellos sociedades (Hochtief Aktiengesellschaft en Abertis; cuatro sociedades francesas en Centros Comerciales Carrefour; una SGPS portuguesa en Banco Finantia); con la ampliación queda fuera uno, la persona física de Corporación Financiera Alba (421). Un nombre dudoso cuenta como persona física: queda oculto, que es el lado seguro.
6. OPAs por año (de autorización), solo cuando el histórico está completo; mientras se carga, la página lo dice («Histórico en carga: N de M»).
7. Versión del lector (`LECTOR`, en `datos/opas.csv`): si cambia, las fichas leídas con el anterior se releen al final de la cola, dentro del máximo por pasada.

## Reglas

- Si el listado no trae la tabla de autorizadas o una ficha no trae su cabecera con su número, la CNMV ha cambiado la página: `::error::ofertas`, código 1, incidencia `ofertas-fallido` y no se publica nada nuevo. Si una ficha no responde, se reintenta en la pasada siguiente (aviso); si no responde ninguna de tres o más, error.
- `datos/opas.csv` se escribe en cada pasada (es la memoria). Lo publicado solo se reescribe si cambia la huella (datos de todas las OPAs, situación del día, presentadas y cobertura) o si falta algún fichero; `--forzar` regenera.
- Sin precios de mercado, rentabilidades ni recomendación; contenido informativo y educativo.

## Comprobaciones

`python ofertas/pruebas_ofertas.py`: 50 comprobaciones sin red con páginas reales de la CNMV del 22/11/2026, recortadas a la parte con datos (`ofertas/pruebas_ofertas/`: listado de 2025-2026 y fichas de Ercros 431, Banco Sabadell 426, CIE Automotive 424, Corporación Financiera Alba 421, con el nombre de la persona física sustituido por uno ficticio, y Applus 413), más casos simulados (en plazo, por empezar, plazo terminado, sin resultado en el registro, desistida, prorrateo), oferentes extranjeros, prioridades de lectura y relectura, memoria, huella, escritura, paradas, línea de órdenes y un caso de control con pandas (recuento por año y resultado).

## Validación con datos reales (22/11/2026)

Registro entero leído de la CNMV (504 páginas de ficha, nueve minutos): **252 OPAs autorizadas desde 1998** (números 180 a 431): 228 con resultado positivo, 6 negativo, 11 desistidas (diez con fecha de desistimiento y Applus 413 por las observaciones) y 7 sin resultado en el registro (de 2001 a 2017). 22 se modificaron (en 17 cambia la contraprestación); 6 son canjes o tienen condiciones y enlazan con la ficha. **2 presentadas y pendientes de autorización**: Aedas Homes (Neinor DMP Bidco, 17/11/2026) y Azkoyen (Ohmnia Electronics, 24/08/2026). Ninguna en plazo de aceptación. Última resuelta: Ercros (Bondalti Iberica), positiva, 37,86 % de los valores a los que se dirigía, publicada el 17/09/2026. Una sola persona física entre los oferentes (Corporación Financiera Alba, 421), sin nombre. Fragmento de 25.500 caracteres. Verificado sobre el dato, no estimado.

Control con una fuente independiente, solo para comprobar (no se publica nada de BME): la copia del registro de BME que El Especulador publicaba hasta el 06/11 (en git, `1bff992^:docs/opas/datos/opas.csv`). De sus 96 OPAs con plazo desde 2008, 84 tienen en la CNMV una OPA con el mismo inicio de plazo; 4 más son la misma OPA con otra fecha de inicio (Árima, Applus por Amber, Funespaña y Aigües de Sabadell), y 8 son valores de Latibex o de BME Growth, que no pasan por el registro de la CNMV. En las 72 que casan también por nombre, el resultado coincide salvo en cuatro que BME tenía y el registro de la CNMV no (Sotogrande 2017, FCC 2016, Jazztel 2015 y Realia 2015, retirada según BME); Abertis 2017 es «retirada» en BME y desistida en la CNMV, lo mismo. La aceptación coincide salvo en nueve: la CNMV la mide sobre los valores a los que se dirigía la oferta y BME, en esas, sobre otra base (Catalana Occidente 2025: 94,27 % en la CNMV, 35,79 % en BME, que es el 94,27 % del 37,97 % del capital al que se dirigía) o sin el prorrateo de las parciales (Abertis 2016: 739,97 % en la CNMV).

## Entrega a Tecnología

- Fragmento: `https://datos.elespeculador.com/ofertas/fragmento-wp.html` (marcas `opas:inicio` / `opas:fin`, las de 8588).
- JSON: `https://datos.elespeculador.com/ofertas/datos/ultima.json`; CSV: `datos/opas.csv` y `datos/presentadas.csv`.
- Pasadas: 08:50 y 19:50 de lunes a viernes. Dato nuevo: cambia la huella de la primera línea.
- Página en borrador: 9496 (`/opas-registro-cnmv/`), creada el 22/11/2026. Escenario de Make 10212340 (DIARIO, inactivo hasta que el servidor sirva `/ofertas/`; cada hora de 09:00 a 10:30 y de 20:00 a 21:30, de lunes a viernes). Propuesta a Federico: sustituir el contenido de 8588 por el del borrador (misma dirección) y apuntar el escenario a 8588.
- Dependencias: `requests` (y la regla de `accionistas/duenos.py` del mismo repositorio).
