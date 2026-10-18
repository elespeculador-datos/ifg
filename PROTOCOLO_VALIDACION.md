# Protocolo de validación del IFG — versión 1, pre-registro

**Estado: PRE-REGISTRO. Este documento debe quedar congelado por un commit
ANTES de descargar un solo dato nuevo.** Si se escribe o se modifica después
de ver los resultados, no vale nada: sería exactamente el procedimiento que
agotó la muestra actual.

Fecha de redacción: 18 de octubre de 2026.
Índice al que se aplica: Índice de Fricción Global, versión 0.9.0.

---

## 1. El problema que este protocolo resuelve

`config.py` ya lo dice, y dice lo correcto:

> `# 0.9.0 y no 1.0.0 a propósito: el índice NO está publicado como referencia`
> `# citable. Supera el umbral de falsos positivos pero no el de aciertos`
> `# (67 % frente al 70 %), y la muestra de validación está agotada tras`
> `# demasiadas iteraciones. Pasa a 1.0.0 cuando se acumule un año de`
> `# episodios genuinamente fuera de muestra y los cumpla sin tocar nada.`

La muestra está quemada. Los 11 hitos mayores de `config.HITOS` se han mirado
tantas veces al calibrar que ya no miden nada: cualquier cambio que mejore el
acierto sobre ellos es ajuste a la muestra, no mejora del índice. Esto no se
arregla con más análisis de los mismos datos.

Hasta ahora el plan era esperar un año a que ocurrieran episodios nuevos.
**No hace falta esperar: hay una década de episodios sin usar, hacia atrás.**

## 2. Por qué existe esa década y por qué está cerrada

La serie publicada arranca en 2010 con una cobertura del 15 % de los
componentes, y no alcanza el 100 % hasta el 11 de junio de 2021. La causa no
es falta de datos. Es esta:

`FACTOR_MERCADO = "acwi"` es la serie con la que se neutraliza la beta de
**todos** los componentes, dentro de `limpio()` en `indice.py`. ACWI es un
ETF que empezó a cotizar el **28 de marzo de 2008**. Su fecha de salida se
propaga, componente a componente, a través de la neutralización y del
z-score posterior.

Medido, no supuesto: sustituyendo el factor por el Stoxx 600 (que empieza el
3 de enero de 2007, solo 15 meses antes), los componentes adelantan su
primera sesión entre **411 y 467 días**:

| Componente | con ACWI | con Stoxx 600 | Adelanto |
|---|---|---|---|
| energía | 2011-12-20 | 2011-06-01 | 202 días |
| refugios | 2011-11-08 | 2010-09-15 | 419 días |
| defensa | 2011-12-06 | 2010-08-26 | 467 días |
| transporte | 2011-11-18 | 2010-09-03 | 441 días |
| fletes | 2011-11-08 | 2010-08-26 | 439 días |
| grano | 2011-11-08 | 2010-09-23 | 411 días |

El adelanto es casi uno a uno con la historia añadida al factor. Dicho de
otro modo: **la historia utilizable del índice está determinada por la fecha
de salida a bolsa de un ETF elegido como variable de control.** Eso es un
defecto de especificación, y el argumento vale con independencia de lo que el
cambio haga con las tasas de acierto. Por eso corregirlo no es ajustar la
curva.

## 3. La corrección

Sustituir el factor de mercado por la serie de bolsa amplia con mayor
historia disponible, y descargar los componentes desde esa fecha.

**Antes de elegir ninguna fecha hay que sondear qué historia da realmente
cada fuente** (`sonda_fuentes.py`). Hay límites duros conocidos que no se
pueden salvar y que deben declararse:

| Serie | Límite | Naturaleza del límite |
|---|---|---|
| `gas_ttf` (TTF) | 2017-10 | el contrato no existía antes |
| `iag` | 2011-01 | la empresa no existía (fusión BA–Iberia) |
| `amadeus` | 2010-04 | salida a bolsa |
| `acwi` | 2008-03 | salida a bolsa del ETF |
| `ovx` | 2007-05 | el índice no existía (lo creó el CBOE en 2007) |
| `brent` (BZ=F) | 2007-07 | profundidad de la fuente; WTI (CL=F) llega mucho más atrás |

Consecuencia honesta: la extensión hacia atrás **no recupera el índice
completo**. Recupera el núcleo —energía, refugios, divisas, grano, fletes,
defensa, prima— con una cobertura parcial pero muy superior al 15 % actual.
Sustituir Brent por WTI en el tramo antiguo es una discontinuidad
metodológica que hay que declarar, no esconder.

Objetivo realista a sondear: serie homogénea desde **2000-2003**, no desde
1995.

## 4. La muestra nueva: hitos pre-registrados 1996–2009

**Esta lista se fija AHORA, antes de que exista un solo valor del índice en
esas fechas.** Clasificación `mayor` según el mismo criterio que la lista
vigente: episodio de fricción geopolítica de primer orden con canal de
transmisión a los mercados.

| Fecha | Evento | Mayor |
|---|---|---|
| 1996-03-08 | Crisis de los misiles del estrecho de Taiwán | no |
| 1998-08-07 | Atentados contra embajadas de EE. UU. en Kenia y Tanzania | no |
| 1998-12-16 | Operación Zorro del Desierto (bombardeo de Irak) | no |
| 1999-03-24 | Bombardeo de la OTAN sobre Yugoslavia | sí |
| 2000-10-12 | Atentado contra el USS Cole | no |
| 2001-09-11 | Atentados del 11 de septiembre | sí |
| 2002-12-02 | Huelga de PDVSA / colapso del crudo venezolano | no |
| 2003-03-20 | Invasión de Irak | sí |
| 2004-03-11 | Atentados del 11-M en Madrid | sí |
| 2005-07-07 | Atentados de Londres | no |
| 2006-07-12 | Guerra del Líbano (Israel-Hezbolá) | sí |
| 2006-10-09 | Primera prueba nuclear de Corea del Norte | no |
| 2008-08-08 | Guerra de Rusia y Georgia | sí |
| 2009-06-13 | Protestas poselectorales en Irán | no |

Siete hitos mayores, ninguno usado jamás en la calibración. El 11-M importa
especialmente: es el único episodio de la lista con impacto directo y
documentado sobre el IBEX, que es el mercado al que el índice presta
atención preferente.

## 5. Los controles pre-registrados 1997–2009

Caídas de bolsa cuyo origen documentado **no** es geopolítico. El índice no
debe dispararse aquí. Esta prueba es la que separa el IFG de un indicador de
aversión al riesgo genérica.

| Fecha | Evento | Origen |
|---|---|---|
| 1997-10-27 | Crisis asiática | financiero / cambiario |
| 1998-08-17 | Suspensión de pagos de Rusia y colapso de LTCM | crediticio |
| 2000-04-14 | Pinchazo de las tecnológicas | burbuja de valoración |
| 2002-07-23 | Escándalos contables (WorldCom) | gobierno corporativo |
| 2005-08-29 | Huracán Katrina | natural |
| 2007-08-09 | Congelación de los fondos de BNP Paribas | crediticio |
| 2008-09-15 | Quiebra de Lehman Brothers | crediticio |
| 2008-10-10 | Pánico de octubre de 2008 | crediticio |
| 2009-03-09 | Mínimo del mercado | macroeconómico |

Katrina merece un comentario, porque es el control más exigente de toda la
batería: fue un **shock de oferta de energía sin causa geopolítica**. Si el
índice se dispara con Katrina, no está midiendo fricción geopolítica: está
midiendo precios de la energía. Es el mejor test del constructo que hay
disponible.

## 6. Umbrales: los mismos, sin tocar una cifra

Se usan los de `config.UMBRALES`, tal como están hoy:

- nivel de activación: 75
- ventana del hito: (−2, +10) sesiones
- tasa mínima de acierto sobre hitos mayores: 70 %
- tasa máxima de falsos positivos: 30 %
- correlación máxima con el VIX en variaciones: 0,60
- correlación con el GPR en niveles: entre 0,25 y 0,90

**No se modifica ninguno.** Si el índice no los cumple sobre la muestra
nueva, el índice no vale y se corrige la fórmula, o se descarta.

## 7. Decisiones que hay que cerrar ANTES de ejecutar

Están abiertas hoy. Cambiarlas después de ver los resultados de la muestra
nueva sería quemarla igual que se quemó la anterior. Cada una necesita
argumento a priori, no empírico.

### 7.1 Qué valor es el índice oficial

Hoy el valor publicado y el tramo salen de `ifg_suavizado` (línea 479 de
`indice.py`), la media exponencial de 3 días. Medido sobre la muestra actual,
el suavizado cuesta 4,8 puntos de amplitud de media y 13,8 en el peor caso,
y ese peor caso decide la prueba: el ataque iraní del 13 de abril de 2024
pasa de 78,4 en crudo a 64,5 suavizado.

Argumento a priori, independiente del resultado: un índice cuya función es
**detectar** no debería publicar como titular una versión retrasada y con los
picos rebajados de sí mismo. Las dos cifras ya se calculan y ya se publican
(`valor` y `valor_crudo` en `ifg.json`), así que no es un cambio de fórmula
sino de etiqueta: cuál de las dos es el índice y cuál es la línea de
tendencia del gráfico.

**Pendiente de decisión del responsable del índice.**

### 7.2 La clasificación del Brexit

El Brexit figura como hito mayor y el índice no lo detecta (máximo 62,5).
La autopsia por componentes (`autopsia_hitos.py`) muestra por qué: la capa de
precios no se movió en absoluto. Energía 0,04 · defensa −0,10 · fletes −0,15
· grano −0,60. Lo único que reaccionó fue transporte (4,00, en el tope, por
el desplome de IAG) y refugios (2,32).

Es decir: el Brexit no dejó firma de fricción geopolítica en los canales que
el índice mide. Cabe sostener que el índice se está comportando
correctamente y que el hito está mal clasificado — es un episodio
político-financiero, no un shock de fricción geopolítica con transmisión
física.

**Pero esta reclasificación solo es legítima si se decide antes de la prueba
nueva y por el constructo, nunca por el resultado.** Si se decide, el
resultado antiguo (no detectado, con el Brexit como mayor) se conserva
publicado en la metodología.

### 7.3 El peso de GDELT

El recálculo sin GDELT da 84,5 en la ventana de Abqaiq, frente a los 70,9 de
la serie publicada: **GDELT, con 10 puntos de peso, es lo que impide detectar
el mayor shock de oferta de crudo del periodo.** El z-score de energía en
Abqaiq es 1,99, el más alto de todos los hitos examinados, incluidos Ucrania
(0,85) y Hamás (1,18). El componente de precios funcionó; la capa lenta lo
diluyó.

La especificación del proyecto dice que las capas lentas «aportan contexto y
calibración, nunca son el motor del índice». Con 15 puntos entre GDELT y GPR,
pueden decidir una detección en el margen, que es ser motor.

Reducir el peso de GDELT *porque* mejora Abqaiq sería ajuste. La pregunta
legítima y a priori es distinta: **¿mide GDELT el mismo constructo?** GDELT
cuenta volumen mundial de eventos de conflicto; el IFG mide transmisión de
fricción geopolítica a los mercados. Un ataque con drones a una refinería
saudí no mueve el volumen mundial de conflicto y sí mueve el crudo. Son dos
cosas distintas.

**Pendiente de decisión del responsable del índice.**

## 8. Limitación estructural que no se corrige: se declara

En el pico de la crisis del gas europea (26 de agosto de 2022, con el TTF en
máximos históricos) el componente de gas marcó un z-score de 1,71 y el índice
68,5: no detectado.

La causa no es un error. El z-score se calcula sobre ventana móvil de 750
sesiones, y en agosto de 2022 esa ventana ya había absorbido seis meses de
precios altos. El pico dejó de ser estadísticamente extremo.

**Una crisis sostenida se vuelve invisible para el índice.** Es inherente a
normalizar sobre ventana móvil y no se arregla tocando pesos. Tiene que
figurar como limitación declarada en el documento de metodología, en estos
términos: *el IFG mide aceleraciones de la fricción, no niveles sostenidos de
fricción.*

Si en el futuro se quiere corregir, exige un cambio estructural —un anclaje
de nivel, o una normalización doble— con versión nueva y validación
prospectiva propia. No se improvisa ahora.

## 9. Reglas de ejecución

Esto es lo que convierte el protocolo en protocolo:

1. **Una sola evaluación.** La batería se ejecuta **una vez** sobre la muestra
   1996–2009, con la fórmula congelada y las decisiones del punto 7 ya
   cerradas. No hay segunda pasada.
2. **Sin iteración.** Si el resultado no gusta, no se retoca nada y se vuelve
   a probar. Se acepta el resultado o se descarta el índice.
3. **Publicación incondicional.** El resultado se publica tal cual salga,
   incluido el suspenso. Un índice que solo publica sus validaciones
   favorables no es citable, es publicidad.
4. **Orden estricto:** congelar este documento por commit → cerrar las
   decisiones del punto 7 → sondear fuentes → descargar → recalcular →
   ejecutar la batería una vez → publicar.
5. **La muestra nueva queda quemada tras la ejecución.** A partir de ahí, la
   única validación limpia que queda es la prospectiva, y entonces sí aplica
   el plan original: un año de episodios nuevos sin tocar nada.

## 10. Qué significa cada resultado

| Resultado sobre la muestra nueva | Lectura | Acción |
|---|---|---|
| Cumple los cuatro umbrales | El índice funciona fuera de muestra | Pasa a 1.0.0 y se publica como referencia citable |
| Cumple especificidad, falla sensibilidad | Mide bien, detecta poco | Se publica como indicador de régimen, **no** como detector de eventos, y se dice así |
| Falla especificidad | Es un indicador de aversión al riesgo con pasos extra | Se descarta la premisa del proyecto |
| Resultados contradictorios entre eras | La serie no es homogénea | Se publica solo el tramo homogéneo y se declara |

---

Contenido informativo y educativo. No constituye asesoramiento financiero ni
recomendación de inversión. El índice es una lectura del estado del mercado,
nunca una señal de compra o de venta.
