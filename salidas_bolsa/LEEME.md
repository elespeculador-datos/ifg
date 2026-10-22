# Salidas a bolsa en España desde 2000

Registro de todas las empresas que empezaron a cotizar en el mercado continuo (SIBE) con una oferta pública de acciones (OPV, OPS o mixta) desde el 1/1/2000, y qué ha sido de cada una. Página: https://elespeculador.com/salidas-a-bolsa-espana/ (página 8656 de WordPress).

La carpeta se llama `salidas_bolsa/` y no `salidas/` porque `.gitignore` ignora cualquier carpeta `salidas/` (ahí van los gráficos locales).

## Ficheros

- `registro.csv`: el registro, curado a mano. Una fila por salida, cada una con su fuente (`fuente_salida`, y `fuente_exclusion` si ya no cotiza; varias URL separadas por « | »). Es la única parte que se edita a mano, con `descartadas.csv`.
- `descartadas.csv`: admisiones en el SIBE que no son salidas con oferta (traslados desde BME Growth, escisiones, listados directos, admisiones tras una fusión, ofertas de empresas que ya cotizaban, salidas al MAB), con el motivo. Sirve para que el flujo no vuelva a avisar de ellas y se publica tal cual en los datos abiertos.
- `salidas.py`: cada día hábil (flujo `salidas-bolsa-diario`, 17:45 UTC) comprueba en la API de BME qué empresas siguen en el SIBE, si hay admisiones nuevas y los precios de las salidas de los últimos cinco años, y publica `docs/salidas_bolsa/` solo si cambia algo.
- `plantilla-wp.html`: el texto fijo de la página de WordPress; `[[BLOQUE]]` es donde va `docs/salidas_bolsa/fragmento-wp.html`. El escenario de Make 10021282 copia cada día el bloque entre `<!-- salidas:inicio` y `<!-- salidas:fin -->` y solo escribe si ha cambiado.

## Columnas del registro

- `fecha_primera_sesion`, `fecha_exclusion`: `AAAA-MM-DD`; si la fuente no da más, `AAAA-MM` o `AAAA`, y la página lo muestra así («octubre de 2000», «2005»). La de exclusión es el último día en que cotizó.
- `precio_salida_eur`, `importe_oferta_meur`: vacíos si no hay fuente pública que los confirme (la página pone «—»). El importe es el de la oferta sin el *green shoe*, salvo que `importe_con_green_shoe` sea `true` porque consta que se ejerció.
- `precio_fuente_unica`: `true` si el precio solo tiene una fuente pública (la página lo marca con ‡).
- `estado_hoy`: `cotiza` o `excluida`. Lo que publica la página sale de BME (ver abajo). `nota_hoy` se añade a «Cotiza» (por ejemplo, una OPA ya liquidada con la exclusión pendiente).
- `motivo_exclusion`: `OPA de exclusión`, `OPA`, `fusión o absorción`, `concurso o liquidación`, `exclusión a petición propia sin OPA` u `otro`. Cualquier otro valor hace fallar el flujo, a propósito. Una exclusión sin `fuente_exclusion` también.

## Qué no hace solo

- **El estado de hoy sale de BME, no del registro.** Si una empresa que el registro da por cotizada desaparece de la lista del SIBE, la página dice «ya no está en el SIBE (por confirmar)» y el flujo abre una incidencia `salidas-revisar`: hay que completar a mano la fecha y el motivo de la exclusión, con su fuente.
- **Una salida nueva no se añade sola.** Cuando BME registra una admisión nueva en el SIBE que no está ni en `registro.csv` ni en `descartadas.csv`, el flujo abre una incidencia `salidas-revisar`. Se añade a mano con el precio y el importe del folleto o de la comunicación de la empresa a la CNMV.
- **La variación desde la salida solo se calcula para los últimos cinco años**, que es lo que guarda el histórico de precios de BME, y solo de precio (sin dividendos). Si BME marca un ajuste de capital (split, contrasplit, ampliación con derechos) después de la salida, no se calcula.

## Cómo se hizo

El registro de 2026-10-22 sale del registro de ofertas públicas de BME (sistema 02, mercado continuo), contrastado fila a fila con folletos y hechos relevantes de la CNMV, informes anuales y prensa, y revisado después por separado: dos importes corregidos (Aena e Iberdrola Renovables, con el *green shoe* ejercido), huecos rellenados y los datos sin confirmar dejados en blanco.

## Licencia

El registro es de El Especulador y se puede reutilizar citándolo. Los precios de cotización son de BME y se rigen por sus condiciones.
