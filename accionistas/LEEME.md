# Accionistas del IBEX 35

Los accionistas significativos de cada empresa del IBEX 35, tal y como figuran en el
registro de participaciones significativas de la CNMV (última notificación de cada
accionista, Real Decreto 1362/2007). La lista de las 35 sale de la lista de cotizadas de BME.

- Script: `accionistas/duenos.py --salida docs/accionistas`
- Flujo: `.github/workflows/accionistas-diario.yml` (05:45 UTC, martes a sábado)
- Salida (GitHub Pages): `docs/accionistas/` → `fragmento-wp.html` (entre las marcas
  `<!-- accionistas:inicio HUELLA -->` y `<!-- accionistas:fin -->`, con el marcado Dataset),
  `index.html`, `datos/accionistas.csv`, `datos/ultima.json`.
- La huella de la primera línea solo cambia si cambian los datos: el escenario de Make que
  actualiza la página de WordPress solo escribe cuando hay datos nuevos.
- Página de WordPress: /accionistas-ibex-35/ (borrador).

Notas:
- La CNMV no tiene enlaces fijos por NIF: cada vez se busca la entidad por nombre
  (formulario ASP.NET), se elige si hay varias y se sigue el enlace de un solo uso de la ficha.
  Si cambia el nombre de una empresa en la CNMV, hay que tocar `EMPRESAS`.
- Ferrovial (Países Bajos) y ArcelorMittal (Luxemburgo) no se toman de la CNMV: sus
  accionistas comunican al supervisor de su país.
- Condiciones de la CNMV: reproducción fiel, sin alterar; se permiten cálculos. Los nombres
  de los accionistas se reproducen como los publica la CNMV. Los enlaces a la CNMV abren en
  ventana nueva.
