# Ficha integrada por empresa (indicador 16)

Pregunta del lector (en la ficha de cada empresa del IBEX 35): ¿qué está pasando con esta empresa que no sale en la cotización: qué ha comunicado a la CNMV, qué dividendos ha anunciado, quién apuesta en contra, si compran o venden sus directivos, quién manda en el capital y si está recomprando?

Estado: **contrato 1.0 con el chat de fichas de Tecnología (21/11/2026), versión 1.0.0, en rama `empresas-contrato`**. Funciona con las fuentes que ya sirve el servidor (cnmv, cortos, accionistas filtrado) y completa `directivos` cuando se despliegue su colector. Sin nada de BME (ni dividendos, ni rentabilidades, ni precios).

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
| `registro_oficial` | comunicados a la CNMV de doce meses (resultados, dividendos, recompras, ampliaciones y OPVs, OPAs): `fecha`, `tipo`, `titulo` (tal como lo publica la CNMV), `fuente`, `enlace`, `nreg`, `grupo` (los de una misma operación comparten grupo) | colector `cnmv` |
| `dividendos` | anuncios de dividendo comunicados a la CNMV en doce meses: `fecha_comunicado`, `tipo`, `titulo`, `importe`, `moneda`, `fecha_ex`, `fecha_pago`, `lectura`, `fuente`, `enlace`, `nreg`. **Sin rentabilidad.** Importe y fechas van vacíos hasta que se lean con seguridad del propio comunicado (`cnmv/dividendos_cnmv.py`, prototipo; versión 1.1): la ficha enlaza el comunicado | colector `cnmv` |
| `cortos` | `total_publicado` (suma de posiciones ≥ 0,5 %), `fecha_dato` (publicación de la CNMV), `tenedores`, `posiciones` (tenedor, %, fecha), `ultima_posicion`, `cambios_30d`, `fuente` | colector `cortos` |
| `directivos` | 13 semanas: compras y ventas discrecionales (número e importe), neto, última operación, operaciones registradas en 30 días. Sin nombres | colector `directivos` |
| `accionistas` | hasta 8 participaciones principales, solo personas jurídicas, derechos de voto y su fecha, nota con cuántas de personas físicas no se publican | colector `accionistas` |
| `recompra` | último comunicado de recompra y si está «en curso» (comunicado en los últimos 45 días) | colector `cnmv` |
| `cuatro_fuerzas` | lista de cifras: `fuerza`, `indicador`, `cifra`, `unidad`, `texto`, `ejercicio`, `documento`, `pagina`, `enlace`, `fecha`, `verificado_por`, `verificado_el` | `empresas/cuatro_fuerzas.csv` (tabla de Datos; vacía hasta que la Redacción cierre la lista de cifras) |
| `perfil` | `sede`, `cierre_ejercicio`, `web_ri`, `fuente`, `fecha` | `empresas/perfil.csv` (tabla de Datos; vacía) |
| `eventos` | eventos de la empresa (tipos abajo) | las anteriores |
| `fuentes` | por bloque: `estado` y `fecha` del dato | — |
| `licencia`, `aviso` | cita de la CNMV y aviso de fin informativo y educativo | — |

Estados de `fuentes`: `ok`; `parcial` (accionistas: alguna empresa sin el filtro de personas jurídicas); `anterior` (el colector falló hoy y se conserva **el último dato bueno**, con su fecha); `vacio` (no hay dato: la ficha oculta el bloque); `pendiente` (cuatro fuerzas y perfil sin filas).

Tipos de evento (`TIPOS_EVENTO`): `corto_nueva`, `corto_sube`, `corto_baja`, `corto_sale`, `insider_compra`, `insider_venta`, `comunicado_recompras`, `comunicado_resultados`, `comunicado_dividendos`, `comunicado_opvs-ampliaciones`, `comunicado_opas`, `comunicado_otro`. Cada evento: `fecha`, `tipo`, `isin`, `empresa`, `ficha`, `titulo`, `detalle`, `url` (documento de la CNMV o página publicada de El Especulador; vacía si no hay), `fuente`. Los eventos de dividendo con fecha ex y pago (`dividendo_ex`, `dividendo_pago`) vuelven en la versión 1.1, con datos de la CNMV.

La huella (SHA-256, 12 caracteres) se calcula sobre el contenido de la ficha sin `actualizado`, `version`, `fuentes` ni `licencia`: un archivo solo se reescribe si cambian sus datos.

Ejemplos reales en `ejemplos/` (21/11/2026: cortos y accionistas del servidor; cnmv con el relleno de la PR #111; directivos aún sin desplegar): Iberdrola (`ES0144580Y14`, dividendo flexible), Repsol (`ES0173516115`, recompra y cortos), Solaria (`ES0165386014`, diez posiciones cortas) e `indice.json`.

## Licencias y cumplimiento

Todo son datos de la CNMV ya publicados por otros colectores con licencia verificada (nota legal de la CNMV, 02/11/2026: reproducción fiel, cálculos permitidos; gratuitos en cnmv.es). Cuatro fuerzas: cifras del informe financiero anual depositado en la CNMV, con documento y página, dos extracciones independientes coincidentes. Personas físicas: no entran. Accionistas, solo con el filtro de personas jurídicas; cortos, un tenedor que no se reconozca como persona jurídica (regla de `accionistas/duenos.py` más `TENEDORES_ENTIDAD`) sale como «Tenedor no identificado como persona jurídica (nombre no publicado)» y con aviso, para revisarlo; directivos, sin nombre desde su colector. Sin predicción ni recomendación en los textos de los eventos.

## Reglas de ejecución

- Colector ausente: su bloque conserva el de la ficha anterior (`anterior`, con su fecha), y también sus eventos dentro de la ventana; si nunca hubo dato, el bloque va vacío. Un `::warning::` por colector ausente.
- Ningún colector disponible: `DatosRaros` y el script se para sin escribir (`servidor/ejecutar.sh` abre la incidencia `empresas-fallido`). Tabla de cuatro fuerzas o de perfil sin sus columnas: `DatosRaros`.
- Horario en el servidor: 07:40 L-S y 21:10 L-V de Madrid (`servidor/ejecutar.sh empresas`; ver `DESPLIEGUE.md`). Carpeta `empresas` en la lista blanca de nginx.

## Pruebas

`python empresas/pruebas_empresas.py`: 61 comprobaciones con salidas simuladas de los colectores en su formato real: campos del contrato, direcciones `/ibex35/`, ninguna huella de BME aunque estén sus ficheros antiguos, cortos (persona física sin nombre, entidad sin forma societaria con nombre), directivos, accionistas, registro oficial de doce meses, dividendos de la CNMV sin rentabilidad, recompra, eventos, huella estable, escritura solo con cambios, `indice.json` con la fecha de comprobación, `cambios.csv`, último dato bueno, fuentes ausentes, cuatro fuerzas y perfil. Cinco mutaciones del código hacen fallar alguna.

## Pendiente

- Desplegar con los siete colectores pendientes (mensaje 1 de `Mensajes-para-pegar-2026-11-19`); primera pasada a mano y revisión de tres fichas.
- Versión 1.1: importe, fecha ex y fecha de pago de cada dividendo leídos del comunicado de la CNMV (solo cuando se lean con seguridad; si no, enlace); `recompra.ejecutado` con el colector de recompras.
- Cuatro fuerzas: cuando la Redacción cierre la lista de cifras por fuerza (contrato del 21/11). Perfil: tabla a mano con fuente por dato.
- SEC (empresas de EE. UU.) cuando el colector de la SEC llegue a Datos.

Horas de Federico: 0 (más fusionar).
