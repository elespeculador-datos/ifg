# Letras del Tesoro

Resultados de todas las subastas de Letras del Tesoro desde 2001, la última de cada plazo, las
próximas subastas (con la fecha límite de peticiones de los particulares con Cuenta Directa) y las
Letras en manos de personas físicas. Fuente: D. G. del Tesoro y Política Financiera (www.tesoro.es).

- Script: `letras/letras.py --salida docs/letras`
- Ejecución: en el servidor, `servidor/ejecutar.sh letras` a las 13:30 de Madrid, de lunes a viernes (ver `DESPLIEGUE.md`); el flujo `.github/workflows/letras-diario.yml` queda como documentación (tesoro.es no responde a los ejecutores de GitHub).
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

## Memoria y protección del CSV (23/11/2026)

El mismo fallo que perdió dos subastas de Bonos del 05/11/2026 (ver `bonos/LEEME.md`) amenazaba a Letras: la tabla de resultados del Tesoro solo enseña la última subasta de cada plazo y el Excel mensual (`11-xlsx`) tarda semanas en recoger las nuevas, así que una subasta que solo estaba en la web desaparecía del CSV cuando la tabla pasaba a la siguiente (las Letras rotan cada mes: la del 03/11 a 6 y 12 meses habría desaparecido en la pasada del 01/12 si el Excel aún no traía noviembre) y, con ella, lo que solo da la web: precios medio y mínimo, vencimiento y liquidación.

- **Memoria**: cada pasada lee su CSV anterior (`datos/subastas_letras.csv` de `--salida`); las filas que vinieron de la web y cuya subasta ya no está en la tabla del Tesoro se tratan como si siguieran en ella (como antes, la web manda sobre el Excel cuando hablan de la misma subasta).
- **Protección**: antes de escribir, el CSV nuevo se compara con el anterior por fila completa. En Letras una subasta es una fecha y un plazo: cada fila anterior sigue igual o está actualizada; la que desaparecería se conserva tal cual y el flujo avisa (`::warning::` y `control_csv` en `ultima.json`). El registro de cada pasada lista las filas actualizadas (columna a columna), conservadas y nuevas.
- **Escritura atómica** del CSV y del JSON (temporal y cambio de nombre).
- `--recuperar CSV` añade las subastas de otro CSV de este colector que falten en el anterior; `--comparar CSV` (sin red) compara el CSV publicado con otro por fila completa.
- **Sin cambio de formato**: mismas columnas; con los mismos datos, el CSV sale idéntico byte a byte y la huella no cambia.

Pruebas (`pruebas_letras.py`, 24 comprobaciones): el CSV real que servía el servidor el 21/11/2026 (`pruebas_tesoro/subastas-letras-servidor-2026-11-21.csv`, 1.107 filas), sus cuatro filas de la web como tabla del Tesoro y el Excel reconstruido desde ese CSV: pasada igual (idéntico byte a byte); rotación del 01/12 (control: sin memoria se pierden las dos del 03/11; con memoria siguen iguales, y una unión externa con `pandas` por fila completa lo confirma); llegada del Excel con noviembre; una fila que el Excel deja de traer; recuperación con `--recuperar` y comprobación con `--comparar`. Dos mutaciones (sin memoria, sin protección) hacen fallar alguna comprobación.
