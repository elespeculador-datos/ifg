# Letras del Tesoro

Resultados de todas las subastas de Letras del Tesoro desde 2001, la última de cada plazo, las
próximas subastas (con la fecha límite de peticiones de los particulares con Cuenta Directa) y las
Letras en manos de personas físicas. Fuente: D. G. del Tesoro y Política Financiera (www.tesoro.es).

- Script: `letras/letras.py --salida docs/letras`
- Flujo: `.github/workflows/letras-diario.yml` (12:30 UTC, lunes a viernes)
- Salida (GitHub Pages): `docs/letras/` → `fragmento-wp.html` (marcas `<!-- letras:inicio HUELLA -->` y
  `<!-- letras:fin -->`, con el marcado Dataset), `index.html`, `datos/subastas_letras.csv`,
  `datos/proximas_subastas.csv`, `datos/ultima.json`.
- Fuentes: web de últimas subastas, Excel mensual 11-xlsx (año en curso y anterior), histórico
  historico_subastas-xlsx (2001-2025; la fecha se toma del día y mes de la celda y del año de la hoja),
  Excel 04-xlsx (tenedores) y el PDF del calendario de cada año (enlace leído de la página del calendario).
- tesoro.es no envía el certificado intermedio (FNMT): el script lo descarga del campo AIA y lo añade
  a certifi. La verificación TLS sigue activa.
- Condiciones del Tesoro: reproducción fiel, citando a la D. G. del Tesoro y Política Financiera; se
  permiten cálculos.

## Llamadas a nota en la tabla del Tesoro (19/11/2026)

Desde el 19/11/2026 el Tesoro pone en la fila «Nominal adjudicado (2ª vuelta)» (y en «Efectivo adjudicado (2ª vuelta)») una llamada a nota «[1]» en vez de la cifra cuando los resultados de la 2.ª vuelta todavía no se han anunciado; la nota, al pie de la tabla, dice cuándo se anunciarán (comprobado en la página de Obligaciones el 19/11/2026: «Los resultados de la 2ª vuelta se anunciarán el 23/11/2026»). El colector paraba con «número con formato inesperado: '[1]'». Ahora `_dec` quita cualquier llamada «[n]» antes de leer la cifra, y una celda que solo tiene la nota vale None, igual que un guion; en el CSV la 2.ª vuelta queda vacía hasta que el Tesoro publique la cifra (la siguiente pasada la recoge). Pruebas: `pruebas_letras.py` con la tabla simulada `prueba_ultimas_nota.html`.
