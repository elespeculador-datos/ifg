# -*- coding: utf-8 -*-
"""
Muestra de validación 1996-2009. PRE-REGISTRO CONGELADO.

Este archivo contiene la lista de hitos y controles con los que se va a
validar el IFG fuera de muestra, redactada el 18 de octubre de 2026, ANTES de
que exista un solo valor del índice en esas fechas. Va en un módulo propio y
no dentro de config.py para que su diff sea limpio y su fecha de congelación
sea auditable por el historial de git.

NO SE TOCA DESPUÉS DE EJECUTAR LA VALIDACIÓN. Ni para añadir, ni para quitar,
ni para reclasificar. Si hiciera falta cambiar algo, se abre un pre-registro
nuevo con fecha nueva y se declara que el anterior quedó invalidado.

Ver PROTOCOLO_VALIDACION.md, secciones 4, 5 y 11.

-----------------------------------------------------------------------------
LÍMITE QUE SE DECLARA ANTES DE MEDIR NADA
-----------------------------------------------------------------------------
Buena parte de esta muestra NO va a ser evaluable, y se sabe a priori, por
hechos del calendario y no por resultados:

  - El euro no existe hasta el 1 de enero de 1999. EURCHF y EURJPY, que
    alimentan el componente de refugios, no pueden ir más atrás.
  - DHT Holdings sale a bolsa en 2005; la cesta de fletes queda incompleta
    antes de esa fecha.
  - El OVX lo crea el CBOE en 2007: la volatilidad energética no existe antes.
  - El TTF arranca en octubre de 2017; el gas europeo no entra nunca en este
    tramo.
  - El Brent de la fuente actual (BZ=F) empieza en 2007. Para el tramo antiguo
    hay que sustituirlo por WTI (CL=F), lo que es una discontinuidad
    metodológica declarada, no un detalle.

Por tanto, la expectativa realista —fijada aquí, antes de sondear— es que la
serie homogénea alcance hacia atrás hasta algún punto entre 2001 y 2003, y
que los hitos mayores efectivamente evaluables sean del orden de cinco:
el 11-S, la invasión de Irak, el 11-M, la guerra del Líbano y Georgia.

Cinco hitos mayores con un umbral del 70 % significa acertar cuatro de cinco.
Es una prueba gruesa, y hay que decirlo: con cinco eventos el intervalo de
confianza de una tasa es enorme. Pero es una prueba FUERA DE MUESTRA, y una
prueba gruesa limpia vale más que una prueba fina sobre datos ya mirados
veinte veces. La parte de especificidad, con nueve controles, es bastante
más informativa que la de sensibilidad.

Los hitos anteriores a la fecha que resulte del sondeo quedarán como no
evaluables. Se publican igualmente en el informe, marcados como tales, para
que conste que estaban pre-registrados y no se eligieron a posteriori.
"""

from __future__ import annotations

FECHA_PRE_REGISTRO = "2026-10-18"

# ---------------------------------------------------------------------------
# HITOS. "mayor" con el mismo criterio que config.HITOS: episodio de fricción
# geopolítica de primer orden con canal de transmisión a los mercados.
# ---------------------------------------------------------------------------
HITOS = [
    # fecha,        etiqueta,                                        mayor
    ("1996-03-08", "Crisis de los misiles del estrecho de Taiwán",   False),
    ("1998-08-07", "Atentados contra embajadas de EE. UU.",          False),
    ("1998-12-16", "Operación Zorro del Desierto",                   False),
    ("1999-03-24", "Bombardeo de la OTAN sobre Yugoslavia",          True),
    ("2000-10-12", "Atentado contra el USS Cole",                    False),
    ("2001-09-11", "Atentados del 11 de septiembre",                 True),
    ("2002-12-02", "Huelga de PDVSA / colapso del crudo venezolano", False),
    ("2003-03-20", "Invasión de Irak",                               True),
    ("2004-03-11", "Atentados del 11-M en Madrid",                   True),
    ("2005-07-07", "Atentados de Londres",                           False),
    ("2006-07-12", "Guerra del Líbano (Israel-Hezbolá)",             True),
    ("2006-10-09", "Primera prueba nuclear de Corea del Norte",      False),
    ("2008-08-08", "Guerra de Rusia y Georgia",                      True),
    ("2009-06-13", "Protestas poselectorales en Irán",               False),
]

# ---------------------------------------------------------------------------
# CONTROLES. Caídas de bolsa cuyo origen documentado NO es geopolítico.
# El índice no debe dispararse aquí.
# ---------------------------------------------------------------------------
CONTROLES = [
    # fecha,        etiqueta (origen del episodio)
    ("1997-10-27", "Crisis asiática (financiero/cambiario)"),
    ("1998-08-17", "Suspensión de pagos de Rusia y LTCM (crediticio)"),
    ("2000-04-14", "Pinchazo de las tecnológicas (valoración)"),
    ("2002-07-23", "Escándalos contables, WorldCom (gobierno corporativo)"),
    ("2005-08-29", "Huracán Katrina (natural)"),
    ("2007-08-09", "Congelación de los fondos de BNP Paribas (crediticio)"),
    ("2008-09-15", "Quiebra de Lehman Brothers (crediticio)"),
    ("2008-10-10", "Pánico de octubre de 2008 (crediticio)"),
    ("2009-03-09", "Mínimo del mercado (macroeconómico)"),
]

# KATRINA ES EL CONTROL MÁS EXIGENTE DE LA BATERÍA y por eso está aquí.
# Fue un shock de oferta de energía SIN causa geopolítica: el crudo y la
# gasolina se dispararon porque el huracán cerró refinerías y plataformas en
# el Golfo de México. Si el IFG se activa con Katrina, no está midiendo
# fricción geopolítica: está midiendo precios de la energía con pasos
# intermedios. Es el mejor test del constructo que permiten los datos.

# ---------------------------------------------------------------------------
# Las dos especificaciones pre-registradas (protocolo, sección 11.2).
# ---------------------------------------------------------------------------
ESPECIFICACIONES = {
    "E1": {
        "descripcion": "GDELT incluido, pesos de config.PESOS sin cambios",
        "usar_gdelt": True,
    },
    "E2": {
        "descripcion": "GDELT excluido, su peso repartido por el pipeline",
        "usar_gdelt": False,
    },
}

# Orden de preferencia a priori. Si las DOS cumplen los cuatro umbrales, gana
# la primera de esta lista: ante empate manda la especificación vigente y no
# se introduce un cambio que los datos no exigen (protocolo, sección 11.3).
PREFERENCIA = ["E1", "E2"]
