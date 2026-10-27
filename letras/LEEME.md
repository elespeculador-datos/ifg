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
