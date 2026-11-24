# Ficha integrada por empresa (indicador 16)

Pregunta del lector (en la ficha de cada empresa del IBEX 35): ¿qué está pasando con esta empresa que no sale en la cotización: qué ha comunicado a la CNMV, qué dividendos ha anunciado, quién apuesta en contra, si compran o venden sus directivos, quién manda en el capital y si está recomprando?

Estado: **contrato 1.0 con el chat de fichas de Tecnología (21/11/2026; encargo formal del 22/11), versión 1.2.0 (24/11/2026)**. Funciona con las fuentes que ya sirve el servidor (cnmv, cortos, accionistas filtrado) y completa `directivos` cuando se despliegue su colector. Sin nada de BME (ni dividendos, ni rentabilidades, ni precios).

## Contrato 1.0 (Datos ↔ chat «Fichas de valores», 21/11/2026)

Datos **no toca las páginas** `/ibex35/<empresa>/` (hijas de la 8258) ni los fragmentos del chat de fichas: el chat de fichas pinta los datos al mostrar la página, leyendo de `datos.elespeculador.com`, con caché y la fecha del dato. Datos publica en el servidor:

- `empresas/<ISIN>.json`: una ficha por empresa del IBEX 35 (35 archivos; `cnmv/empresas.csv` fija el universo y la dirección de la ficha). Para un ISIN sin archivo (hoy, DAX y EE. UU.) la respuesta es 404: la ficha oculta los bloques.
- `empresas/indice.json`: `comprobado` (fecha de la última pasada, se escribe en cada una), `fuentes` y, por empresa, la huella y la dirección del JSON. Comparando huellas basta con releer lo que cambia.
- `empresas/eventos.json`: todos los eventos con fecha entre hoy−30 y hoy+30 días, del más reciente al más antiguo, con su tipo.
- `empresas/cambios.csv`: registro de cambios de cada cifra (fecha, ISIN, empresa, campo, antes, después, fuente), solo con datos; se añade al final.
- `empresas/index.html`: página propia con el resumen.

Campos de cada `<ISIN>.json`:

| Campo | Contenido | Fuente |
|---|---|---|
| `contrato`, `version` | `"1.0"` (cambia solo si cambian los campos) y versión del colector | — |
| `empresa`, `isin`, `ficha` | nombre corto, ISIN (la clave común con el registro de valores de Tecnología) y dirección de la ficha | `cnmv/empresas.csv` |
| `actualizado` | fecha de la pasada en que cambió algún dato de esta ficha | — |
| `registro_oficial` | comunicados a la CNMV de doce meses (resultados, dividendos, recompras, ampliaciones y OPVs, OPAs): `fecha`, `tipo`, `titulo` (tal como lo publica la CNMV), `fuente`, `enlace`, `nreg`, `grupo` (los de una misma operación comparten grupo). En `fuentes.registro_oficial`: `alcance` (qué comunicados entran) y `desde` (desde qué fecha está completo: doce meses cuando el colector `cnmv` termina su relleno hacia atrás) | colector `cnmv` |
| `dividendos` | anuncios de dividendo comunicados a la CNMV en doce meses: `fecha_comunicado`, `tipo`, `titulo`, `importe` (bruto por acción), `moneda`, `fecha_ex`, `fecha_registro`, `fecha_pago`, `lectura`, `fuente`, `enlace`, `nreg`. **Sin rentabilidad.** Importe, moneda y fechas leídos del PDF del propio comunicado por `cnmv/dividendos_cnmv.py` solo cuando se leen con seguridad (`lectura`: «leído del comunicado», «parcial: el resto, en el comunicado», «dividendo flexible…», «sin leer: ver el comunicado»); lo que no se lee va vacío y la ficha enlaza el comunicado | colector `cnmv` (`datos/dividendos.csv`) |
| `cortos` | `total_publicado` (suma de posiciones ≥ 0,5 %), `fecha_dato` (publicación de la CNMV), `tenedores`, `posiciones` (tenedor, %, fecha), `ultima_posicion`, `cambios_30d`, `fuente` | colector `cortos` |
| `directivos` | 13 semanas: compras y ventas discrecionales (número e importe), neto, última operación, operaciones registradas en 30 días, `fecha_dato`, `fuente`. Sin nombres | colector `directivos` |
| `accionistas` | hasta 8 participaciones principales (cada una con su fecha), solo personas jurídicas, derechos de voto y `fecha_derechos_voto`, `fecha_dato`, nota con cuántas de personas físicas no se publican, `fuente` | colector `accionistas` |
| `recompra` | último comunicado de recompra (con su fecha) y si está «en curso» (comunicado en los últimos 45 días que no anuncia el final del programa), `fecha_dato`, `fuente` | colector `cnmv` |
| `cuatro_fuerzas` | lista de cifras: `fuerza`, `indicador`, `cifra`, `unidad`, `texto`, `ejercicio`, `fuente`, `pagina`, `enlace`, `fecha`, `verificado_por`, `verificado_el` (método en `CUATRO_FUERZAS.md`) | `empresas/cuatro_fuerzas.csv` (tabla de Datos; vacía hasta que la Redacción cierre la lista de cifras) |
| `perfil` | `sede` (domicilio social), `cierre_ejercicio` (DD/MM), `web_ri`, `fuente`, `fecha` (de la comprobación) | `empresas/perfil.csv` (tabla de Datos con fuente por fila; el 22/11, Iberdrola, Banco Santander e Inditex, con lo que se ha podido comprobar en fuente oficial; lo demás, vacío) |
| `eventos` | eventos de la empresa (tipos abajo) | las anteriores |
| `fuentes` | por bloque: `estado` y `fecha` del dato | — |
| `licencia`, `aviso` | cita de la CNMV y aviso de fin informativo y educativo | — |

Estados de `fuentes`: `ok`; `parcial` (accionistas: alguna empresa sin el filtro de personas jurídicas; dividendos: ver abajo); `anterior` (el colector falló hoy y se conserva **el último dato bueno**, con su fecha); `vacio` (no hay dato: la ficha oculta el bloque); `pendiente` (cuatro fuerzas y perfil sin filas).

Estado del bloque `dividendos` (desde la 1.2.0, 24/11/2026; antes era el del colector `cnmv` para todas las empresas): es el de cada empresa. `ok`: todos sus pagos leídos del comunicado (importe y fechas; en un flexible, el efectivo y su fecha de pago); `parcial`: algún pago remite al comunicado, o solo hay anuncios de política de dividendos; `vacio`: ningún comunicado de dividendo en doce meses. Mismos valores del contrato 1.0, otro significado: Iberdrola sale `parcial` (sus comunicados de cierre y de capital del flexible no traen importe) e Inditex, `ok`. Los dividendos que una empresa anuncia solo en su nota de resultados (lista cerrada del colector `cnmv`, hoy Inditex) entran como un dividendo por pago, con `tipo` «Dividendo», la nota como `titulo` y `enlace`, y `lectura` «dividendo … anunciado en los resultados: leído del comunicado». En un flexible con el efectivo leído, `importe` es el efectivo por acción para quien elige cobrar en efectivo; `lectura` y el evento lo dicen.

Tipos de evento (`TIPOS_EVENTO`): `corto_nueva`, `corto_sube`, `corto_baja`, `corto_sale`, `insider_compra`, `insider_venta`, `dividendo_ex`, `dividendo_pago`, `comunicado_recompras`, `comunicado_resultados`, `comunicado_dividendos`, `comunicado_opvs-ampliaciones`, `comunicado_opas`, `comunicado_otro`. Cada evento: `fecha`, `tipo`, `isin`, `empresa`, `ficha`, `titulo`, `detalle`, `url` (documento de la CNMV o página publicada de El Especulador; vacía si no hay), `fuente`. Los de dividendo (desde la 1.1.0) salen de las fechas leídas del comunicado de la CNMV; un mismo dividendo anunciado varias veces (misma fecha e importe a menos de un 5 %, o sin importe en uno: el aprobado y el ajustado por la autocartera, o un recordatorio) da un solo evento, con el importe exacto del comunicado más reciente que lo tenga.

La huella (SHA-256, 12 caracteres) se calcula sobre el contenido de la ficha sin `actualizado`, `version`, `fuentes` ni `licencia`: un archivo solo se reescribe si cambian sus datos.

Ejemplos reales en `ejemplos/` (22/11/2026; muestra del encargo de Tecnología): **Iberdrola** (`ES0144580Y14`: diez comunicados de dividendo flexible, OPA de exclusión de Neoenergia), **Banco Santander** (`ES0113900J37`: dos dividendos en efectivo leídos del comunicado, 0,125 € y 0,127 €, con sus fechas, y la política de dividendos) e **Inditex** (`ES0148396007`: sin comunicados de dividendo propios en doce meses: anunció el de 2025 dentro de sus resultados anuales, OIR 39667, que está en el registro oficial), más Repsol (`ES0173516115`, recompra en curso y una posición corta) y Solaria (`ES0165386014`, diez posiciones cortas) para la plantilla, `indice.json` y `eventos.json`. Datos: cortos y accionistas del servidor (20 y 21/11), `cnmv` con el relleno de doce meses de la PR #111 (17/10/2025 a 22/11/2026); `directivos`, sin desplegar (bloque vacío).

## Licencias y cumplimiento

Todo son datos de la CNMV ya publicados por otros colectores con licencia verificada (nota legal de la CNMV, 02/11/2026: reproducción fiel, cálculos permitidos; gratuitos en cnmv.es). Cuatro fuerzas: cifras del informe financiero anual depositado en la CNMV, con documento y página, dos extracciones independientes coincidentes. Personas físicas: no entran. Accionistas, solo con el filtro de personas jurídicas; cortos, un tenedor que no se reconozca como persona jurídica (regla de `accionistas/duenos.py` más `TENEDORES_ENTIDAD`) sale como «Tenedor no identificado como persona jurídica (nombre no publicado)» y con aviso, para revisarlo; directivos, sin nombre desde su colector. Sin predicción ni recomendación en los textos de los eventos.

## Reglas de ejecución

- Colector ausente: su bloque conserva el de la ficha anterior (`anterior`, con su fecha), y también sus eventos dentro de la ventana; si nunca hubo dato, el bloque va vacío. Un `::warning::` por colector ausente.
- Ningún colector disponible: `DatosRaros` y el script se para sin escribir (`servidor/ejecutar.sh` abre la incidencia `empresas-fallido`). Tabla de cuatro fuerzas o de perfil sin sus columnas: `DatosRaros`.
- Horario en el servidor: 07:40 L-S y 21:10 L-V de Madrid (`servidor/ejecutar.sh empresas`; ver `DESPLIEGUE.md`). Carpeta `empresas` en la lista blanca de nginx.

## Pruebas

`python empresas/pruebas_empresas.py`: 81 comprobaciones con salidas simuladas de los colectores en su formato real: campos del contrato, direcciones `/ibex35/`, ninguna huella de BME aunque estén sus ficheros antiguos, cortos (persona física sin nombre, entidad sin forma societaria con nombre), directivos, accionistas, registro oficial de doce meses, dividendos de la CNMV sin rentabilidad, recompra, eventos, huella estable, escritura solo con cambios, `indice.json` con la fecha de comprobación, `cambios.csv`, último dato bueno, fuentes ausentes, cuatro fuerzas, perfil, un dividendo anunciado varias veces, una recompra que ha terminado y (1.2.0) el estado de dividendos por empresa con un control con pandas, los dividendos de Inditex anunciados en los resultados, un flexible con el efectivo leído y el último dato bueno de una empresa sin dividendos. Las mutaciones de cada regla hacen fallar alguna.

## Pendiente

- Desplegar con los siete colectores pendientes (mensaje 1 de `Mensajes-para-pegar-2026-11-19`); primera pasada a mano y revisión de tres fichas.
- Hecho en la 1.2.0 (24/11, a petición de Tecnología): estado de dividendos por empresa (Inditex salía «ok» con el bloque vacío), dividendos anunciados en los resultados (Inditex), efectivo de los flexibles (Iberdrola, ACS, Ferrovial, Sacyr) y perfil de Banco Santander con fuente de la CNMV (domicilio, OIR 39132; cierre del ejercicio, OIR 39978).
- Hecho en la 1.1.0 (22/11): importe, moneda y fechas de cada dividendo leídos del comunicado de la CNMV (`cnmv/dividendos_cnmv.py`, PR #111), eventos de fecha ex y pago, fecha del dato en cada bloque, alcance y «desde» del registro oficial.
- Siguiente: `recompra.ejecutado` con el colector de recompras; perfil de las 32 empresas restantes (tabla a mano con fuente oficial por fila; ~1 h de Datos).
- Cuatro fuerzas: cuando la Redacción cierre la lista de cifras por fuerza (método en `CUATRO_FUERZAS.md`).
- SEC (empresas de EE. UU.) cuando el colector de la SEC llegue a Datos.

Horas de Federico: 0 (más fusionar).
