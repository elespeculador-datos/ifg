# Expectativas de los hogares españoles (indicador 20c)

Cada día hábil a las 11:30 (hora de Madrid), el servidor smpro-datos-1 (`servidor/ejecutar.sh expectativas`, ver `DESPLIEGUE.md`) descarga del portal de datos del BCE la encuesta de expectativas de los consumidores (conjunto CES, medianas ponderadas, mensual desde abril de 2020) para España, la zona euro de la encuesta (once países, código Z18, desde abril de 2022), Alemania, Francia e Italia, y publica en `$ESPEC_DATOS_DIR/expectativas/` (https://datos.elespeculador.com/expectativas/):

- `fragmento-wp.html`: la lectura del mes (inflación esperada a doce meses con variaciones y percentil, inflación percibida frente al IPC real del INE, expectativas a tres y cinco años), la tabla de países, el acierto de hace un año, la tabla de lo demás que esperan los hogares (vivienda, ingresos, gasto, crecimiento, paro, hipoteca), un gráfico SVG de tres años y el método, entre `<!-- expectativas:inicio HUELLA -->` y `<!-- expectativas:fin -->`;
- `index.html`: página propia de la salida;
- `datos/ultima.json` (versión 1.0.2) y `datos/serie.csv` (todas las series, formato largo con nombre).

La encuesta sale una vez al mes (el BCE publica el mes T hacia finales de T+1); la pasada diaria es una sola petición y el fragmento solo cambia cuando entra un mes nuevo.

Pregunta del lector: ¿qué inflación creen que han sufrido y esperan los hogares españoles, cuánto se equivocan, y qué esperan de su casa, su sueldo, el paro y su hipoteca?

Fuentes y licencias:
- **BCE, Consumer Expectations Survey** (claves `CES.M.<área>.ALL.T.<variable>.NUM_VAR.WM`; variables C1020 percibida 12 m, C1120 esperada 12 m, C1220 3 años, E2020 5 años, C1150_UNCERT incertidumbre, C2120 vivienda, C3220 ingresos, C6120 gasto, C4020 crecimiento, C4031 paro esperado, C5111 tipo hipotecario; áreas ES, Z18, DE, FR, IT; comprobadas en el portal el 18/11/2026). Política de reutilización del SEBC verificada el 02/11/2026: citar la fuente, no modificar las series, declarar los cálculos propios.
- **INE, IPC general interanual**, tomado de `ahorro/datos/serie.csv` (serie `ipc`) si está al lado de la salida (o en `--ipc`); CC BY 4.0 verificada el 02/11/2026. Sin él, la brecha y el acierto no se publican y se avisa.

Método: medianas ponderadas tal como las publica el BCE. Variaciones a un mes y a doce meses en puntos porcentuales; percentil «débil» desde el inicio de la serie (caso de control contra scipy). Brecha de percepción = inflación percibida − IPC real del mismo mes. Acierto a doce meses = expectativa de hace doce meses − IPC real del mes de la encuesta. Gráfico: esperada (España y zona euro), percibida e IPC real, 36 meses. Sin predicción ni recomendación.

Reglas: si el portal no responde (cuatro reintentos), falta la expectativa o la percepción de España, hay valores de inflación fuera de −20 % a 60 % o el último mes tiene más de 120 días de desfase, el script se para sin publicar y `servidor/ejecutar.sh` abre la incidencia `expectativas-fallido`; con más de 75 días solo avisa. Sin cambio de huella (mes, valores de España y de la zona euro, IPC) no reescribe; `--forzar` regenera.

Comprobaciones sin red: `python expectativas/pruebas_expectativas.py` (31 comprobaciones con un CSV simulado del portal y un serie.csv de ahorro: lectura y paradas, fichas con variaciones y percentil, brecha, acierto, zona euro desde 2022, desfase, sin IPC, huella, fragmento, JSON, CSV, no reescritura).

Validado con datos reales el 18/11/2026 (flujo `expectativas-validacion`, ejecución 44391478221; en el ejecutor no hay IPC al lado, en el servidor sí): encuesta de septiembre de 2026, España espera 3,8 % a doce meses (+0,7 p.p. en el mes; percentil 73 desde 2020; máximo 5,6 % en marzo de 2022), percibe 4,4 %, 3,2 % a tres años y 3,0 % a cinco; zona euro 3,1 %, Alemania 2,9 %, Francia 2,9 %, Italia 4,4 %; vivienda +4,1 %, ingresos +1,8 %, paro esperado 10,5 %, hipoteca 3,5 %. Verificados sobre el dato, no estimados.

Entrega a Tecnología: fragmento `https://datos.elespeculador.com/expectativas/fragmento-wp.html` (marcas `expectativas:inicio`/`expectativas:fin`), JSON `https://datos.elespeculador.com/expectativas/datos/ultima.json`; pasada diaria 11:30 L-V; dato nuevo cuando cambia la huella (una vez al mes). Página de WordPress en borrador: /expectativas-de-los-hogares/. Dependencias: `requests pandas`.

1.0.2 (25/11/2026): la frase de la brecha de percepción ya no termina en «p.p..» (doble punto). La huella incluye la versión, así que la página 9400 se reescribe en la primera pasada tras la fusión.
