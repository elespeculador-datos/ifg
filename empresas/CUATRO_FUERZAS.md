# «Las cuatro fuerzas»: cómo las hace Datos (propuesta, 22/11/2026; aún sin ejecutar)

Qué es: la exposición de cada empresa a **tipos, energía, divisa y política** según sus propias cuentas. No es sensibilidad estadística (eso es del Mapa de sensibilidades) ni una predicción. Para la plantilla v2 de las fichas de valores (encargo de Tecnología del 22/11/2026).

## 1. Documento fuente

- **IBEX 35:** el informe financiero anual (IFA) del último ejercicio cerrado de cada empresa (no todas cierran el 31 de diciembre), depositado en la CNMV: cuentas anuales consolidadas auditadas e informe de gestión consolidado, con su estado de información no financiera. Cada cifra cita el documento depositado, su página y el enlace a la CNMV. El informe semestral (IFS) solo si la Redacción quiere una actualización a mitad de año.
- **Licencia:** nota legal de la CNMV (verificada el 02/11/2026): reproducción fiel citando la fuente; cálculos propios permitidos si se declaran como tales.
- **EE. UU.** (cuando llegue el colector de la SEC): el formulario 10-K en EDGAR (SEC, información pública; verificada el 21/11/2026), mismas notas.

## 2. Qué cifras (propuesta para que la Redacción cierre la lista)

Las mismas para todas las empresas, con una variante para bancos y aseguradoras. Se copia lo que la empresa declara; si no lo declara, la cifra queda vacía y la ficha la oculta.

| Fuerza | Cifra propuesta | Dónde está en las cuentas |
|---|---|---|
| Tipos | % de la deuda financiera a tipo fijo o cubierta | nota de deudas financieras o de gestión del riesgo de tipo de interés (NIIF 7) |
| Tipos | efecto declarado de +100 pb en el resultado antes de impuestos | la misma nota (análisis de sensibilidad de la NIIF 7) |
| Tipos (bancos) | sensibilidad declarada del margen de intereses a +100 pb | informe de gestión o información con relevancia prudencial |
| Divisa | % de los ingresos fuera de la zona euro | nota de información por segmentos y áreas geográficas (NIIF 8) |
| Divisa | efecto declarado de una variación del 10 % del euro | nota de riesgo de tipo de cambio (NIIF 7) |
| Energía | consumo de energía del grupo, o peso de la actividad energética en los ingresos | estado de información no financiera (consumo); nota de segmentos (ingresos) |
| Política | % de ingresos o de resultado de actividades reguladas | nota de segmentos o informe de gestión |
| Política | gravámenes y tributos extraordinarios del ejercicio (importe) | nota de situación fiscal |

Cada cifra lleva: valor tal como lo publica la empresa (o cálculo propio declarado, por ejemplo un porcentaje sobre el total), unidad, ejercicio, fuente (empresa y documento), página, enlace y fecha del documento. El campo `texto` describe la cifra sin valorarla.

## 3. Doble comprobación

1. Dos extracciones independientes: dos agentes reciben el mismo documento y la misma lista cerrada de cifras, sin ver el trabajo del otro. Cada uno anota cifra, unidad, página y la frase exacta de la que sale.
2. Se publica solo si coinciden cifra, unidad y página. Si no coinciden, o uno de los dos no la encuentra, la cifra va a la Redacción con las dos lecturas y la página, y no se publica hasta que la Redacción decida.
3. `verificado_por`: «doble extracción coincidente» o «Redacción (discrepancia resuelta)»; `verificado_el`: la fecha.
4. Control antes de cargar las 35: cinco empresas con sus cifras comprobadas a mano por la Redacción. Si una de las dos extracciones falla en más de una cifra de cada cuarenta, se corrigen las instrucciones antes de seguir.

## 4. Dónde queda

- **Conjunto de datos:** `empresas/cuatro_fuerzas.csv` en el repositorio, una fila por empresa, fuerza e indicador (`isin, fuerza, indicador, cifra, unidad, texto, ejercicio, fuente, pagina, enlace, fecha, verificado_por, verificado_el`). Cada cambio entra por PR con su documento y página: el historial de git guarda cada versión.
- **Lecturas:** las dos lecturas de cada empresa y ejercicio, con las discrepancias y cómo se resolvieron, en `empresas/cuatro_fuerzas/lecturas/<ISIN>-<ejercicio>.csv`, para auditoría.
- **Publicación:** el bloque `cuatro_fuerzas` de `https://datos.elespeculador.com/empresas/<ISIN>.json`, y el registro de cambios del servidor (`empresas/cambios.csv`: fecha, ISIN, campo, antes, después, fuente), que anota cada cifra que cambia.

## 5. Calendario y coste

- Arranque: cuando la Redacción cierre la lista de cifras (modelos del 25/11) y Cumplimiento dé su visto bueno (27/11).
- Carga del IBEX 35: unas dos semanas (35 empresas por unas 8 cifras, con doble lectura). Actualización: una vez al año, cuando cada empresa deposite sus cuentas anuales; unos dos días.
- Horas de Federico: 0. Gasto en datos: 0 (documentos públicos).
