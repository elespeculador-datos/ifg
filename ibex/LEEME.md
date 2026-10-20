# Estadística del IBEX 35

Cada día hábil, después del cierre, el flujo `ibex-diario` descarga los cierres oficiales del IBEX 35 de la API pública de BME (la misma que usa su web; da los últimos cinco años) y publica:

- `docs/ibex/index.html`: página con el último cierre, la rentabilidad del año, del mes y a 12 meses, el máximo histórico (al cierre e intradía), la rentabilidad de cada año desde 1993 y de cada mes de los últimos cinco años;
- `docs/ibex/datos/*.csv` y `ultima.json`: las mismas cifras en abierto, con licencia CC BY 4.0;
- `docs/ibex/fragmento-wp.html`: las tablas en HTML limpio entre `<!-- ibex:inicio … -->` y `<!-- ibex:fin -->`, que un escenario de Make copia en la página «El IBEX 35 en cifras» de elespeculador.com.

Los años anteriores a la ventana de BME salen de `ibex/historico_anual.csv`, la serie verificada de El Especulador. En los años que se solapan, el script compara su cálculo con esa serie y se para si difieren más de 0,05 puntos. No se publica la serie diaria de cotizaciones, solo cifras derivadas.

Es independiente del IFG y del rastreador de cortos: solo lee y escribe `ibex/` y `docs/ibex/`. Si BME no responde o cambia el formato, el flujo abre una incidencia con la etiqueta `ibex-fallido`.

Prueba local: `python ibex/estadistica.py --local cierres.csv` (columnas `fecha,cierre[,maximo]`).
