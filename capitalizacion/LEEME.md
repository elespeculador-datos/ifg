# Las empresas más grandes de la bolsa española

Clasificación diaria de las empresas españolas del mercado continuo por capitalización al
cierre, con la variación de cada una en el año, las que más suben y más bajan, las cinco
que más suben y bajan del IBEX 35 y las extranjeras que cotizan en España.

- Script: `ranking.py` (nombres cortos en `nombres.py`). Salida: `docs/capitalizacion/`
  (`fragmento-wp.html` para la página https://elespeculador.com/empresas-mas-grandes-bolsa-espanola/,
  `index.html`, `datos/empresas.csv`, `datos/AAAA.csv`, `datos/ultima.json`).
- Flujo: `.github/workflows/capitalizacion-diario.yml`, de martes a sábado a las 05:30 UTC.
- Fuente: API pública de BME (lista de cotizadas SIBE, ficha e histórico de cada valor).
  Sin licencia abierta: se pide citar «El Especulador, a partir de datos de BME».

Comprobaciones: 35 valores del IBEX y más de 500.000 millones en total (si no, no publica);
valores sin cotizar en dos semanas y salidas a bolsa del año, marcados y fuera de las listas;
variación de BME contrastada con el histórico (tolerancia 2 puntos); listas solo con
empresas de más de 100 millones. Si una cotizada nueva no está en `nombres.py`, el flujo
avisa y usa el nombre de BME.

Estado (21/10/2026): preparado y probado con datos reales en la rama `capitalizacion-borrador`,
sin publicar, a la espera de que BME aclare su licencia de datos. Página en borrador: 8615. Escenario de Make que la
actualiza: 10013817 (inactivo). Puesta en marcha: fusionar esta rama, lanzar el flujo, activar 10013817 y publicar 8615.
