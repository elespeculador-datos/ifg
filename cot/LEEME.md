# Posicionamiento especulativo, COT de la CFTC (indicador 20a)

Los sábados y los lunes a las 07:00 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh cot`, ver `DESPLIEGUE.md`) descarga de la API pública de la CFTC (Socrata, conjunto «Commitments of Traders, Legacy, futures only», `6dca-aqww`) las posiciones semanales desde 2015 de 18 futuros, por código de mercado (los nombres cambiaron en 2022; los códigos no), y publica en `$ESPEC_DATOS_DIR/cot/` (https://datos.elespeculador.com/cot/):

- `fragmento-wp.html`: lectura de la semana (mercados más largos y más cortos en términos de tres años, extremos), tabla mercado por mercado (neto de los especuladores, variación semanal y a cuatro semanas, neto sobre interés abierto, índice COT de tres años, percentil de tres años, lectura, neto de los comerciales), cuatro gráficos SVG de tres años (euro, oro, WTI, S&P 500) y método, entre `<!-- cot:inicio HUELLA -->` y `<!-- cot:fin -->`;
- `index.html`: página propia de la salida;
- `datos/ultima.json` (versión 1.0.0) y `datos/serie.csv` (netos semanales de todos los mercados desde 2015).

Pregunta del lector (trader de tntbolsa; contenido premium según la decisión de Federico del 18/11/2026): ¿cómo están colocados los grandes especuladores en los futuros que mueven a los mercados y dónde hay un extremo?

Mercados (código CFTC): euro 099741, libra 096742, yen 097741, índice dólar 098662, bitcoin 133741, oro 088691, plata 084691, platino 076651, cobre 085692, WTI 067651, gas natural 023651, S&P 500 E-mini 13874A, Nasdaq 100 mini 209742, nota a 10 años 043602, VIX 1170E1, trigo SRW 001602, maíz 002602, soja 005602. Comprobados en la API el 19/11/2026.

Fuente y licencia: CFTC, Commitments of Traders, obra del Gobierno federal de EE. UU. (dominio público; anotado en el catálogo el 02/11/2026; la nota de copyright por escrito es opcional y no bloquea). Las cifras se reproducen sin modificar; neto, índice COT y percentiles son de El Especulador (CC BY 4.0).

Método: neto de los no comerciales = largos − cortos (futuros, sin opciones); variación frente al informe anterior y frente a cuatro semanas antes; neto sobre el interés abierto; índice COT = (neto − mínimo de 156 semanas) / (máximo − mínimo) × 100; percentil «débil» del neto en 156 semanas (caso de control contra scipy); ambos solo con 52 semanas de serie. Lectura: «largo extremo» o «corto extremo» desde 90 o hasta 10 en el índice o el percentil; «largo» o «corto» desde 75 o hasta 25; en medio, «zona media». Neto de los comerciales a título informativo. Sin predicción ni recomendación: «describe cómo están colocados, no lo que hará el precio».

Reglas: si la API no responde (cuatro reintentos), la respuesta no es JSON o está vacía, faltan columnas, hay posiciones negativas o el último informe tiene más de 30 días, el script se para sin publicar y `servidor/ejecutar.sh` abre la incidencia `cot-fallido`; con más de 12 días solo avisa (la CFTC retrasa el informe en festivos). Un mercado que falte en la respuesta se avisa y los demás salen. Sin cambio de huella (fecha del informe y netos) no reescribe; `--forzar` regenera.

Comprobaciones sin red: `python cot/pruebas_cot.py` (31 comprobaciones con un JSON simulado de la API y valores conocidos: lectura y paradas, netos, variaciones, índice COT en el máximo y en mitad del rango, percentil contra scipy, tramos, desfase, mercado ausente, huella, fragmento con cuatro gráficos, JSON, CSV, no reescritura).

Validado con datos reales el 19/11/2026 (flujo `cot-validacion`, ejecución 44419014071): informe del 10/11/2026, 18 mercados, 10.972 observaciones desde el 06/01/2015; extremos cortos de tres años en euro (−136.396 contratos, índice 6), plata, WTI, gas natural y nota a 10 años; yen, índice dólar y bitcoin largos. Verificados sobre el dato, no estimados.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/cot/fragmento-wp.html` (marcas `cot:inicio`/`cot:fin`), JSON `https://datos.elespeculador.com/cot/datos/ultima.json`; pasada sábados y lunes 07:00 (la CFTC publica los viernes a las 15:30 de Washington; el lunes recoge los retrasos por festivo); dato nuevo cuando cambia la huella (una vez por semana). Página de WordPress en borrador: /posicionamiento-especulativo-cot/ (zona premium cuando exista). Dependencias: `requests pandas`.
