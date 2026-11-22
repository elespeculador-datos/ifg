# Calendario de dividendos del IBEX 35 (indicador 11, primera parte)

Cada hora, al minuto 37 de las 06 a las 23 y todos los días, el servidor smpro-datos-1 (`servidor/ejecutar.sh calendario`, ver `DESPLIEGUE.md`) ordena los dividendos que las empresas del IBEX 35 comunican a la CNMV y publica en `$ESPEC_DATOS_DIR/calendario/` (https://datos.elespeculador.com/calendario/):

- `fragmento-wp.html`: frase del día, próximos dividendos (fecha ex o de pago de hoy en adelante), pagados en los últimos 90 días, dividendos flexibles comunicados en los últimos 120 días y método, entre `<!-- dividendos:inicio HUELLA -->` y `<!-- dividendos:fin -->`, las mismas marcas que la página 8578 (/calendario-dividendos/);
- `index.html`: página propia de la salida;
- `datos/ultima.json` (versión 1.0.0) y `datos/calendario.csv` (un dividendo por fila).

Pregunta del lector: ¿qué dividendos vienen en el IBEX 35, cuánto paga cada uno por acción y en qué fechas?

Sustituye, con una fuente con licencia, al calendario de BME de /calendario-dividendos/ (8578), congelado desde el 06/11/2026 porque la API de BME no tiene licencia de uso (P3 del catálogo, riesgo A).

## Fuente y licencia

CNMV: comunicados de otra información relevante e información privilegiada de las empresas del IBEX 35. Nota legal de la CNMV leída el 02/11/2026 (catálogo, fuentes): uso no privado autorizado con reproducción fiel, sin alterar contenidos; cálculos derivados permitidos y difundibles; en productos de pago, avisar de que la información es gratis en cnmv.es (el calendario es gratuito; si alguna vez entra en una zona de pago, el aviso va con él). Es el sustituto de P3 que ya preveía el catálogo: dividendos desde los comunicados de la CNMV; rentabilidad por dividendo, solo con licencia de precios. El calendario no descarga nada: lee la salida del colector `cnmv` de la misma carpeta (`cnmv/datos/dividendos.csv`, importe y fechas leídos del PDF de cada comunicado de dividendo, e `ibex35.csv`, clasificación de cada comunicado), que existe desde la PR #111. La lectura, la selección y el calendario son de El Especulador (CC BY 4.0). Sin precios ni rentabilidad por dividendo: harían falta cotizaciones con licencia.

## Método

1. Entran los comunicados que el colector `cnmv` clasifica hoy como «Dividendo» o «Dividendo flexible» (un comunicado que deja de ser de dividendos sale solo) y su lectura de `dividendos.csv`.
2. Un mismo dividendo anunciado varias veces (el importe aprobado, el ajustado por la autocartera, un recordatorio) sale una vez: misma empresa, misma fecha ex o misma fecha de pago e importe compatible (5 %); vale el comunicado más reciente con importe, y uno sin importe no borra el importe de otro anterior.
3. Próximos: fecha ex o fecha de pago de hoy en adelante, por orden de fecha ex (o de pago si no hay ex). Una fecha ex ya pasada con el pago pendiente se marca «(pasada)». Sin fecha ex leída, raya.
4. Pagados: pago en los últimos 90 días, del más reciente al más antiguo.
5. Flexibles: último comunicado de cada empresa en 120 días, sin importe (el efectivo depende de lo que elija el accionista); fuera los que solo modifican una recompra.
6. Tipo (a cuenta, complementario, extraordinario): del título del comunicado; si el título no lo dice, raya.
7. Importes brutos por acción en su moneda (dólares de ArcelorMittal, por ejemplo), con dos decimales como mínimo y los que dé el comunicado. Si el importe no se lee con seguridad, la casilla enlaza con el comunicado.

Límite conocido: solo entran los dividendos comunicados en un comunicado propio. Los que una empresa anuncia únicamente dentro de su presentación de resultados (Inditex en los últimos doce meses) no aparecen, y así lo dice la página.

## Reglas

- Si falta `cnmv/datos/dividendos.csv` o `ibex35.csv`, está vacío o le faltan columnas, el script se para sin publicar (`::error::calendario: …`, código 1) y `servidor/ejecutar.sh` abre la incidencia `calendario-fallido`.
- Huella: versión y datos publicados, incluidas las fechas ex que ya han pasado (la frase y la marca «pasada» cambian con el día). Sin cambio de huella no reescribe, salvo que falte algún fichero; `--forzar` regenera.
- Sin predicción ni recomendación; contenido informativo y educativo.

## Comprobaciones

`python calendario/pruebas_calendario.py`: 34 comprobaciones sin red con salidas simuladas del colector `cnmv` (formato real): lectura y exclusiones, concepto, un dividendo anunciado tres veces, fecha ex pasada con el pago pendiente, pago sin fecha ex, dos dividendos distintos el mismo día, pagados dentro y fuera de 90 días, flexibles y recompras, dólares, importe sin leer, títulos con caracteres especiales, frase del día (con y sin importe, singular, sin fechas ex por delante), marcas, huella, escritura, paradas, línea de órdenes y un caso de control con pandas.

## Validación con datos reales (22/11/2026)

Sobre los doce meses de comunicados de la CNMV de la PR #111 (6.988 comunicados; 61 dividendos en efectivo del IBEX 35 revisados uno a uno contra su PDF el 22/11, sin ningún importe ni fecha distinto del comunicado): 7 dividendos con fecha ex de hoy en adelante, de 7 empresas (Mapfre 0,080248 € el 24/11, IAG, Fluidra, Enagás, Unicaja, Redeia y Repsol); 9 filas en «próximos» con Merlin (fecha ex pasada, pago el 10/12) y Grifols (sin fecha ex en el comunicado, pago el 04/12); 4 pagados en 90 días (CaixaBank, Santander, BBVA y Unicaja); 2 empresas con dividendo flexible (Ferrovial e Iberdrola). Fragmento de 9.071 caracteres. Verificado sobre el dato, no estimado.

## Entrega a Tecnología

- Fragmento: `https://datos.elespeculador.com/calendario/fragmento-wp.html` (marcas `dividendos:inicio` / `dividendos:fin`).
- JSON: `https://datos.elespeculador.com/calendario/datos/ultima.json`; CSV: `https://datos.elespeculador.com/calendario/datos/calendario.csv`.
- Pasada: al minuto 37 de 06 a 23, todos los días (media hora después de cada pasada de `cnmv`). Dato nuevo: cambia la huella de la primera línea.
- Página en borrador: 9495 (`/calendario-dividendos-ibex-35/`), creada el 22/11/2026 con el fragmento real. Escenario de Make 10212212 (DIARIO, inactivo hasta que el servidor sirva `/calendario/`; cada hora de 06:45 a 23:30, todos los días). Propuesta a Federico: sustituir el contenido de 8578 por el del borrador (misma dirección) y apuntar el escenario a 8578.
- Dependencias: ninguna fuera de la biblioteca estándar (las pruebas usan pandas).
