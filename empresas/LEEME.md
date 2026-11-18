# Ficha integrada por empresa (indicador 16)

Pregunta del lector (en la ficha de cada empresa del IBEX 35): ¿qué está pasando con esta empresa que no sale en la cotización: quién apuesta en contra, si compran o venden sus directivos, quién manda en el capital, cuándo paga el dividendo, si está recomprando y qué ha comunicado a la CNMV?

Estado: **esqueleto completo en rama `ficha-integrada`** (versión 0.1.0). Funciona ya con las fuentes que existen (cortos, cnmv) y se completa solo cuando el servidor sirva `directivos/` y `accionistas/` (con el filtro de personas jurídicas de la PR #97). El bloque `dividendo` queda en null en el servidor mientras el colector de dividendos siga parado por la licencia de la API de BME (P3 del catálogo; `servidor/ejecutar.sh` lo rechaza): la ficha no publica nada de BME hasta que esa licencia se resuelva. Pasa a 1.0.0 cuando las fuentes disponibles estén en el servidor y una pasada real se haya revisado.

## Contrato (catálogo, 18/11/2026)

Datos **no toca las páginas** `/ibex-35/<empresa>/` (las hace otro chat; Tecnología las pinta con un snippet PHP como el de los comunicados de la CNMV). Datos publica en el servidor:

- `empresas/<ISIN>.json`: una ficha por empresa del IBEX 35 (35 archivos; `cnmv/empresas.csv` fija el universo y la dirección de la ficha de la web).
- `empresas/eventos.json`: todos los eventos con fecha entre hoy−30 y hoy+30 días, del más reciente al más antiguo, con su tipo, para avisos y listados.
- `empresas/indice.json`: lista de empresas con huella, fecha y dirección de cada JSON.
- `empresas/index.html`: página propia con el resumen (sin fragmento de WordPress: la ficha la pinta el chat de fichas desde el JSON).

## Qué lleva cada `<ISIN>.json`

| Bloque | Contenido | Fuente leída |
|---|---|---|
| `cortos` | suma publicada (posiciones ≥ 0,5 %), tenedores, lista de posiciones con fecha, cambios de los últimos 30 días (nueva, sube, baja, deja de publicarse) | `cortos/datos/vigentes.csv`, `historial_cambios.csv`, `ultima.json` |
| `directivos` | 13 semanas: compras y ventas discrecionales (número e importe), neto, última operación, operaciones registradas en 30 días. Sin nombres (el colector no los guarda); las sustituidas por una modificación no cuentan | `directivos/datos/operaciones.csv`, `ultima.json` |
| `accionistas` | hasta 8 participaciones principales (solo personas jurídicas), derechos de voto y su fecha, nota con cuántas personas físicas no se publican. **Solo se copia si la salida del colector lleva ya el campo `fisicas_excluidas`** (PR #97); si no, la sección va en null y el flujo avisa | `accionistas/datos/ultima.json` |
| `dividendo` | próximo (fecha ex, pago, bruto, moneda, concepto, extraordinario, flexible) y lo pagado en doce meses | `dividendos/datos/proximos.csv`, `ultimos_12m.csv` |
| `recompra` | último comunicado de recompra y si está «en curso» (comunicado en los últimos 45 días) | `cnmv/datos/ibex35.csv` (caja `recompras`) |
| `resultados`, `comunicados_30d` | último comunicado de resultados; todos los comunicados de 30 días | `cnmv/datos/ibex35.csv` |
| `eventos` | la lista de la empresa (ver tipos) | las cinco |
| `fuentes` | estado (`ok`, `parcial`, `ausente`) y fecha de cada fuente | — |

Tipos de evento (`TIPOS_EVENTO`): `corto_nueva`, `corto_sube`, `corto_baja`, `corto_sale`, `insider_compra`, `insider_venta`, `dividendo_ex`, `dividendo_pago`, `comunicado_recompras`, `comunicado_resultados`, `comunicado_dividendos`, `comunicado_opvs`, `comunicado_otro`. Cada evento: `fecha`, `tipo`, `isin`, `empresa`, `ficha` (dirección de la página), `titulo`, `detalle`, `url` (documento o página de datos de El Especulador), `fuente`.

La huella (SHA-256, 12 caracteres) se calcula sobre el contenido de la ficha sin la fecha de la pasada: un archivo solo se reescribe si cambian sus datos, así el chat de fichas puede comparar huellas. `eventos.json` lleva su propia huella.

## Licencias y cumplimiento

Todo son datos ya publicados por otros colectores con licencia verificada: CNMV (nota legal, reproducción fiel; gratis en cnmv.es) y BME (dividendos, condiciones de BME: citar «El Especulador, a partir de datos de BME»). El JSON lleva el campo `licencia` con la cita y el aviso de fin informativo y educativo. Personas físicas: no entran (cortos: gestoras; directivos: sin nombre desde su colector; accionistas: filtro de personas jurídicas obligatorio). Sin predicción ni recomendación en los textos de los eventos.

## Reglas de ejecución

- Fuente ausente: su sección va en null, `fuentes.<x>.estado = "ausente"` y `::warning::`. Ninguna fuente: `DatosRaros` y el script se para sin escribir (`servidor/ejecutar.sh` abre la incidencia `empresas-fallido`).
- Universo vacío (ni `cnmv/empresas.csv` ni `dividendos/ibex35.csv`): `DatosRaros`.
- Horario propuesto en el servidor: dos pasadas diarias, 07:40 (tras directivos, 07:10) y 21:10 (tras cortos, 20:40 en invierno) de Madrid: `servidor/ejecutar.sh empresas` (convención genérica: `empresas/empresas.py --salida $ESPEC_DATOS_DIR/empresas`; `--datos` toma por defecto la carpeta madre de la salida, es decir, `$ESPEC_DATOS_DIR`). Carpeta `empresas` en la lista blanca de nginx. Ver `DESPLIEGUE.md`.

## Pruebas

`python empresas/pruebas_empresas.py`: 56 comprobaciones con salidas simuladas de los cinco colectores en su formato real (cabeceras y claves copiadas de las salidas publicadas): ventanas de 13 semanas y 30 días, filtros (≥ 0,5 %, discrecional, sustituidas, personas jurídicas), próximo dividendo, recompra en curso, eventos y su orden, huella estable, escritura solo con cambios, fuentes ausentes y DatosRaros.

Pasada local con las salidas guardadas en el repositorio (cortos hasta el 28/10 y cnmv hasta el 06/11): `python empresas/empresas.py --salida /tmp/empresas --datos docs --fecha 2026-11-06` → 35 fichas, 133 eventos, tres avisos (directivos, accionistas y dividendos ausentes); la segunda pasada no reescribe nada.

El flujo `empresas-validacion` (solo a mano) descarga las salidas públicas de `datos.elespeculador.com` que existan y genera las fichas en el ejecutor para revisarlas antes de desplegar. Ejecución 44424375107 (19/11/2026): cortos, accionistas y cnmv presentes; 35 fichas y 181 eventos (40 comunicados de recompra, 50 de resultados, 12 de dividendos, 79 cambios de cortos); la sección de accionistas quedó en null en las 33 empresas porque el servidor aún no aplica el filtro de personas jurídicas (PR #97), que es justo lo que debe pasar.

## Pendiente

- Desplegar en el servidor cuando `directivos/` y `accionistas/` (filtrado) estén servidos; primera pasada a mano y revisión de tres fichas (una con cortos, una con insiders, una con recompra).
- Avisar al chat de fichas de las rutas y de los tipos de evento (deber de Federico anotado en el catálogo).
- Versión 1.1: añadir el bloque `recompra.ejecutado` (acciones y precio medio de la semana) cuando exista el colector de recompras (fase 1 del indicador 17).

Horas de Federico: 0 (más el aviso al chat de fichas).
