# -*- coding: utf-8 -*-
"""
Configuración del Índice de Fricción Global (IFG).

Todo lo que es decisión de diseño vive aquí. El resto del código no debe
contener constantes numéricas sueltas: si hay que cambiar algo, se cambia
en este fichero y se incrementa VERSION.

Convención de signo: TODOS los componentes se orientan de forma que
"valor más alto = más fricción geopolítica".
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Versionado (requisito 2 de la sección 4: reglas congeladas y versionadas)
# ---------------------------------------------------------------------------
VERSION = "0.10.0"
# REGLAS CONGELADAS. Componentes, pesos, agregador, umbrales y hora de corte
# quedan fijos. Cualquier cambio exige numerar una versión nueva y recalcular
# la serie entera.
#
# Sigue sin ser 1.0.0, y por el mismo motivo que antes: el índice NO está
# publicado como referencia citable, y la muestra de validación está agotada
# tras demasiadas iteraciones. Pasa a 1.0.0 cuando se acumule un año de
# episodios genuinamente fuera de muestra y los cumpla sin tocar nada. El
# sondeo de fuentes del 18 de octubre de 2026 descartó el atajo de validar
# hacia atrás: no hay historia suficiente (ver viabilidad_extension.py).
#
# ---------------------------------------------------------------------------
# CAMBIOS DE 0.9.0 A 0.10.0, con la serie recalculada entera
# ---------------------------------------------------------------------------
# Los tres primeros corrigen defectos; el cuarto aplica una decisión de
# diseño cerrada por argumento a priori en PROTOCOLO_VALIDACION.md, sección 7.
#
# 1. FACTOR_MERCADO pasa de "acwi" a "sp500". ACWI es un ETF que cotiza desde
#    el 28 de marzo de 2008 y se usaba para neutralizar la beta de TODOS los
#    componentes: su fecha de salida a bolsa se propagaba al inicio de cada
#    uno. Medido, sustituirlo por una serie 15 meses más antigua adelantaba
#    los componentes entre 411 y 467 días.
#
# 2. FECHA_INICIO_MUESTRA pasa de 2007 a 2000. Estaba recortando series que
#    tenían más historia: el cobre y el trigo existen desde agosto y julio de
#    2000, el oro desde agosto de 2000. Se tiraba el calentamiento gratis.
#
# 3. El crudo del tramo antiguo pasa a ser WTI empalmado con Brent. BZ=F solo
#    llega a julio de 2007 y era el cuello de botella del componente de
#    energía, que pesa 20. DISCONTINUIDAD DECLARADA: antes de 2007-07-30 el
#    componente usa WTI reencadenado sobre el primer nivel del Brent, de modo
#    que el empalme no introduce un salto de nivel.
#
# 4. El índice oficial y el tramo pasan a calcularse sobre el valor CRUDO. El
#    suavizado exponencial de 3 días se conserva y se publica como línea de
#    tendencia. No se suaviza una medición y después se llama medición al
#    suavizado: el valor del día es el dato y el suavizado es una lectura de
#    su tendencia. Valdría igual si el suavizado hubiera aprobado la
#    validación con holgura, que no la aprobaba (64 % frente al 70 % exigido,
#    mientras el crudo daba 73 %).
#
# EFECTO ESPERADO sobre la serie: cobertura de componentes del orden del 75 %
# en enero de 2010, frente al 15 % de la 0.9.0, y serie homogénea desde 2010
# en vez de desde junio de 2021. Los valores publicados cambian en toda la
# serie; la 0.9.0 se conserva archivada en docs/historico/.
FECHA_INICIO_MUESTRA = "2000-01-01"   # máxima historia disponible en la fuente
FECHA_INICIO_PUBLICACION = "2010-01-01"

# ---------------------------------------------------------------------------
# Ventanas de normalización
# ---------------------------------------------------------------------------
VENTANA_Z = 750          # sesiones (~3 años) para el z-score de cada componente
MIN_PERIODOS_Z = 375     # mínimo para emitir z-score (~1,5 años)
VENTANA_ESTADO = 60      # sesiones: media de referencia del "modo estado"
HORIZONTE_IMPULSO = 5    # sesiones: horizonte del "modo impulso" (5d del diseño)
CLIP_Z = 4.0             # winsorización de z-scores (evita que un outlier mande)
SUAVIZADO_TITULAR = 3    # span de la EMA para el valor de titular
MIN_COBERTURA_PESO = 0.70  # si hay menos peso disponible, el día se marca "parcial"

# Modo de transformación de los componentes de precios.
#   "impulso"  -> variación a 5 días (especificación original de la sección 3)
#   "estado"   -> desviación respecto a la media de 60 sesiones
#   "mixto"    -> 50 % impulso + 50 % estado  (recomendado, ver README)
MODO_TRANSFORMACION = "mixto"

# Neutralización del factor de mercado.
# Un ratio NO elimina el riesgo de mercado salvo que numerador y denominador
# tengan beta parecida. Oro/ACWI tiene beta cercana a -1: no filtra la bolsa,
# es una posición corta de bolsa encubierta, y sube en CUALQUIER caída. Para
# cumplir el criterio de diseño del proyecto hay que retirar explícitamente la
# parte del componente explicada por el mercado y quedarse con el residuo.
NEUTRALIZAR_BETA = True
FACTOR_MERCADO = "sp500"     # serie que representa el riesgo de mercado común
#
# Denominador del componente de refugios (oro / bolsa). Usa la MISMA serie que
# el factor de mercado, a propósito: un índice con dos referencias de bolsa
# distintas según el tramo no es comparable consigo mismo. Hasta la 0.9.0 era
# ACWI, y su fecha de salida a bolsa limitaba el componente igual que limitaba
# la neutralización.
DENOMINADOR_BOLSA = "sp500"
#
# Crudo: serie principal y respaldo para el tramo antiguo. El respaldo se
# reencadena sobre el primer nivel de la principal, así que el empalme no
# introduce un salto. DISCONTINUIDAD DECLARADA en la metodología.
CRUDO_PRINCIPAL = "brent"
CRUDO_RESPALDO = "wti"
#
# HISTORIA DEL DEFECTO QUE ESTO CORRIGE (resuelto en 0.10.0).
# ACWI es un ETF que cotiza desde el 28 de marzo de 2008, y esta serie se usa
# para neutralizar la beta de TODOS los componentes dentro de limpio(). Su
# fecha de salida a bolsa se propaga, a través de la neutralización y del
# z-score posterior, al inicio de cada componente: medido sustituyéndola por
# el Stoxx 600 (15 meses más de historia), los componentes adelantan su
# primera sesión entre 411 y 467 días, casi uno a uno con la historia añadida
# al factor. La era degradada de 2010-2011, con cobertura del 15-25 %, no es
# falta de datos: los precios están desde 2007. Es el coste de calentamiento
# de una variable de control mal elegida. Ver validacion_eras.py y la sección
# 11.1 de PROTOCOLO_VALIDACION.md.
#
# POR QUÉ ESTE CAMBIO NO PODÍA HACERSE SOLO AQUÍ. Cambiar esta constante
# altera el valor de toda la serie histórica. Tocada a secas, la ejecución
# diaria siguiente produce valores distintos para fechas ya publicadas,
# verificar_estabilidad.py falla —que es lo que tiene que hacer— y la
# publicación se detiene. De ahí que la 0.10.0 venga acompañada de
# republicar_version.py, que archiva la serie anterior, recalcula la completa
# y la sustituye en un acto deliberado y declarado. El flujo diario no puede
# hacer esto por accidente.
VENTANA_BETA = 250           # sesiones para estimar la beta móvil
MIN_PERIODOS_BETA = 120

# Escala final 0-100.
#   "percentil" -> percentil histórico. Distribución UNIFORME por construcción:
#                  con los tramos de la sección 3, el índice estaría en
#                  "Extrema" el 10 % de las sesiones, unos 25 días al año.
#   "logistica" -> logística sobre el z-score compuesto con parámetros
#                  congelados. Distribución acampanada: los extremos son
#                  raros de verdad y la escala no depende del tamaño de la
#                  muestra. Recomendada para un índice publicado.
MODO_ESCALA = "logistica"
LOGISTICA_PENDIENTE = 1.0  # sigmas del compuesto que llevan el índice a ~73
# Con pendiente 1,0 y compuesto aproximadamente normal:
#   Alta (>=75) a partir de +1,1 sigma   -> ~14 % del tiempo
#   Extrema (>=90) a partir de +2,2 sigma -> ~1,4 % (unos 3-4 días al año)
# La calibración definitiva se fija con datos reales y se congela.

# Cálculo del percentil final.
#   "expansivo" -> usa toda la historia hasta t (sin look-ahead, valor estable)
#   "movil"     -> ventana móvil VENTANA_PERCENTIL (más sensible, menos memoria)
MODO_PERCENTIL = "expansivo"
VENTANA_PERCENTIL = 1250   # solo se usa si MODO_PERCENTIL == "movil"
MIN_PERIODOS_PERCENTIL = 750

# ---------------------------------------------------------------------------
# Pesos (suman 100). Editables. Si un componente no tiene datos un día,
# su peso se reparte proporcionalmente entre los disponibles y queda registrado.
# ---------------------------------------------------------------------------
PESOS = {
    # --- Firma física: no reaccionan a sustos financieros (nuevos en v2) ---
    "fletes":        15,   # cesta de petroleros vs. mercado
    "grano":         10,   # trigo
    "gas":           10,   # TTF europeo (solo desde octubre de 2017)
    # --- Capa de precios heredada ---
    "energia":       20,   # Brent vs. cobre
    "vol_energia":   10,   # OVX + VSTOXX (VSTOXX opcional)
    "refugios":      10,   # oro/ACWI, CHF, JPY
    "defensa":       10,   # cesta defensa europea vs. Stoxx 600
    "prima":          5,   # España 10a - Bund 10a (opcional)
    "transporte":     5,   # IAG + Amadeus vs. IBEX
    # --- Capas lentas ---
    "gdelt":         10,   # proporción de eventos de conflicto (opcional)
    "gpr":            5,   # Caldara & Iacoviello (opcional)
}

# NOTA SOBRE LOS PESOS: solo gobiernan el agregador de media ponderada, que
# en v2 queda como línea base de comparación. El agregador por firma estima
# su propia dirección a partir de los datos de calibración y NO usa estos
# pesos. Se mantienen para poder comparar los dos en igualdad de condiciones.

# Componentes que pueden faltar sin invalidar el índice.
OPCIONALES = {"vol_energia_vstoxx", "prima", "gdelt", "gpr"}

# ---------------------------------------------------------------------------
# Tickers (Yahoo Finance). Los marcados como opcionales pueden fallar.
# ---------------------------------------------------------------------------
TICKERS = {
    # Energía / materias primas
    "brent":        "BZ=F",
    # WTI: respaldo del Brent para el tramo anterior a julio de 2007, que es
    # donde arranca BZ=F en esta fuente. CL=F llega hasta agosto de 2000.
    "wti":          "CL=F",
    "cobre":        "HG=F",
    # Volatilidad
    "ovx":          "^OVX",
    "vstoxx":       "^V2TX",    # rara vez disponible en Yahoo -> opcional
    "vix":          "^VIX",     # NO entra en el índice: solo para validar
    # Refugios
    "oro":          "GC=F",
    "acwi":         "ACWI",
    "eurchf":       "EURCHF=X",
    "eurjpy":       "EURJPY=X",
    # Referencias de bolsa
    "stoxx600":     "^STOXX",
    "ibex":         "^IBEX",
    # Factor de mercado de largo historial. SE DESCARGA PERO NO SE USA
    # TODAVÍA: ver la advertencia junto a FACTOR_MERCADO.
    "sp500":        "^GSPC",
    # Gas europeo (incorporación tardía: el TTF arranca en octubre de 2017)
    "gas_ttf":      "TTF=F",
    # Grano: corredores del mar Negro
    "trigo":        "ZW=F",
    # Transporte España
    "iag":          "IAG.MC",
    "amadeus":      "AMS.MC",
    "melia":        "MEL.MC",   # no entra en el índice: submarcador IBEX
}

# Cesta sintética de defensa europea, equiponderada en rentabilidades diarias.
# Motivo: EUAD no tiene historia suficiente para reconstruir desde 2010.
# Se excluyen Airbus y Safran a propósito: su negocio es mayoritariamente civil
# y contaminarían el componente con el ciclo aeronáutico, que además va en
# sentido contrario al bloque de transporte.
CESTA_DEFENSA = {
    "rheinmetall":  "RHM.DE",
    "bae":          "BA.L",
    "thales":       "HO.PA",
    "leonardo":     "LDO.MI",
    "dassault_av":  "AM.PA",
    "indra":        "IDR.MC",
}

# Cesta de fletes de petroleros, equiponderada en rentabilidades diarias.
# Las tarifas del Baltic Exchange no son de acceso libre, así que se usa la
# apuesta del mercado sobre la tarifa en vez de la tarifa. Las tres cotizan
# desde enero de 2007, de modo que el componente cubre todo el periodo.
# Se eligen petroleros y no graneleros ni contenedores: los graneleros
# responden al ciclo de materias primas y los contenedores al ciclo
# comercial, mientras que el flete de crudo responde a cierres de estrecho,
# sanciones y desvíos de ruta, que es lo que aquí se quiere medir.
CESTA_FLETES = {
    "frontline":    "FRO",
    "dht":          "DHT",
    "nordic":       "NAT",
}

# ---------------------------------------------------------------------------
# Fuentes externas (verificar URLs antes de congelar la metodología)
# ---------------------------------------------------------------------------
# GPR diario de Caldara & Iacoviello (Reserva Federal).
URL_GPR = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"

# Prima de riesgo. Se intentan varias fuentes en cascada (ver fuentes.py).
# El portal del BCE NO publica el rendimiento diario del bono español a 10
# años: las claves del dataset FM que se probaron primero daban 404.
BCE_BASE = "https://data-api.ecb.europa.eu/service/data/"
# Curvas de tipos de la zona euro: todos los bonos y solo los de máxima
# calificación. Su diferencia es una aproximación de crédito de la zona euro,
# no el diferencial España-Alemania. HIPÓTESIS POR VALIDAR.
BCE_CURVA_TODOS = "YC/B.U2.EUR.4F.G_N_C.SV_C_YM.SR_10Y"
BCE_CURVA_AAA = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
# Stooq publica rendimientos de deuda en CSV abierto. HIPÓTESIS POR VALIDAR.
STOOQ_BONO_ES = "10esy.b"
STOOQ_BONO_DE = "10dey.b"
# Fichero puesto a mano: dos columnas, fecha y prima en puntos básicos.
# Sirve una descarga del Banco de España. Es la vía que se usa primero.
RUTA_PRIMA_MANUAL = "datos/prima_manual.csv"

# GDELT: el backfill histórico es pesado (un fichero diario desde 2013).
# El script espera un parquet ya construido; si no existe, el componente
# se desactiva y su peso se reparte.
RUTA_CACHE_GDELT = "datos/gdelt_conflicto_diario.parquet"

# ---------------------------------------------------------------------------
# Agregación (novedad de la v2)
# ---------------------------------------------------------------------------
#   "media"     -> suma ponderada con los PESOS de arriba. Línea base de la v1.
#   "firma"     -> proyección sobre la dirección discriminante, estimada con
#                  la muestra de calibración. Mide si la CONFIGURACIÓN de los
#                  componentes coincide con la de un shock geopolítico.
#   "firma_cos" -> igual, multiplicada por el coseno con esa dirección: premia
#                  que además estén alineados, al modo del parámetro de orden
#                  de Vicsek. Un movimiento grande pero desalineado puntúa bajo.
# DECISIÓN TRAS LA VALIDACIÓN DE LA v2: se congela en pesos iguales.
# Estimar la dirección discriminante resultó ser sobreajuste puro: dentro de
# muestra separaba 38,9 puntos y fuera 2,9. Según se encogía hacia pesos
# iguales, lo de dentro se desplomaba y lo de fuera mejoraba, y entre el 50 %
# y el 100 % la validación quedaba plana. La estimación no aporta nada.
# Seleccionar componentes por su discriminación en calibración tampoco
# generalizó. Pesos iguales no tiene parámetros que sobreajustar.
MODO_AGREGACION = "iguales_cos"

# Frontera de la muestra partida. La dirección discriminante se estima SOLO
# con episodios anteriores a esta fecha; lo posterior es validación ciega.
FECHA_CORTE_CALIBRACION = "2020-01-01"

# Encogimiento de la dirección estimada hacia el vector de pesos iguales.
# 0 = dirección estimada pura; 1 = media equiponderada.
# Con once episodios de calibración y diez componentes, la dirección cruda
# tiene demasiados grados de libertad: encogerla a la mitad es una decisión
# tomada ANTES de ver resultados, no un parámetro que se ajusta después.
ENCOGIMIENTO_FIRMA = 1.0   # 1.0 = pesos iguales; se conserva por compatibilidad

# ---------------------------------------------------------------------------
# Tramos de lectura
# ---------------------------------------------------------------------------
TRAMOS = [
    (0,  20,  "Calma"),
    (20, 50,  "Normal"),
    (50, 75,  "Tensión"),
    (75, 90,  "Alta"),
    (90, 101, "Extrema"),
]

# ---------------------------------------------------------------------------
# HITOS: eventos de fricción geopolítica. El índice DEBE reaccionar aquí.
# Fijados antes de ver un solo resultado (requisito de la sección 7).
# "mayor" = episodio de primer orden; el test exige acierto sobre estos.
# ---------------------------------------------------------------------------
HITOS = [
    # fecha,       etiqueta,                                   mayor
    ("2010-05-06", "Crisis deuda griega / rescate",             False),
    ("2011-02-17", "Guerra civil de Libia",                     False),
    ("2011-03-11", "Fukushima",                                 False),
    ("2011-08-05", "Rebaja rating EE. UU. / prima española",    False),
    ("2012-07-24", "Pico prima de riesgo española",             True),
    ("2014-03-01", "Anexión de Crimea",                         True),
    ("2014-07-17", "Derribo del MH17",                          False),
    ("2015-11-13", "Atentados de París",                        True),
    ("2016-06-23", "Referéndum del Brexit",                     True),
    ("2017-08-08", "Crisis nuclear con Corea del Norte",        False),
    ("2018-03-22", "Inicio guerra comercial EE. UU.-China",     False),
    ("2019-09-14", "Ataque a Abqaiq (Arabia Saudí)",            True),
    ("2020-01-03", "Muerte de Soleimani",                       True),
    ("2021-03-23", "Bloqueo del canal de Suez",                 False),
    ("2021-08-15", "Caída de Kabul",                            False),
    ("2022-02-24", "Invasión de Ucrania",                       True),
    ("2022-08-26", "Pico de la crisis del gas europea",         True),
    ("2022-09-26", "Sabotaje del Nord Stream",                  False),
    ("2023-10-07", "Ataque de Hamás e inicio de la guerra",     True),
    ("2024-01-12", "Ataques en el mar Rojo / hutíes",           False),
    ("2024-04-13", "Ataque directo de Irán a Israel",           True),
    ("2024-10-01", "Segundo ataque iraní a Israel",             False),
    ("2025-06-13", "Ataque israelí a Irán / riesgo Ormuz",      True),
]

# ---------------------------------------------------------------------------
# CONTROLES: caídas de bolsa SIN origen geopolítico. El índice NO debe
# dispararse aquí. Este test es el que separa el IFG de un VIX disfrazado.
# ---------------------------------------------------------------------------
CONTROLES = [
    # Elegidos por su CAUSA, no por cómo responde el índice: cada uno es una
    # caída de bolsa cuyo origen documentado es monetario, crediticio,
    # sanitario, de microestructura o de política interna, nunca geopolítico.
    # Con solo tres controles anteriores a 2020 la calibración no se sostenía.
    ("2013-06-20", "Taper tantrum (monetario)"),
    ("2014-10-15", "Flash rally del Tesoro (microestructura)"),
    ("2015-08-24", "Devaluación del yuan / flash crash"),
    ("2016-01-20", "Pánico por crecimiento chino (macro)"),
    ("2017-05-17", "Caída por el memo de Comey (política interna)"),
    ("2018-02-05", "Volmageddon (estructura de volatilidad)"),
    ("2018-10-10", "Corrección de octubre por tipos (monetario)"),
    ("2018-12-24", "Pánico por endurecimiento de la Fed"),
    ("2019-08-14", "Inversión de la curva / miedo a recesión"),
    ("2020-03-16", "Pandemia (shock sanitario, no geopolítico)"),
    ("2021-01-27", "Episodio GameStop / microestructura"),
    ("2021-09-20", "Evergrande (crédito inmobiliario chino)"),
    ("2021-11-26", "Ómicron (sanitario)"),
    ("2022-06-13", "Sorpresa de IPC y subidas de tipos"),
    ("2023-03-13", "SVB y Credit Suisse (crisis bancaria)"),
    ("2023-08-02", "Rebaja de rating de EE. UU. por Fitch (fiscal)"),
    ("2024-08-05", "Deshacer del carry trade del yen"),
]

# ---------------------------------------------------------------------------
# Umbrales de aceptación, fijados DE ANTEMANO (sección 7).
# Si el índice no los cumple, se corrige la fórmula, no los umbrales.
# ---------------------------------------------------------------------------
UMBRALES = {
    "nivel_activacion": 75,        # el índice debe superarlo en los hitos mayores
    "ventana_hito": (-2, 10),      # sesiones alrededor del hito
    "tasa_acierto_minima": 0.70,   # % de hitos mayores detectados
    "nivel_falso_positivo": 75,    # superarlo en un control es un falso positivo
    "tasa_falsos_maxima": 0.30,
    "corr_max_vix_variaciones": 0.60,   # por encima, el IFG es un VIX disfrazado
    "corr_min_gpr_niveles": 0.25,       # por debajo, no está midiendo geopolítica
    "corr_max_gpr_niveles": 0.90,       # por encima, es GPR con pasos extra
}
