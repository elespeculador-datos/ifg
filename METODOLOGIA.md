# Índice de Fricción Global (IFG) — Metodología

**Versión 0.11.0** · Documento actualizado el 20 de octubre de 2026
Publicado por **el especulador.com**

> **Estado del índice: preliminar.** Las reglas están congeladas y versionadas,
> y la serie histórica está publicada, pero el IFG **no se presenta todavía
> como referencia citable**. Pasará a 1.0.0 cuando acumule un año de episodios
> genuinamente fuera de muestra y cumpla sus umbrales sin que se toque nada.
> El motivo está explicado sin rodeos en la sección 10.

---

## 1. Qué mide el IFG, y qué no

El IFG mide **la fricción geopolítica transmitida a los mercados**: en qué
grado los precios de los activos están reflejando tensión geopolítica, no
tensión financiera genérica.

El criterio de diseño que gobierna todas las decisiones de este documento es
uno: **el índice debe distinguir una caída de bolsa por resultados, tipos o
crédito de una caída por tensión geopolítica.** Un índice que sube en
cualquier episodio de aversión al riesgo no aporta nada que no diga ya el VIX.

De ahí que casi todos los componentes sean **diferenciales** y no niveles. El
central es el diferencial entre el crudo y el cobre: un shock de oferta
encarece el petróleo y hunde el cobre, mientras una expansión económica sube
los dos. Ese contraste es la firma que se busca.

**Lo que el IFG no es:**

- No es un índice de aversión al riesgo. Su correlación con el VIX en
  variaciones es de −0,03 (sección 10).
- No es una previsión. No anticipa nada: describe el estado presente.
- No es una señal de compra ni de venta. Ver sección 14.
- No es el GPR de Caldara e Iacoviello con pasos extra. Correlaciona con él a
  0,38 en niveles, que es lo que se buscaba: medir el mismo fenómeno sin ser
  una copia.

---

## 2. Componentes

Once componentes, agrupados por el canal de fricción que capturan.

| Componente | Construcción | Fuente |
|---|---|---|
| **energia** | z(crudo) − z(cobre), normalizado por √2 | `BZ=F` (Brent) empalmado con `CL=F` (WTI); `HG=F` |
| **vol_energia** | nivel logarítmico de la volatilidad implícita del crudo | `^OVX` |
| **refugios** | media de: oro/bolsa, −CHF, −JPY | `GC=F`, `^GSPC`, `EURCHF=X`, `EURJPY=X` |
| **defensa** | cesta de defensa europea / Stoxx 600 | RHM.DE, BA.L, HO.PA, LDO.MI, AM.PA, IDR.MC; `^STOXX` |
| **prima** | bono español 10a − Bund 10a, mitad nivel y mitad variación | fuente externa en cascada |
| **transporte** | (IAG + Amadeus) / IBEX 35 | `IAG.MC`, `AMS.MC`, `^IBEX` |
| **fletes** | cesta de petroleros / mercado | `FRO`, `DHT`, `NAT` |
| **grano** | trigo | `ZW=F` |
| **gas** | TTF europeo | `TTF=F` |
| **gdelt** | proporción de eventos de conflicto, media móvil de 3 días | GDELT |
| **gpr** | índice GPR diario | Caldara e Iacoviello, Reserva Federal |

Convención de signo: **todos** los componentes se orientan de forma que valor
más alto significa más fricción. El franco y el yen entran con signo
invertido, porque un EURCHF a la baja significa franco fuerte, es decir,
fricción.

### Dos aclaraciones sobre los componentes, que no son menores

**`vol_energia` tiene una sola pata, no dos.** La especificación original
preveía OVX + VSTOXX. El sondeo de fuentes del 18 de octubre de 2026 confirmó
que el símbolo del VSTOXX (`^V2TX`) **no devuelve datos** en la fuente
utilizada. El componente es, en la práctica, la volatilidad implícita del
crudo y nada más.

**`defensa` excluye a Airbus y Safran a propósito.** Su negocio es
mayoritariamente civil y contaminarían el componente con el ciclo
aeronáutico, que además se mueve en sentido contrario al bloque de transporte.

**`fletes` usa cotizaciones de navieras, no tarifas de flete.** Las tarifas
del Baltic Exchange no son de acceso libre, de modo que se usa la apuesta del
mercado sobre la tarifa en vez de la tarifa. Se eligen petroleros y no
graneleros ni contenedores: el flete de crudo responde a cierres de estrecho,
sanciones y desvíos de ruta, que es lo que aquí interesa, mientras el granelero
responde al ciclo de materias primas y el contenedor al ciclo comercial.

**`defensa` mezcla divisas.** Las rentabilidades de la cesta se toman en
moneda local, de modo que BAE (en peniques) ignora el efecto divisa. Es
aceptable en un ratio sectorial relativo, pero se declara.

---

## 3. La fórmula, paso a paso

### 3.1 Transformación de cada serie

Modo **mixto**, mitad y mitad:

```
transformar(s) = 0,5 · z( s(t)/s(t−5) − 1 )  +  0,5 · z( s(t) − media60(s) )
```

La primera pata es el **impulso**: la variación a 5 sesiones. La segunda es el
**estado**: la desviación respecto a la media de 60 sesiones. Las dos se
estandarizan antes de mezclarse, porque el estado es mucho más volátil que el
impulso y si no se lo comería.

### 3.2 Neutralización del factor de mercado

```
residuo = s − β(t) · mercado,    β estimada en ventana móvil de 250 sesiones
                                 (mínimo 120)
mercado = ^GSPC
```

**Por qué esto es imprescindible y no cosmético.** Un ratio no elimina el
riesgo de mercado salvo que numerador y denominador tengan beta parecida. El
ratio oro/bolsa tiene beta cercana a −1: no filtra la bolsa, es una posición
corta de bolsa encubierta, y sube en **cualquier** caída. Para cumplir el
criterio de diseño de la sección 1 hay que retirar explícitamente la parte del
componente explicada por el mercado y quedarse con el residuo.

### 3.3 Estandarización

```
z = (residuo − media750(residuo)) / desv750(residuo),   recortado a ±4
```

Ventana de 750 sesiones, unos tres años, con un mínimo de 375 para emitir
valor. El recorte a ±4 desviaciones evita que un dato erróneo mande sobre el
índice; afecta a menos del 0,7 % de las sesiones de cualquier componente.

### 3.4 Agregación

Aquí está la decisión que **más se aparta de la especificación original**, y
conviene leerla con atención.

El compuesto diario se calcula proyectando el vector de z-scores del día sobre
una dirección de referencia, y escalando por el coseno del ángulo entre
ambos:

```
d        = dirección de referencia, unitaria
d_dia    = d restringida a los componentes disponibles ese día, renormalizada
proy     = Σ  z_i · d_dia_i / ‖d_dia‖
coseno   = proy / ‖z‖
compuesto = proy · |coseno|
```

El factor del coseno es lo que hace que un día en que **todos** los
componentes apuntan a fricción puntúe más que un día con la misma magnitud
repartida de cualquier manera. Se usa el valor absoluto del coseno para que un
día que apunta justo al revés de la firma puntúe negativo, y no positivo por
doble cambio de signo.

### 3.5 Los pesos: el índice pondera IGUAL los once componentes

**La dirección de referencia `d` es el vector de pesos iguales:** 1/√11 en
cada componente, es decir, **9,1 % de peso efectivo para cada uno**.

Esto hay que decirlo con todas las letras porque el repositorio contiene un
diccionario `PESOS` con valores distintos —20 para energía, 15 para fletes,
4,5 para prima, transporte y GPR— y **ese diccionario no gobierna el índice**.
Solo se usa para dos cosas: medir la cobertura diaria (sección 5) y calcular
la línea base de media ponderada con la que se compara el agregador.

| Componente | Peso en el diccionario | Peso efectivo en el índice |
|---|---|---|
| energia | 18,2 % | **9,1 %** |
| fletes | 13,6 % | **9,1 %** |
| grano, gas, vol_energia, refugios, defensa, gdelt | 9,1 % | **9,1 %** |
| prima, transporte, gpr | 4,5 % | **9,1 %** |

**Por qué pesos iguales.** No es desidia: es el resultado de la validación.
Cuando se intentó estimar la dirección a partir de los datos de calibración,
todo lo que rendía fuera de muestra venía de los pesos iguales y nada de la
dirección aprendida. Una dirección estimada sobre 11 componentes y un puñado
de episodios es un ejercicio de sobreajuste con buena presentación. Los pesos
iguales no estiman nada, así que no hay nada que sobreajustar.

**Consecuencia que el lector debe conocer:** la tabla de pesos de la
especificación original del proyecto (energía 25, volatilidad 20, refugios
20…) describe una intención de diseño, no el índice que se publica. El índice
que se publica pondera igual.

### 3.6 Escala 0–100

```
z_compuesto = compuesto / σ_expansiva(compuesto)
IFG         = 100 / (1 + e^(−z_compuesto))
```

σ se calcula de forma **expansiva** —toda la historia conocida hasta la fecha,
nunca posterior— con un mínimo de 750 observaciones.

**Por qué logística y no percentil.** El percentil histórico produce una
distribución uniforme por construcción: con los tramos de la sección 6, el
índice estaría en «Extrema» el 10 % de las sesiones, unos 25 días al año, y la
palabra dejaría de significar nada. La logística da una distribución
acampanada en la que los extremos son raros de verdad y la escala no depende
del tamaño de la muestra. Las frecuencias observadas están en la sección 6.

### 3.7 Suavizado

Se calcula una media exponencial de 3 sesiones del índice, que se publica como
**línea de tendencia del gráfico**.

**El suavizado no es el índice.** Hasta la versión 0.9.0 el valor publicado y
el tramo se calculaban sobre la serie suavizada. Se corrigió en la 0.10.0 por
una razón de principio: no se suaviza una medición y después se llama medición
al suavizado. El valor del día es el dato; el suavizado es una lectura de su
tendencia. Medido sobre la serie actual, el suavizado rebaja la amplitud en
4,5 puntos de media y hasta 13,1 en el peor caso, y ese peor caso cambia el
veredicto de la prueba de sensibilidad (sección 10).

---

## 4. Fuentes y licencias

| Fuente | Qué aporta | Licencia / condiciones |
|---|---|---|
| Yahoo Finance | precios de materias primas, divisas, índices y acciones | uso sujeto a sus condiciones |
| GDELT Project | flujo diario de eventos de conflicto | datos abiertos |
| **GPR de Caldara e Iacoviello** (Reserva Federal) | ancla de nivel y validación externa | **Creative Commons BY**: uso permitido citando a los autores |
| Prima de riesgo | diferencial España–Alemania a 10 años | fuente externa en cascada |

**Cita obligada de la fuente externa principal:** Dario Caldara y Matteo
Iacoviello, *Measuring Geopolitical Risk*, Board of Governors of the Federal
Reserve System. Serie diaria descargada de
`matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls`.

El GPR se publica con datos diarios pero **se actualiza solo los lunes**. El
tratamiento de ese desfase está en la sección 5.

---

## 5. Calendario, festivos y datos ausentes

**Calendario de referencia: las sesiones del IBEX 35.** El índice existe para
leerse desde la bolsa española, de modo que su calendario es el del IBEX. Si
esa serie faltara, se usa la unión de sesiones de todas las fuentes.

**Arrastre limitado a 3 sesiones.** Cada componente se reindexa al calendario
y su último valor se arrastra un máximo de tres sesiones. El límite es
deliberado: sin él, una serie que deja de publicarse seguiría inyectando su
último valor indefinidamente y el índice parecería vivo cuando en realidad
estaría congelado.

**El GPR se arrastra, no se interpola.** Interpolar parece más fino y es un
*look-ahead* encubierto: el valor de un miércoles saldría de promediar la
muestra del lunes anterior con la del lunes siguiente, que todavía no existe
cuando se publica. Se detectó en pruebas que, al llegar esa muestra, el valor
ya publicado se movía hasta 2 puntos. Arrastrando, cada día usa la última
lectura conocida y nada se revisa a posteriori.

**Reparto del peso ausente.** Si un componente no tiene dato un día, la
dirección de referencia se renormaliza sobre los disponibles. El índice no se
interrumpe, pero queda registrada la **cobertura**: la fracción del peso
nominal disponible ese día.

**Días marcados «parcial».** Si la cobertura baja de 0,70, la sesión se marca
como parcial en la serie publicada. La cobertura se publica para **todas** las
sesiones, de modo que cualquiera puede descartar las que no le sirvan.

---

## 6. Tramos

| Tramo | Rango | Frecuencia observada |
|---|---|---|
| Calma | 0 – 20 | 6,4 días/año |
| Normal | 20 – 50 | 115,7 días/año |
| Tensión | 50 – 75 | 118,2 días/año |
| Alta | 75 – 90 | 10,5 días/año |
| Extrema | 90 – 100 | 4,2 días/año |

Los tramos se asignan sobre el **valor crudo**, no sobre el suavizado.

Las frecuencias son las observadas en la serie completa 2010–2026, y son
coherentes con lo que la calibración logística predecía antes de medirlas
(unos 3–4 días al año en «Extrema»). Se publican porque son el control de
sanidad de la escala: si «Extrema» se activara 25 días al año, la palabra
perdería su autoridad editorial.

Nótese que «Calma» se activa muy poco. El índice rara vez baja de 20.

---

## 7. Publicación

- **Hora: 03:15 de Madrid**, de lunes a viernes.
- **Por qué de madrugada y no a las 8:30:** la hora de corte queda coherente
  con el cierre de Wall Street de la víspera, y el texto editorial de cada
  mañana necesita el valor ya publicado.
- **Infraestructura:** el cálculo se ejecuta fuera de WordPress, en una tarea
  programada que publica dos archivos JSON y la serie en CSV. Nunca en PHP
  dentro de la web: el cálculo pesado penalizaría cada visita y una tarea
  disparada por tráfico no es fiable para una hora fija.
- **Si una fuente cae**, la publicación sigue con los componentes disponibles
  y la cobertura lo refleja. Si el cálculo no produce ningún valor, no se
  publica nada: una ficha en blanco informa menos que un dato de ayer
  rotulado como de ayer.

### Archivos publicados

| Archivo | Contenido |
|---|---|
| `ifg.json` | foto del día: valor, variación, tramo, cobertura, descomposición |
| `ifg_serie_12m.json` | doce meses para el gráfico |
| `ifg_serie.csv` | **serie histórica completa**, dato abierto |
| `componentes.csv` | z-scores de cada componente, para reproducibilidad |
| `revisiones.csv` | deriva observada en cada ejecución, con la versión que la midió |
| `correcciones.csv` | correcciones aplicadas a valores provisionales |
| `revision_version.md` | nota de discontinuidad del último cambio de versión |
| `historico/` | series de versiones anteriores, archivadas |

---

## 8. Política de revisiones

Esta sección es la que convierte el IFG en una serie utilizable por terceros,
así que es explícita.

### 8.1 Tres estados

| Estado | Cuándo | ¿Puede cambiar? |
|---|---|---|
| `definitivo` | cobertura completa | **No. Nunca.** |
| `provisional` | falta algún componente y está dentro de la ventana | Sí: es su razón de existir |
| `definitivo_incompleto` | salió de la ventana sin completarse | No, y queda marcado como lo que es |

**La ventana es de 5 sesiones.** Cubre los dos plazos reales de las fuentes:
una caída de precios se resuelve en uno o dos días hábiles, y GDELT publica su
muestra semanal dentro de los siete naturales siguientes. Más ventana no
recupera casi nada y retrasa el cierre; menos deja fuera la mitad de los
casos.

### 8.2 Por qué existen los provisionales

Porque la inmutabilidad, aplicada sin matices, protege los errores. El 9 y el
12 de octubre de 2026 se publicaron con un componente ausente y quedaron
congelados con un valor degradado, porque la regla no distinguía entre un dato
completo y un dato incompleto. Un valor al que le faltaba una fuente no
debería haber nacido inmutable.

### 8.2 bis Qué cuenta como cobertura: el arrastre no

Las series no llegan todas a la vez, así que un componente sin dato ese día se
rellena con su último valor, un máximo de tres sesiones. Eso mantiene vivo el
índice y **no cambia**: el valor de un día con unas entradas dadas es el mismo
desde la 0.10.0.

Lo que cambia en la 0.11.0 es que ese valor arrastrado **ya no cuenta como
cobertura**, cuando lo que se está arrastrando es una entrega pendiente. Antes
sí contaba, y la consecuencia no era cosmética: cobertura completa significa
cerrar la fila como definitiva ese mismo día, así que el dato real llegaba
cuando la fila ya era inmutable. El 14, 15 y 16 de octubre de 2026 se
publicaron con el GPR del día 13 arrastrado y cobertura 1,00; el lunes
siguiente, con los valores reales de la Reserva Federal encima de la mesa, el
recálculo se separaba 10,14 puntos de lo publicado y nada podía corregirlo.
Era la misma patología de 8.2 entrando por la puerta que la cobertura no
vigilaba.

**Hay dos clases de arrastre y solo una descuenta cobertura**, porque son
cosas distintas:

| Clase | Ejemplo | ¿Llegará el dato? | ¿Cuenta como cobertura? |
|---|---|---|---|
| Hueco permanente | festivo en Nueva York: el cobre no imprime en una sesión hábil del IBEX | No, nunca | **Sí.** Arrastrar es el tratamiento correcto y el único posible |
| Entrega pendiente | el GPR no ha publicado su semana; el BCE va con un día; un proveedor caído | Sí, con fecha de esa sesión | **No.** La fila nace provisional y se corrige al llegar |

El criterio que las separa sale de los datos, sin lista de componentes escrita
a mano: se mira si la fecha arrastrada cae más allá del último dato propio de
ese componente. Más allá del final de su serie es una fuente que aún no ha
llegado ahí; dentro de su rango es un agujero interior, o sea el festivo.

La distinción no es un detalle. Medido sobre la serie completa, descontar todo
arrastre habría marcado **439 sesiones** (el 10 %) como incompletas para
siempre, sin que ninguna corrección pudiera llegar jamás; descontar solo la
entrega pendiente afecta a **1 sesión**.

### 8.3 Qué se publica de cada revisión

- Toda corrección aplicada a un provisional se anota en `correcciones.csv`
  con el valor anterior, el nuevo y la fecha.
- La **deriva** —la diferencia entre lo que el recálculo de hoy daría y lo que
  está publicado, medida solo sobre filas cerradas— se publica en
  `revisiones.csv` en cada ejecución, para que cualquiera la audite. Cada fila
  lleva la versión con la que se midió: una deriva de la 0.9.0 y una de la
  0.10.0 no son la misma magnitud y el archivo no debe invitar a sumarlas.
- Medir la deriva no basta, porque un número en un CSV no lo lee nadie. La
  publicación **se avisa a sí misma** —sin detenerse, porque un dato cerrado
  es inmutable— en dos casos, ninguno de ellos un umbral elegido a ojo:
  cuando el recálculo contradice el **tramo** de una sesión ya publicada, que
  es cuando la deriva tiene consecuencia editorial porque el índice se cita
  por su tramo; y cuando la deriva es **mayor que cualquiera registrada bajo
  la versión en curso**, que avisa de lo que no tiene precedente y se calla
  en cuanto ese nivel deja de ser excepcional.
- Un cambio de reglas obliga a recalcular la serie completa, archivar la
  anterior en `historico/` y publicar una nota de discontinuidad medida. La
  verificación automática de estabilidad detiene la publicación si una fila
  cerrada cambia de valor por cualquier otra vía.

---

## 9. Reproducibilidad

**El IFG no es reproducible partiendo de las fuentes, y no por un defecto.**
Los datos de origen no son inmutables: el proveedor de precios devuelve series
ajustadas y reescribe su histórico con cada dividendo, y GDELT rellena huecos
hacia atrás. Quien recalcule mañana obtendrá números distintos.

Por eso se publica `componentes.csv` con los z-scores exactos con los que se
calculó cada día. **Cualquiera puede coger esa tabla, aplicar la fórmula de la
sección 3 y obtener exactamente el valor publicado.** Eso es lo que separa un
índice reproducible de uno que hay que creerse.

---

## 10. Validación

### 10.1 El marco, fijado de antemano

Cuatro pruebas con umbrales **fijados antes de ver un solo resultado**. Si el
índice no los cumple, se corrige la fórmula, no el umbral.

| Prueba | Qué comprueba | Umbral |
|---|---|---|
| **A. Sensibilidad** | ¿sube en los hitos geopolíticos mayores? | ≥ 70 % de aciertos |
| **B. Especificidad** | ¿se queda quieto en caídas de bolsa no geopolíticas? | ≤ 30 % de falsos positivos |
| **C. Independencia** | ¿se distingue del VIX y del GPR? | corr. VIX en variaciones ≤ 0,60; corr. GPR en niveles entre 0,25 y 0,90 |
| **D. Estructura** | ¿los pesos efectivos se parecen a los nominales? | diagnóstico, sin umbral |

La prueba B es la importante. Sin ella, cualquier índice de aversión al riesgo
aprueba la A y no aporta nada.

Un hito se considera detectado si el índice supera 75 en una ventana de −2 a
+10 sesiones alrededor del evento. La lista de 23 hitos y 17 controles se fijó
antes de medir, y los controles se eligieron **por su causa documentada**
—monetaria, crediticia, sanitaria, de microestructura o de política interna—
nunca por cómo responde el índice.

### 10.2 Resultados sobre la serie 0.10.0

| Prueba | Resultado | Umbral | |
|---|---|---|---|
| A. Sensibilidad | 8 de 11 = **73 %** | ≥ 70 % | cumple |
| B. Falsos positivos | 3 de 17 = **18 %** | ≤ 30 % | cumple |
| C. Corr. VIX (variaciones) | **−0,03** | ≤ 0,60 | cumple |
| C. Corr. GPR (niveles) | **+0,38** | 0,25 – 0,90 | cumple |

### 10.3 Por qué esto NO basta para llamarlo referencia citable

Los cuatro umbrales se cumplen, y aun así el índice sigue en 0.10.0. El motivo
es que **la muestra de validación está agotada**: esos 23 hitos se han mirado
tantas veces al calibrar que ya no miden capacidad predictiva, sino ajuste. Un
resultado favorable sobre datos vistos veinte veces no es evidencia.

Se exploró el atajo de validar hacia atrás, con episodios de 1996–2009 nunca
usados. **El sondeo de fuentes lo descartó:** el cobre y el trigo arrancan en
2000, los cruces del euro en 2003, la prima en 2004; sumado el calentamiento
de la normalización, no hay serie utilizable antes de 2009. Ninguno de los
hitos mayores de aquel periodo resulta evaluable.

**Queda por tanto una sola vía limpia: la validación prospectiva.** El índice
pasará a 1.0.0 cuando acumule un año de episodios nuevos y cumpla los umbrales
sin que se toque nada. El protocolo está pre-registrado y publicado en el
repositorio, con la muestra, los umbrales y las reglas de ejecución fijados de
antemano: una sola evaluación, sin iteración y con publicación incondicional
del resultado, incluido el suspenso.

---

## 11. Limitaciones declaradas

No son letra pequeña. Son el perfil real del instrumento.

**11.1 Una crisis sostenida se vuelve invisible.** La normalización usa una
ventana móvil de 750 sesiones. En el pico de la crisis del gas europea, con el
TTF en máximos históricos, esa ventana ya había absorbido seis meses de
precios altos y el componente marcó solo 1,8 desviaciones: el índice no lo
detectó. **El IFG mide aceleraciones de la fricción, no niveles sostenidos de
fricción.** Es inherente al método y no se arregla ajustando pesos.

**11.2 Cuando falla la especificidad, falla a lo grande.** Los tres falsos
positivos están los tres en tramo «Extrema» o «Alta»: el pánico de la Fed de
diciembre de 2018 (95,6), la pandemia de marzo de 2020 (92,2) y la rebaja de
*rating* de Fitch (85,7). El índice cumple el umbral agregado, pero un lector
que vea que el IFG marcó 92 durante la pandemia tendrá razón en preguntar.

**11.3 Tres hitos mayores que no detecta.** El referéndum del Brexit (máximo
62), el ataque a Abqaiq (69) y el pico de la crisis del gas (67).

- En el Brexit **el índice se comporta bien**: la capa de precios no se movió
  en absoluto, porque el Brexit no dejó firma de fricción geopolítica en los
  canales que el IFG mide. Cabe sostener que el episodio está mal clasificado
  como hito geopolítico. No se ha reclasificado: quitar un hito que falla
  mejora la tasa sin mejorar el índice.
- Abqaiq es más grave, porque es el mayor shock de oferta de crudo del periodo
  y la energía debería capturarlo. El componente de energía marcó 2,0
  desviaciones, el valor más alto de todos los hitos examinados, pero las
  capas lentas diluyeron la señal.

**11.4 `vol_energia` tiene una sola pata.** Ver sección 2.

**11.5 La serie no es homogénea en cobertura.** Entre 2010 y 2014 la cobertura
media ronda 0,82; alcanza el 100 % el 11 de junio de 2021, cuando entra el
gas. El TTF no existía antes de octubre de 2017 y eso no tiene arreglo. La
cobertura se publica para cada sesión.

**11.6 Dos discontinuidades metodológicas declaradas.** El crudo usa WTI
reencadenado antes de julio de 2007, y el factor de mercado cambió de un ETF
mundial al S&P 500 en la versión 0.10.0. Ambas están documentadas en la
sección 12.

---

## 12. Historial de versiones

Las reglas están congeladas y versionadas. Todo cambio se anuncia, se numera y
obliga a recalcular la serie completa, archivando la anterior.

### 0.11.0 — 20 de octubre de 2026

Un valor arrastrado que espera entrega deja de contar como cobertura, de modo
que la fila nace provisional en vez de definitiva y se corrige cuando la
fuente publica. Ver 8.2 bis.

No cambia ni un peso, ni una ventana, ni un umbral, ni la fórmula: el
compuesto y las contribuciones de cada día son idénticos a los de la 0.10.0.
Lo que cambia es la política de revisiones, y por eso lleva número de versión
y obliga a recalcular la serie entera. La serie 0.10.0 queda archivada en
`docs/historico/`.

Consecuencia para la validación prospectiva: el reloj del año de episodios
fuera de muestra se reinicia, igual que con cualquier cambio de versión.

### 0.10.0 — 18 de octubre de 2026

Cuatro cambios. Los tres primeros corrigen defectos.

1. **Factor de mercado:** de un ETF mundial que cotiza desde marzo de 2008 al
   S&P 500, con historia desde 1927. La fecha de salida a bolsa del ETF se
   propagaba, a través de la neutralización de beta, al inicio de **todos** los
   componentes. Efecto medido: la cobertura de 2010 pasa de 0,15 a 0,82.
2. **Inicio de la muestra:** de 2007 a 2000. Estaba recortando series que
   tenían más historia disponible.
3. **Crudo empalmado:** Brent donde existe, WTI reencadenado antes de julio de
   2007. El empalme se hace sobre rentabilidades y no sobre niveles: el
   diferencial Brent–WTI ha superado los 25 dólares, y pegar los niveles
   habría introducido un salto artificial que el índice habría leído como un
   pico de fricción.
4. **El valor oficial y el tramo pasan al valor crudo.** Ver sección 3.7.

Discontinuidad medida: cambian de valor 4.273 de 4.293 sesiones, con un cambio
absoluto medio de 2,7 puntos y un máximo de 47,0; 828 sesiones cambian de
tramo. La serie 0.9.0 queda archivada en `historico/`.

### 0.9.0 — 10 de octubre de 2026

Primera versión con reglas congeladas. Introduce la política de provisionales
y el archivo de componentes.

---

## 13. Licencia y citación

**La serie histórica es un dato abierto**, publicada en CSV bajo licencia
**Creative Commons BY 4.0**. Puede reutilizarse, redistribuirse y analizarse,
incluso con fines comerciales, citando la fuente.

**Fórmula de citación:**

> el especulador.com, *Índice de Fricción Global*, versión 0.11.0,
> consultado el [fecha]. https://elespeculador.com/indices/friccion-global/

Lo que no es abierto no es el dato: son el desglose por componente del día, las
alertas y la lectura de impacto sobre el IBEX 35.

Si se reutiliza la serie, debe citarse también la fuente externa del componente
GPR, como se indica en la sección 4.

---

## 14. Encuadre legal

Todo el contenido relacionado con el IFG es **informativo y educativo**.

**No constituye asesoramiento financiero ni recomendación de inversión.** El
índice se presenta como una lectura del estado del mercado, **jamás como una
señal de compra o de venta**. No predice rentabilidades ni movimientos de
precios, y no debe utilizarse como base única de ninguna decisión de
inversión.

el especulador.com no es un asesor de inversiones registrado y no mantiene
relación de asesoramiento con los lectores del índice.
