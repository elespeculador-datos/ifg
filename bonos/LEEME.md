# Bonos y Obligaciones del Estado

Resultados de todas las subastas de Bonos y Obligaciones del Estado desde 2001, la última de cada plazo
(tal como la presenta el Tesoro), los valores en emisión, las próximas subastas (con la fecha límite de
peticiones de los particulares con Cuenta Directa) y los Bonos y Obligaciones no segregados en manos de
personas físicas. Fuente: D. G. del Tesoro y Política Financiera (www.tesoro.es).

- Script: `bonos/bonos.py --salida docs/bonos`. Independiente de `letras/`: copia sus utilidades para que
  un cambio en un activo no rompa el otro.
- Flujo: `.github/workflows/bonos-diario.yml` (12:40 UTC, lunes a viernes). Si falla, abre una incidencia
  con la etiqueta `bonos-fallido` y la página se queda con el último dato bueno.
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
  (subastas del mes en curso), entran como filas de la web con el plazo de su columna o de su vida
  residual (VR).
- Etiquetas del Tesoro en el Excel: B/O, €i (indexado a la inflación europea), (BV) verde, (v) tipo
  variable, (s) sindicación, «>30a» más de 30 años. La serie a 10 años y las medias anuales excluyen
  indexados, verdes, variables y sindicaciones.
- tesoro.es no envía el certificado intermedio (FNMT): el script lo descarga del campo AIA y lo añade
  a certifi. La verificación TLS sigue activa.
- Condiciones del Tesoro: reproducción fiel, citando a la D. G. del Tesoro y Política Financiera; se
  permiten cálculos.

## Llamadas a nota en la tabla del Tesoro (19/11/2026)

Desde el 19/11/2026 el Tesoro pone en la fila «Nominal adjudicado (2ª vuelta)» (y en «Efectivo adjudicado (2ª vuelta)») una llamada a nota «[1]» en vez de la cifra cuando los resultados de la 2.ª vuelta todavía no se han anunciado; la nota, al pie de la tabla, dice cuándo se anunciarán (comprobado en la página de Obligaciones el 19/11/2026: «Los resultados de la 2ª vuelta se anunciarán el 23/11/2026»). El colector paraba con «número con formato inesperado: '[1]'». Ahora `_dec` quita cualquier llamada «[n]» antes de leer la cifra, y una celda que solo tiene la nota vale None, igual que un guion; en el CSV la 2.ª vuelta queda vacía hasta que el Tesoro publique la cifra (la siguiente pasada la recoge). Pruebas: `pruebas_bonos.py` con la tabla simulada `prueba_ultimas_nota.html` y con las cuatro tablas reales del 21/11/2026 en `pruebas_tesoro/` (obligaciones, bonos, indexados y valores en emisión, copiadas de tesoro.es con su estructura): el código anterior falla con ellas con el mismo error que el servidor; el arreglado las lee enteras.
