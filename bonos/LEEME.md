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
