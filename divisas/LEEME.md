# Divisas de exposición del IBEX (indicador 14)

Cada día hábil a las 16:40 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh divisas`, ver `DESPLIEGUE.md`) descarga del portal de datos del BCE los tipos de cambio de referencia del euro (conjunto EXR, diarios desde 2010) del real brasileño, el peso mexicano, la lira turca, el dólar y la libra, y publica en `$ESPEC_DATOS_DIR/divisas/` (https://datos.elespeculador.com/divisas/):

- `fragmento-wp.html`: lectura del día (cesta emergente y la divisa que más se mueve), tabla divisa por divisa (tipo por euro, variaciones a una semana, un mes, desde enero y doce meses, percentil de tres años con su zona, máximo y mínimo de 52 semanas), gráfico SVG de doce meses con base 100 y método, entre `<!-- divisas:inicio HUELLA -->` y `<!-- divisas:fin -->`;
- `index.html`: página propia de la salida;
- `datos/ultima.json` (versión 1.0.0) y `datos/serie.csv` (tipos diarios desde 2010, formato largo).

Pregunta del lector: ¿las divisas de los países donde ganan dinero las cotizadas españolas juegan a favor o en contra de sus resultados en euros, y cuánto se han movido?

Fuente y licencia: BCE, tipos de cambio de referencia del euro (`EXR.D.<divisa>.EUR.SP00.A`, API `data-api.ecb.europa.eu`, formato csvdata). Política de reutilización del SEBC verificada el 02/11/2026: citar la fuente, no modificar las series, declarar los cálculos propios. Los tipos se reproducen tal cual; la cesta, las variaciones y los percentiles son de El Especulador (CC BY 4.0). El BCE no publica referencia para el peso chileno, el peso colombiano, el sol peruano ni el peso argentino: quedan fuera y se dice.

Método: los tipos son unidades de divisa por euro; las variaciones se expresan siempre como movimiento de la divisa frente al euro (tipo anterior / tipo actual − 1), así una variación negativa es una divisa que se deprecia. Ventanas: 7, 30 y 365 días (último dato disponible hasta esa fecha) y desde el último dato del año anterior. Percentil «débil» del tipo en tres años (porcentaje de sesiones con el euro igual o más bajo) con zonas: ≥ 90 «zona más débil de tres años» de la divisa, ≥ 75 «débil», ≤ 25 «fuerte», ≤ 10 «zona más fuerte». Cesta emergente: media geométrica, a partes iguales, de las variaciones del real, el peso mexicano y la lira en cada ventana; se publica como variación y no como nivel para que la lira no domine una serie larga. Gráfico: valor en euros de cada divisa (inverso del tipo) con base 100 en el primer día de doce meses. Sin predicción ni recomendación.

Reglas: si el portal no responde (cuatro reintentos), falta alguna divisa, hay tipos no positivos o el último dato tiene más de diez días, el script se para sin publicar y `servidor/ejecutar.sh` abre la incidencia `divisas-fallido`; con más de cinco días solo avisa. Sin cambio de huella (fecha y tipos) no reescribe; `--forzar` regenera.

Comprobaciones sin red: `python divisas/pruebas_divisas.py` (33 comprobaciones con un CSV simulado del portal y valores conocidos: lectura y paradas, variaciones invertidas, desde enero, cesta geométrica, percentiles conocidos y caso de control contra scipy, desfase, huella, fragmento, JSON, CSV, no reescritura).

Validado con datos reales el 18/11/2026 (flujo `divisas-validacion`, ejecución 44389314392): tipos del 18/11/2026, BRL 6,3818, MXN 20,3738, TRY 55,3197, USD 1,0968, GBP 0,8329; cesta emergente −3,1 % en un mes y −3,4 % en doce meses; lira en percentil 92 de tres años (zona más débil), libra en percentil 8 (zona más fuerte). Verificados sobre el dato, no estimados.

Pendiente (versión 1.1, premium): tabla de exposición por empresa (qué divisas pesan en cada cotizada del IBEX) con la fuente de cada asignación (informe anual, nota de segmentos geográficos) y fecha; hasta que esté verificada empresa a empresa no se publica.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/divisas/fragmento-wp.html` (marcas `divisas:inicio`/`divisas:fin`), JSON `https://datos.elespeculador.com/divisas/datos/ultima.json`; pasada diaria 16:40 L-V (el BCE fija los tipos hacia las 16:00 CET); dato nuevo cuando cambia la huella. Página de WordPress en borrador: /divisas-del-ibex/. Dependencias: `requests pandas`.
