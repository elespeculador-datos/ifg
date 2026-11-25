# Bonos y Obligaciones del Estado

Resultados de todas las subastas de Bonos y Obligaciones del Estado desde 2001, la última de cada plazo
(tal como la presenta el Tesoro), los valores en emisión, las próximas subastas (con la fecha límite de
peticiones de los particulares con Cuenta Directa) y los Bonos y Obligaciones no segregados en manos de
personas físicas. Fuente: D. G. del Tesoro y Política Financiera (www.tesoro.es).

- Script: `bonos/bonos.py --salida docs/bonos`. Independiente de `letras/`: copia sus utilidades para que
  un cambio en un activo no rompa el otro.
- Ejecución: en el servidor, `servidor/ejecutar.sh bonos` a las 13:40 de Madrid, de lunes a viernes (ver
  `DESPLIEGUE.md`); el flujo `.github/workflows/bonos-diario.yml` queda como documentación (tesoro.es no
  responde a los ejecutores de GitHub). Si falla, abre la incidencia `bonos-fallido` y la página se queda
  con el último dato bueno.
- Salida (GitHub Pages): `docs/bonos/` → `fragmento-wp.html` (marcas `<!-- bonos:inicio HUELLA -->` y
  `<!-- bonos:fin -->`, con el marcado Dataset), `index.html`, `datos/subastas_bonos_obligaciones.csv`,
  `datos/proximas_subastas.csv`, `datos/ultima.json`.
- Fuentes: las tres páginas de últimas subastas (Bonos, Obligaciones, indexados), la de valores en
  emisión, el Excel mensual 11-xlsx (año en curso y anterior), el histórico historico_subastas-xlsx
  (2001-2025; columnas 7 a 13, emisiones a largo plazo; la fecha se toma del día y mes de la celda y del
  año de la hoja), el Excel 05-xlsx (tenedores de Bonos y Obligaciones no segregados) y el PDF del
  calendario de cada año (columnas 3.ª y 4.ª de cada mes; el asterisco marca las que pueden incluir
  indexados).
- Las subastas de la web se casan con las del Excel por fecha, cupón y si son indexadas; si no casan
  (subastas que el Excel mensual aún no recoge), entran como filas de la web. El plazo es siempre la
  columna del Tesoro (ver «Memoria, protección y plazo», más abajo).
- Etiquetas del Tesoro en el Excel: B/O, €i (indexado a la inflación europea), (BV) verde, (v) tipo
  variable, (s) sindicación, «>30a» más de 30 años. La serie a 10 años y las medias anuales excluyen
  indexados, verdes, variables y sindicaciones.
- tesoro.es no envía el certificado intermedio (FNMT): el script lo descarga del campo AIA y lo añade
  a certifi. La verificación TLS sigue activa.
- Condiciones del Tesoro: reproducción fiel, citando a la D. G. del Tesoro y Política Financiera; se
  permiten cálculos.

## Llamadas a nota en la tabla del Tesoro (19/11/2026)

Desde el 19/11/2026 el Tesoro pone en la fila «Nominal adjudicado (2ª vuelta)» (y en «Efectivo adjudicado (2ª vuelta)») una llamada a nota «[1]» en vez de la cifra cuando los resultados de la 2.ª vuelta todavía no se han anunciado; la nota, al pie de la tabla, dice cuándo se anunciarán (comprobado en la página de Obligaciones el 19/11/2026: «Los resultados de la 2ª vuelta se anunciarán el 23/11/2026»). El colector paraba con «número con formato inesperado: '[1]'». Ahora `_dec` quita cualquier llamada «[n]» antes de leer la cifra, y una celda que solo tiene la nota vale None, igual que un guion; en el CSV la 2.ª vuelta queda vacía hasta que el Tesoro publique la cifra (la siguiente pasada la recoge). Pruebas: `pruebas_bonos.py` con la tabla simulada `prueba_ultimas_nota.html` y con las cuatro tablas reales del 21/11/2026 en `pruebas_tesoro/` (obligaciones, bonos, indexados y valores en emisión, copiadas de tesoro.es con su estructura): el código anterior falla con ellas con el mismo error que el servidor; el arreglado las lee enteras.

## Memoria, protección y plazo (23/11/2026)

**Qué pasó.** La tabla de resultados del Tesoro solo enseña la última subasta de cada plazo, y el Excel mensual (`11-xlsx`) tarda semanas en recoger las nuevas. Una subasta que solo estaba en la web desaparecía del CSV cuando la tabla pasaba a la siguiente. Así se perdieron, en la pasada del 21/11/2026 (la primera correcta tras el fallo de «[1]»), las dos subastas del 05/11/2026 que el Tesoro ya no mostraba: la Obligación 3,40 % a 10 años y la Obligación 3,10 % (VR 4a 9 m) en la columna de Bono a 5 años. Además, el plazo no era uno solo: el CSV daba a las reaperturas de la web su vida residual (8 años a la O 3,20 % (VR 8a 11m) del 19/11), y la página, la columna del Tesoro (10 años). Marketing decidió el 21/11 un criterio único: la columna del Tesoro, con la vida residual en el nombre del valor.

**Memoria.** Cada pasada lee el CSV anterior (`datos/subastas_bonos_obligaciones.csv` de `--salida`). Las filas que vinieron de la web (`fuente` con «web») y cuya subasta ya no está en la tabla del Tesoro se tratan como si siguieran en ella: se casan con el Excel cuando llega y conservan lo que solo da la web (cifras con dos decimales, precios medios, vencimiento, nombre y columna). El CSV se escribe en un temporal y se cambia de nombre al final, para que una pasada cortada no deje una memoria a medias; un CSV anterior ilegible para la pasada (`DatosRaros`).

**Protección.** Antes de escribir, el CSV nuevo se compara con el anterior por fila completa, contando repeticiones. Cada fila anterior tiene que seguir igual o estar actualizada, es decir, ser la misma subasta con datos nuevos: misma fecha, cupón, indexación y sindicación, y además el mismo activo, el nombre del Tesoro que el Excel recoge ya con su etiqueta, o los mismos rendimientos medio y marginal. Si ninguna fila nueva es su subasta, se conserva tal cual y el flujo avisa (`::warning::` y `control_csv` en `ultima.json`). Una fila anterior que repetía una subasta que sigue en el CSV con otra etiqueta se quita y se anota como duplicada. El registro de cada pasada lista las filas recuperadas, actualizadas (columna a columna), duplicadas, conservadas y nuevas.

**Recuperación.** `filas_recuperadas.csv` guarda las dos subastas del 05/11, con las cifras de la Resolución de 10/11/2026 de la D. G. del Tesoro y Política Financiera (BOE núm. 288, 19/11/2026, BOE-A-2026-24268), con la precisión de la tabla web del Tesoro (importes con dos decimales; precio medio de compra = precio de adjudicación de las peticiones no competitivas; 2.ª vuelta sin peticiones), y la columna y el nombre de la tabla del Tesoro reproducida en la página con el fragmento del 17/11/2026. Las cuatro subastas de ese día comprobadas frente al BOE: las dos que seguían en el CSV (O 3,50 % y O€i 0,70 %) coinciden cifra a cifra. Cada pasada añade las filas de este archivo cuya subasta falte; cuando ya están, no hace nada.
- `--recuperar CSV`: lo mismo con otro CSV de este colector (de cualquier fecha y formato); detalla en el registro en qué difieren las filas que ya estaban.
- `--comparar CSV`: no hace pasada; compara por fila completa el CSV de `--salida` con otro y dice qué cambia, qué falta y qué sobra.

**Plazo.** `plazo_anios` es la columna en que el Tesoro publica el resultado en su tabla cuando la conocemos y, si no, el plazo de la etiqueta del Excel del Tesoro (en las reaperturas, la etiqueta puede reflejar la vida residual: O 2,90 % (VR 20a 1m) subastada en la columna de 15 años figura en el Excel como «O-20a»; O 3,55 % (VR 7a) en la de 5 años, como «O-7a»). Con columna conocida, `mas_de` vale 0 (la columna es exacta: la O 1,45 % de 2071 está en la de 50 años y el Excel la etiqueta «O->30a»). El CSV tiene tres columnas nuevas al final, sin mover las anteriores: `valor_tesoro` (nombre en la tabla del Tesoro), `vida_residual` (solo si el nombre la indica con «VR»; otros paréntesis, como «(7A)», quedan solo en el nombre) y `columna_tesoro` (vacía si no se conoce). `columnas_tesoro.csv` recoge la columna de las subastas vistas antes de que el CSV la guardara: la tabla leída por el colector del 21/10 al 04/11/2026 (historial de `docs/bonos/datos/ultima.json`) y la reproducida en la página el 17/11/2026. Con ello se conoce la columna de todas las subastas desde el 15/10/2026 y de algunas anteriores.
- `ultima.json` (`ultimas`) lleva el plazo de la columna: el pulso del Tesoro de la prima de riesgo, que busca ahí el plazo 10, vuelve a encontrar la última subasta a 10 años (con la versión anterior no encontraba ninguna desde el 19/11).
- La página: el primer párrafo y la tabla de la última subasta de cada plazo ya usaban la columna; la serie de Obligaciones a 10 años y las medias anuales usan ahora el mismo criterio, con la vida residual en el nombre del valor. Las medias siguen separando Bonos y Obligaciones por clase de valor.

**Pendiente, sin prisa (no legítimo).** El CSV repite tres subastas del 04/12/2025, una vez con la etiqueta del histórico («B-5a», «O€i-10a», «O-13a») y otra con la del Excel mensual («B-5y», «O€i-10y», «O-13y»), porque la clave de unión incluye la etiqueta. La media de 2025 de los Bonos a 5 años cuenta dos veces la del 04/12 (2,514 % publicado; 2,520 % sin la repetida). Se quitarán solas cuando el Excel mensual deje 2025 (las anota como duplicadas); si se prefiere antes, basta con normalizar «y» a «a» en la etiqueta al unir. Las siete repeticiones de fecha y activo que señaló Marketing (2008-12-18 «O-30a (s)», etc.) son legítimas: cupones distintos.

**Pruebas** (`pruebas_bonos.py`, 61 comprobaciones): la Resolución del BOE (texto de `pdftotext -layout` en `pruebas_tesoro/BOE-A-2026-24268.txt`) frente a las dos filas recuperadas y, como control, frente a las otras dos subastas del 05/11 que el CSV sí tenía, leídas de la web: coinciden cifra a cifra. Además, el CSV real que servía el servidor el 21/11/2026 (`pruebas_tesoro/subastas-servidor-2026-11-21.csv`), las tablas reales del Tesoro del 21/11 y el Excel reconstruido desde ese CSV. La pasada del lunes da 1.491 filas: 1.476 iguales, 15 actualizadas (las tres columnas nuevas y, en cinco filas, el plazo de la columna), las dos recuperadas y ninguna conservada ni duplicada; control con `pandas` (unión externa por las 19 columnas de antes: solo cambian esas cinco filas y entran las dos recuperadas). Después: segunda pasada idéntica byte a byte, rotación de la tabla del Tesoro, llegada del Excel mensual con noviembre (etiquetas simuladas), una fila que el Excel deja de traer, las repeticiones de diciembre de 2025 cuando el mensual deje 2025, recuperación desde una copia en el formato antiguo y CSV ilegibles. Cinco mutaciones del código (sin memoria, sin protección, plazo por vida residual, sin columnas conocidas, sin quitar duplicadas) hacen fallar alguna comprobación.
