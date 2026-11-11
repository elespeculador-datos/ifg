# -*- coding: utf-8 -*-
"""
Núcleo de cálculo del IFG.

Flujo:
  precios brutos -> componentes crudos -> z-scores (750 sesiones)
  -> suma ponderada con reparto de pesos ausentes -> percentil -> escala 0-100
  -> suavizado -> tramos y descomposición de contribuciones.

Regla anti-look-ahead: toda normalización usa exclusivamente información
disponible hasta la fecha t. Ninguna media, desviación o percentil se calcula
sobre la muestra completa.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config
import firma as mod_firma

log = logging.getLogger("ifg.indice")


# ---------------------------------------------------------------------------
# Transformaciones básicas
# ---------------------------------------------------------------------------
def log_serie(s: pd.Series) -> pd.Series:
    """Logaritmo protegido frente a valores no positivos."""
    return np.log(s.where(s > 0))


def impulso(s: pd.Series, h: int = config.HORIZONTE_IMPULSO) -> pd.Series:
    """Variación logarítmica acumulada a h sesiones."""
    l = log_serie(s)
    return l - l.shift(h)


def estado(s: pd.Series, v: int = config.VENTANA_ESTADO) -> pd.Series:
    """
    Desviación del nivel logarítmico respecto a su media móvil.

    Por qué existe este modo: con impulso puro a 5 días, un shock deja de
    contar a la sexta sesión aunque la tensión siga ahí. El componente vuelve
    a cero mientras el diferencial sigue abierto. El modo estado mantiene el
    nivel elevado mientras persista el desplazamiento.
    """
    l = log_serie(s)
    return l - l.rolling(v, min_periods=v // 2).mean()


def transformar(s: pd.Series, modo: str = config.MODO_TRANSFORMACION) -> pd.Series:
    """Aplica el modo de transformación configurado a una serie de precios."""
    if modo == "impulso":
        return impulso(s)
    if modo == "estado":
        return estado(s)
    if modo == "mixto":
        # Se estandarizan las dos patas antes de mezclar: tienen escalas muy
        # distintas y si no, el estado (más volátil) se comería al impulso.
        return 0.5 * zscore(impulso(s)) + 0.5 * zscore(estado(s))
    raise ValueError(f"Modo de transformación desconocido: {modo}")


def zscore(s: pd.Series,
           ventana: int = config.VENTANA_Z,
           minimo: int = config.MIN_PERIODOS_Z,
           clip: float = config.CLIP_Z) -> pd.Series:
    """Z-score sobre ventana móvil, winsorizado."""
    media = s.rolling(ventana, min_periods=minimo).mean()
    desv = s.rolling(ventana, min_periods=minimo).std()
    z = (s - media) / desv.replace(0, np.nan)
    return z.clip(-clip, clip)


def neutralizar(x: pd.Series,
                mercado: pd.Series | None,
                ventana: int = config.VENTANA_BETA,
                minimo: int = config.MIN_PERIODOS_BETA) -> pd.Series:
    """
    Retira del componente la parte explicada por el factor de mercado.

    x_residual(t) = x(t) - beta(t) * m(t),  con beta estimada en ventana móvil.

    Este paso es el que materializa el criterio de diseño del proyecto. Sin él,
    un componente construido como cociente contra la bolsa (oro/ACWI,
    transporte/IBEX) se dispara en cualquier caída bursátil, tenga origen
    geopolítico o no, y el índice acaba siendo un detector de risk-off con otro
    nombre. La beta se estima con datos pasados, así que no introduce
    look-ahead.
    """
    if mercado is None or not config.NEUTRALIZAR_BETA:
        return x
    alin = pd.concat([x.rename("x"), mercado.rename("m")], axis=1)
    cov = alin["x"].rolling(ventana, min_periods=minimo).cov(alin["m"])
    var = alin["m"].rolling(ventana, min_periods=minimo).var()
    beta = (cov / var.replace(0, np.nan)).clip(-3, 3)
    residuo = alin["x"] - beta.shift(1) * alin["m"]   # beta de ayer, valor de hoy
    return residuo.reindex(x.index)


def cesta_equiponderada(precios: pd.DataFrame, columnas: list[str]) -> pd.Series:
    """
    Índice sintético a partir de la media de rentabilidades diarias.

    Se usa la media de rentabilidades y no la media de precios para que los
    valores que empiezan a cotizar tarde (o que faltan algún día) no
    introduzcan saltos artificiales en el nivel de la cesta.

    ADVERTENCIA: las rentabilidades se toman en moneda local. Para BAE (GBp)
    esto ignora el efecto divisa. Es aceptable en un ratio sectorial relativo,
    pero hay que declararlo en la metodología.
    """
    presentes = [c for c in columnas if c in precios.columns]
    if not presentes:
        return pd.Series(dtype=float)
    rent = np.log(precios[presentes]).diff()
    media = rent.mean(axis=1, skipna=True)
    return np.exp(media.fillna(0).cumsum())


def empalmar(precios: pd.DataFrame, principal: str, respaldo: str) -> pd.Series:
    """
    Serie principal extendida hacia atrás con el respaldo, SOBRE
    RENTABILIDADES y no sobre niveles.

    POR QUÉ NO SE PEGAN LOS NIVELES. El Brent y el WTI no cotizan al mismo
    precio: el diferencial entre ambos ha llegado a superar los 25 dólares.
    Pegar las dos series por el nivel mete un salto artificial justo en la
    junta, y como los componentes se construyen con variaciones a 5 días y
    desviaciones respecto a la media de 60, ese salto se convertiría en un
    pico de fricción inventado en julio de 2007, que es exactamente el tipo de
    artefacto que arruina un índice histórico.

    Lo que se hace es reencadenar: se toman las rentabilidades logarítmicas
    del respaldo en el tramo anterior y se acumulan HACIA ATRÁS desde el
    primer nivel conocido de la principal. El resultado tiene el nivel de la
    principal y la forma del respaldo, sin discontinuidad en la junta.

    Si falta cualquiera de las dos series, devuelve la que haya.
    """
    if principal not in precios.columns:
        return (precios[respaldo].copy() if respaldo in precios.columns
                else pd.Series(dtype=float))
    p = precios[principal]
    if respaldo not in precios.columns or p.dropna().empty:
        return p.copy()
    r = precios[respaldo]

    # Ancla: primera fecha en que las DOS series tienen dato. Reescalar el
    # respaldo por el cociente en esa fecha preserva exactamente sus
    # rentabilidades y lo hace continuo con la principal en la junta.
    ambos = p.notna() & r.notna()
    if not ambos.any():
        return p.copy()                     # sin solape no hay empalme seguro
    ancla = p.index[ambos][0]

    try:
        factor = float(p.loc[ancla]) / float(r.loc[ancla])
    except ZeroDivisionError:
        return p.copy()
    if not np.isfinite(factor) or factor <= 0:
        return p.copy()

    atras = r.loc[:ancla] * factor          # incluye el ancla, donde coincide

    salida = p.copy()
    salida = salida.where(salida.notna(), atras.reindex(salida.index))
    faltan = atras.index.difference(salida.index)
    if len(faltan):
        salida = pd.concat([salida, atras.loc[faltan]]).sort_index()
    return salida.rename(principal)


# ---------------------------------------------------------------------------
# Construcción de componentes
# ---------------------------------------------------------------------------
def construir_componentes(precios: pd.DataFrame,
                          gpr: pd.Series | None = None,
                          prima: pd.Series | None = None,
                          gdelt: pd.Series | None = None,
                          modo: str = config.MODO_TRANSFORMACION,
                          ) -> tuple[pd.DataFrame, dict]:
    """
    Devuelve (DataFrame de componentes ya en z-score, diccionario de detalle).

    Cada componente sale orientado: más alto = más fricción.
    """
    comp: dict[str, pd.Series] = {}
    detalle: dict[str, list[str]] = {}

    def hay(*cols: str) -> bool:
        return all(c in precios.columns for c in cols)

    # Dos factores de mercado, porque hay componentes en espacio de variación
    # (ratios de precios) y componentes en espacio de nivel (volatilidad
    # implícita, prima de riesgo). Regresar un nivel contra una variación no
    # quita nada: la beta estimada sale próxima a cero y la neutralización es
    # decorativa. Hay que emparejar cada componente con el factor que le
    # corresponde.
    fm = config.FACTOR_MERCADO
    if fm in precios.columns:
        mercado_var = transformar(precios[fm], modo)
        # Nivel de riesgo de mercado: volatilidad realizada a 21 sesiones del
        # factor global, en logaritmo. Se usa esta y no el VIX para no
        # contaminar el test de independencia frente al VIX.
        rent = np.log(precios[fm]).diff()
        mercado_niv = np.log(rent.rolling(21, min_periods=10).std() * np.sqrt(252))
    else:
        mercado_var = mercado_niv = None
        log.warning("Sin factor de mercado (%s): no se neutraliza la beta.", fm)

    def limpio(x: pd.Series, espacio: str = "var") -> pd.Series:
        """Neutralización de mercado + z-score."""
        factor = mercado_var if espacio == "var" else mercado_niv
        return zscore(neutralizar(x, factor))

    # --- 1. Energía: Brent menos cobre -------------------------------------
    # Cada pata se estandariza ANTES de restar. Si se restan las variaciones
    # brutas, el Brent (mucho más volátil) domina el componente y el cobre
    # deja de filtrar nada: el peso efectivo no sería el declarado.
    #
    # El crudo se toma empalmado (ver empalmar()): Brent donde existe, WTI
    # reencadenado antes de julio de 2007. Sin el empalme, el componente que
    # más pesa del índice no podía emitir antes de 2011 por la profundidad de
    # BZ=F en la fuente, y no por falta de historia del crudo.
    crudo = empalmar(precios, config.CRUDO_PRINCIPAL, config.CRUDO_RESPALDO)
    if not crudo.dropna().empty and "cobre" in precios.columns:
        z_crudo = limpio(transformar(crudo, modo))
        z_cobre = limpio(transformar(precios["cobre"], modo))
        comp["energia"] = ((z_crudo - z_cobre) / np.sqrt(2)).clip(-config.CLIP_Z,
                                                                  config.CLIP_Z)
        etiq_crudo = config.CRUDO_PRINCIPAL
        if config.CRUDO_RESPALDO in precios.columns:
            etiq_crudo += f"+{config.CRUDO_RESPALDO}"
        detalle["energia"] = [f"{etiq_crudo}(+)", "cobre(-)"]

    # --- 2. Volatilidad energética -----------------------------------------
    # Nivel logarítmico, no variación: la volatilidad implícita es una serie
    # con reversión a la media cuyo nivel ya es informativo por sí mismo.
    # Se neutraliza igualmente: el OVX sube en cualquier pánico bursátil.
    patas_vol, etiq_vol = [], []
    if "ovx" in precios.columns:
        patas_vol.append(limpio(log_serie(precios["ovx"]), "nivel"))
        etiq_vol.append("OVX(+)")
    if "vstoxx" in precios.columns:
        patas_vol.append(limpio(log_serie(precios["vstoxx"]), "nivel"))
        etiq_vol.append("VSTOXX(+)")
    if patas_vol:
        comp["vol_energia"] = pd.concat(patas_vol, axis=1).mean(axis=1)
        detalle["vol_energia"] = etiq_vol

    # --- 3. Refugios --------------------------------------------------------
    # Signos: oro/bolsa al alza = fricción. EURCHF y EURJPY a la BAJA significan
    # franco y yen fuertes, es decir, fricción: van con signo invertido.
    #
    # El denominador es config.DENOMINADOR_BOLSA, la MISMA serie que el factor
    # de mercado. Hasta la 0.9.0 era ACWI y su fecha de salida a bolsa (2008)
    # limitaba este componente igual que limitaba la neutralización de beta.
    patas_ref, etiq_ref = [], []
    den_bolsa = config.DENOMINADOR_BOLSA
    if hay("oro", den_bolsa):
        patas_ref.append(limpio(transformar(precios["oro"] / precios[den_bolsa],
                                            modo)))
        etiq_ref.append(f"oro/{den_bolsa}(+)")
    if "eurchf" in precios.columns:
        patas_ref.append(-limpio(transformar(precios["eurchf"], modo)))
        etiq_ref.append("CHF(+)")
    if "eurjpy" in precios.columns:
        patas_ref.append(-limpio(transformar(precios["eurjpy"], modo)))
        etiq_ref.append("JPY(+)")
    if patas_ref:
        comp["refugios"] = pd.concat(patas_ref, axis=1).mean(axis=1)
        detalle["refugios"] = etiq_ref

    # --- 4. Defensa europea vs. Stoxx 600 -----------------------------------
    cesta = cesta_equiponderada(precios, list(config.CESTA_DEFENSA))
    if not cesta.empty and "stoxx600" in precios.columns:
        ratio = cesta / precios["stoxx600"]
        comp["defensa"] = limpio(transformar(ratio, modo))
        detalle["defensa"] = ["cesta defensa/Stoxx600(+)"]

    # --- 5. Prima periférica ------------------------------------------------
    # Nivel y variación a partes iguales: el nivel capta el régimen de estrés
    # soberano, la variación capta el episodio.
    if prima is not None and not prima.empty:
        z_nivel = limpio(prima, "nivel")
        z_var = limpio(prima.diff(config.HORIZONTE_IMPULSO))
        comp["prima"] = pd.concat([z_nivel, z_var], axis=1).mean(axis=1)
        detalle["prima"] = ["ES-DE 10a nivel(+)", "ES-DE 10a variación(+)"]

    # --- 6. Transporte español ----------------------------------------------
    # Signo invertido: si IAG y Amadeus caen contra el IBEX, hay fricción.
    aereas = [c for c in ("iag", "amadeus") if c in precios.columns]
    if aereas and "ibex" in precios.columns:
        cesta_t = cesta_equiponderada(precios, aereas)
        comp["transporte"] = -limpio(transformar(cesta_t / precios["ibex"], modo))
        detalle["transporte"] = [f"{a}(-)" for a in aereas]

    # --- 7. Fletes de petroleros (nuevo en v2) ---------------------------
    # Cesta contra el mercado. Sube cuando cerrar un estrecho, sancionar una
    # flota o desviar rutas encarece el transporte de crudo. Un susto
    # financiero no encarece un flete: ahí está su valor discriminante.
    cesta_f = cesta_equiponderada(precios, list(config.CESTA_FLETES))
    if not cesta_f.empty and fm in precios.columns:
        comp["fletes"] = limpio(transformar(cesta_f / precios[fm], modo))
        detalle["fletes"] = ["cesta petroleros/mercado(+)"]

    # --- 8. Grano (nuevo en v2) -------------------------------------------
    # Trigo: mide el cierre de corredores de exportación. En 2022 recogió el
    # bloqueo del mar Negro mejor que ningún activo financiero.
    if "trigo" in precios.columns:
        comp["grano"] = limpio(transformar(precios["trigo"], modo))
        detalle["grano"] = ["trigo(+)"]

    # --- 9. Gas europeo (nuevo en v2) -------------------------------------
    # Solo existe desde octubre de 2017. Antes de esa fecha el componente no
    # está y su peso se reparte: hasta entonces el gas europeo iba indexado
    # al petróleo y no había precio de mercado que medir. Discontinuidad
    # metodológica que debe declararse.
    if "gas_ttf" in precios.columns:
        comp["gas"] = limpio(transformar(precios["gas_ttf"], modo))
        detalle["gas"] = ["TTF(+)"]

    # --- 10. GDELT ---------------------------------------------------------
    if gdelt is not None and not gdelt.empty:
        # IMPRESCINDIBLE llevar la serie al calendario de precios ANTES del
        # z-score. La ventana está expresada en SESIONES: aplicada a una
        # serie muestreada semanalmente, 750 sesiones pasan a significar 750
        # semanas y el mínimo de 375 se convierte en siete años, con lo que
        # el componente no aparece hasta 2020 y se pierde toda la
        # calibración.
        #
        # SE ARRASTRA EL ÚLTIMO VALOR, NO SE INTERPOLA. Interpolar parece más
        # fino y es un look-ahead encubierto: el valor de un miércoles saldría
        # de promediar la muestra del lunes anterior con la del lunes
        # siguiente, que todavía no existe cuando se publica. Al llegar esa
        # muestra, el valor ya publicado cambiaba hasta 2 puntos. Arrastrando,
        # cada día usa la última lectura conocida y nada se revisa.
        #
        # El límite de 10 sesiones evita que una GDELT caída siga inyectando
        # su último valor indefinidamente: pasado ese plazo el componente
        # desaparece y su peso se reparte.
        g = (gdelt.reindex(gdelt.index.union(precios.index))
                  .ffill(limit=10)
                  .reindex(precios.index))
        comp["gdelt"] = zscore(g.rolling(3, min_periods=1).mean())
        detalle["gdelt"] = ["conflicto material MM3(+)"]

    # --- 11. GPR ------------------------------------------------------------
    if gpr is not None and not gpr.empty:
        comp["gpr"] = zscore(np.log1p(gpr))
        detalle["gpr"] = ["GPR diario(+)"]

    # Blindaje: cualquier serie con fechas repetidas rompe el ensamblado y el
    # mensaje de error no señala a la fuente culpable. Se limpia aquí y se
    # avisa de cuál venía mal.
    for nombre, serie in list(comp.items()):
        if serie.index.has_duplicates:
            log.warning("El componente %s traía fechas repetidas: se depuran.",
                        nombre)
            comp[nombre] = serie[~serie.index.duplicated(keep="last")]

    df = pd.DataFrame(comp).sort_index()
    log.info("Componentes construidos: %s", list(df.columns))
    ausentes = set(config.PESOS) - set(df.columns)
    if ausentes:
        log.warning("Componentes ausentes (su peso se reparte): %s",
                    sorted(ausentes))
    return df, detalle


# ---------------------------------------------------------------------------
# Alineación al calendario de publicación
# ---------------------------------------------------------------------------
def alinear_con_arrastre(componentes: pd.DataFrame,
                         calendario: pd.DatetimeIndex,
                         max_arrastre: int = 3
                         ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reindexa al calendario de referencia y arrastra valores un máximo de
    `max_arrastre` sesiones, diciendo ADEMÁS qué celdas son arrastradas.

    Motivo del límite: sin él, una serie que deja de publicarse (GPR entre
    lunes, un futuro suspendido) seguiría inyectando su último valor
    indefinidamente y el índice parecería vivo cuando en realidad está
    congelado.

    POR QUÉ HACE FALTA DISTINGUIR EL ARRASTRE. Hasta la 0.11.0 esta función
    devolvía solo la tabla, y una celda arrastrada era indistinguible de una
    con dato propio. Consecuencia: el cálculo de cobertura la contaba como
    dato disponible, la fila nacía con cobertura completa, se cerraba como
    definitiva ese mismo día y cuando llegaba el valor de verdad ya era
    inmutable. El 14, 15 y 16 de octubre de 2026 se publicaron así, con el
    GPR del día 13 arrastrado, y el lunes siguiente —cuando la Reserva
    Federal entregó sus valores reales— el recálculo se separaba 10,14
    puntos de lo publicado sin que nada pudiera corregirlo.

    PERO NO TODO ARRASTRE ES LO MISMO, y confundirlos fue el primer intento
    fallido de arreglar esto. Hay dos clases, y la diferencia no es de grado:

      - HUECO PERMANENTE. El calendario de referencia son las sesiones del
        IBEX, y los demás mercados cierran otros días. Un festivo en Nueva
        York deja sin cierre al cobre, al oro o al ACWI en una sesión que
        para el IBEX es hábil. Arrastrar el último cierre es el tratamiento
        correcto y además el único posible: ese dato no existe y no va a
        existir nunca. Medido sobre la serie real, esto es el 10 % de las
        sesiones. Descontarlo de la cobertura las dejaría marcadas como
        incompletas para siempre sin que ninguna corrección pueda llegar
        jamás: puro ruido, y encima haría saltar la marca de "parcial" en
        cientos de filas.

      - ENTREGA PENDIENTE. El GPR aún no ha publicado su semana, el BCE va
        con un día de retraso, GDELT no ha subido su muestra, un proveedor
        de precios se ha caído. Aquí el dato SÍ va a llegar, y con fecha de
        esa sesión. Contarlo como cobertura es afirmar un dato que todavía
        no se tiene, y esa afirmación cierra la fila antes de tiempo.

    EL CRITERIO QUE LOS SEPARA SALE DE LOS PROPIOS DATOS, sin lista de
    componentes escrita a mano ni ninguna cifra elegida a ojo: se mira si la
    fecha arrastrada cae MÁS ALLÁ del último dato propio de ese componente.
    Más allá del final de su serie significa que la fuente todavía no ha
    llegado ahí; dentro de su rango significa un agujero interior, que es el
    festivo. El caso del 14 de octubre es el primero: el archivo del GPR
    terminaba el día 13. Y una caída de precios al borde de la serie cae
    también en el primero, que es lo que se quiere.

    Devuelve (tabla, pendiente), donde `pendiente` marca solo la segunda
    clase. Ver agregar().
    """
    bruto = componentes.reindex(componentes.index.union(calendario)).sort_index()
    lleno = bruto.ffill(limit=max_arrastre)

    # Arrastrada = vacía antes del ffill y llena después.
    arrastrado = bruto.isna() & lleno.notna()

    # Último dato propio de cada componente. Lo que se arrastra más allá de
    # esa fecha está esperando a su fuente; lo de dentro es un hueco que no
    # se va a rellenar.
    pendiente = arrastrado.copy()
    for col in bruto.columns:
        ultimo = bruto[col].last_valid_index()
        if ultimo is None:
            pendiente[col] = False          # sin un solo dato propio: no hay nada que esperar
        else:
            pendiente.loc[pendiente.index <= ultimo, col] = False

    return (lleno.reindex(calendario),
            pendiente.reindex(calendario).fillna(False))


def alinear(componentes: pd.DataFrame,
            calendario: pd.DatetimeIndex,
            max_arrastre: int = 3) -> pd.DataFrame:
    """La tabla alineada, sin la máscara. Se mantiene por compatibilidad."""
    return alinear_con_arrastre(componentes, calendario, max_arrastre)[0]


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------
def agregar(componentes: pd.DataFrame,
            pesos: dict[str, float] = None,
            pendiente: pd.DataFrame = None) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    """
    Suma ponderada con reparto proporcional del peso ausente.

    Devuelve (compuesto, contribuciones, cobertura).
      - compuesto: serie del índice antes de percentilizar.
      - contribuciones: peso normalizado x z-score, por componente y día.
      - cobertura: fracción del peso nominal CON DATO PROPIO cada día.

    UN DATO PENDIENTE SUMA PERO NO CUENTA COMO COBERTURA (desde la 0.11.0).
    Son dos preguntas distintas y antes se respondían con la misma máscara:

      - "¿con qué calculo hoy?" -> con todo lo que haya, arrastre incluido.
        Para eso existe el arrastre: que un retraso de una fuente no deje al
        índice sin valor. Esto NO cambia, y por tanto el valor del índice de
        un día dado con unas entradas dadas es exactamente el mismo que antes.
      - "¿cuánto de lo que calculo es dato de esa sesión?" -> aquí un valor
        que está esperando a su fuente es justo lo que no hay. Contarlo era
        afirmar una cobertura que no existía, y esa afirmación tenía una
        consecuencia: cobertura completa significa cerrar la fila como
        definitiva el mismo día, de modo que el dato real llegaba cuando ya
        no se podía usar.

    `pendiente` marca solo el arrastre que espera entrega, no el festivo de
    otro mercado: la diferencia, y por qué importa, está en
    alinear_con_arrastre(). Con la máscara, esas filas nacen provisionales y
    se corrigen solas cuando la fuente entrega, que es para lo que se
    inventaron los provisionales. Sin ella, el comportamiento es el de antes.
    """
    pesos = pesos or config.PESOS
    cols = [c for c in componentes.columns if c in pesos]
    if not cols:
        raise ValueError("Ningún componente coincide con el diccionario de pesos.")

    w = pd.Series({c: pesos[c] for c in cols}, dtype=float)
    w = w / w.sum()

    x = componentes[cols]
    disponible = x.notna()

    # Peso nominal CON DATO DE ESA SESIÓN, sobre el total configurado. Una
    # celda que espera entrega se descuenta aquí y solo aquí: sigue entrando
    # en la suma de abajo, porque el índice tiene que dar un valor.
    propio = disponible
    if pendiente is not None:
        propio = disponible & ~(pendiente.reindex(index=x.index, columns=cols)
                                .fillna(False).astype(bool))
    peso_total_config = sum(pesos.values())
    cobertura = (propio * pd.Series({c: pesos[c] for c in cols})).sum(axis=1) \
        / peso_total_config

    # Renormalización diaria: el peso de lo que falta se reparte en proporción.
    w_dia = disponible.mul(w, axis=1)
    suma_w = w_dia.sum(axis=1).replace(0, np.nan)
    w_dia = w_dia.div(suma_w, axis=0)

    contribuciones = x.fillna(0) * w_dia
    compuesto = contribuciones.sum(axis=1, min_count=1)
    compuesto[suma_w.isna()] = np.nan
    compuesto.name = "compuesto"

    return compuesto, contribuciones, cobertura.rename("cobertura")


def escalar(compuesto: pd.Series,
            modo_escala: str = None,
            modo_pct: str = None) -> pd.Series:
    """Convierte el compuesto a la escala 0-100 según el modo configurado."""
    modo_escala = modo_escala or config.MODO_ESCALA
    if modo_escala == "logistica":
        # El compuesto es una media ponderada de z-scores parcialmente
        # correlacionados: su desviación típica NO es 1, sino bastante menor.
        # Hay que estandarizarlo por su propia sigma antes de la logística, o
        # la escala se aplasta en torno a 50. La sigma se calcula de forma
        # expansiva para no usar información futura.
        sigma = compuesto.expanding(min_periods=config.MIN_PERIODOS_PERCENTIL).std()
        z = compuesto / sigma.replace(0, np.nan) / config.LOGISTICA_PENDIENTE
        return (100 / (1 + np.exp(-z))).rename("ifg")
    return percentilizar(compuesto, modo_pct or config.MODO_PERCENTIL)


def percentilizar(compuesto: pd.Series,
                  modo: str = config.MODO_PERCENTIL) -> pd.Series:
    """
    Convierte el compuesto en escala 0-100.

    Modo expansivo (por defecto): percentil del valor de hoy dentro de toda la
    historia conocida hasta hoy. Ventaja decisiva para un índice publicado: el
    valor de una fecha pasada NUNCA cambia al recalcular, porque no depende de
    datos posteriores. Contrapartida: la serie no es estrictamente homogénea
    en el tiempo (los primeros años se calculan con menos muestra) y cada
    máximo histórico marca 100.

    Modo móvil: más sensible a la coyuntura reciente, pero un régimen tenso
    prolongado se "normaliza" y el índice baja con la guerra todavía en curso.
    """
    if modo == "expansivo":
        pct = compuesto.expanding(min_periods=config.MIN_PERIODOS_PERCENTIL).rank(pct=True)
    elif modo == "movil":
        pct = compuesto.rolling(config.VENTANA_PERCENTIL,
                                min_periods=config.MIN_PERIODOS_PERCENTIL).rank(pct=True)
    else:
        raise ValueError(f"Modo de percentil desconocido: {modo}")
    return (pct * 100).rename("ifg")


def tramo(valor: float) -> str:
    """Etiqueta de tramo para un valor 0-100."""
    if pd.isna(valor):
        return "sin dato"
    for bajo, alto, etiqueta in config.TRAMOS:
        if bajo <= valor < alto:
            return etiqueta
    return "Extrema"


# ---------------------------------------------------------------------------
# Orquestación del cálculo
# ---------------------------------------------------------------------------
def calcular(precios: pd.DataFrame,
             gpr: pd.Series | None = None,
             prima: pd.Series | None = None,
             gdelt: pd.Series | None = None,
             pesos: dict[str, float] = None,
             modo: str = None,
             agregacion: str = None) -> dict:
    """
    Calcula el IFG completo. Devuelve un diccionario con todas las piezas.

    `agregacion` elige el agregador: "media" reproduce la v1 y sirve de línea
    base; "firma" y "firma_cos" puntúan por parecido con la firma geopolítica
    estimada en la muestra de calibración.
    """
    modo = modo or config.MODO_TRANSFORMACION
    agregacion = agregacion or config.MODO_AGREGACION
    componentes, detalle = construir_componentes(precios, gpr, prima, gdelt, modo)

    # Calendario de referencia: sesiones del IBEX si está, si no, del conjunto.
    if "ibex" in precios.columns:
        calendario = precios["ibex"].dropna().index
    else:
        calendario = precios.dropna(how="all").index
    componentes, pendiente = alinear_con_arrastre(componentes, calendario)

    # La cobertura se calcula siempre con el reparto de pesos nominales: es
    # una medida de cuántos datos hay ese día, no del agregador elegido. Y de
    # cuántos hay DE ESA SESIÓN: lo que está esperando entrega no cuenta,
    # aunque sí se use para calcular. Ver agregar().
    compuesto, contribuciones, cobertura = agregar(componentes, pesos,
                                                   pendiente=pendiente)

    direccion = diag_firma = coseno = None
    if agregacion.startswith("iguales"):
        direccion = mod_firma.direccion_iguales(componentes)
        diag_firma = {"metodo": "pesos iguales, sin estimación"}
    elif agregacion != "media":
        direccion, diag_firma = mod_firma.estimar_direccion(componentes)

    # OJO: esta llamada va FUERA de las ramas anteriores. Estuvo dentro del
    # elif y el resultado fue que "iguales" e "iguales_cos" calculaban su
    # dirección y luego no la usaban: caían a la media ponderada sin avisar,
    # y las tres filas de la comparación salían idénticas.
    if direccion is not None:
        compuesto, contribuciones, coseno = mod_firma.agregar_por_firma(
            componentes, direccion, agregacion)

    ifg = escalar(compuesto)
    ifg_suave = ifg.ewm(span=config.SUAVIZADO_TITULAR, adjust=False).mean()

    tabla = pd.DataFrame({
        "ifg": ifg.round(2),
        "ifg_suavizado": ifg_suave.round(2),
        "compuesto": compuesto.round(4),
        "cobertura": cobertura.round(3),
    })
    # La variación y el tramo salen del valor CRUDO desde la 0.10.0. El
    # suavizado se sigue calculando y publicando, pero como línea de
    # tendencia: no se suaviza una medición y después se llama medición al
    # suavizado. Ver PROTOCOLO_VALIDACION.md, sección 7.1.
    tabla["variacion"] = tabla["ifg"].diff().round(2)
    tabla["tramo"] = tabla["ifg"].map(tramo)
    tabla["parcial"] = tabla["cobertura"] < config.MIN_COBERTURA_PESO
    if coseno is not None:
        tabla["coseno"] = coseno.round(3)

    recorte = tabla.index >= pd.Timestamp(config.FECHA_INICIO_PUBLICACION)
    return {
        "tabla": tabla[recorte],
        "componentes": componentes[recorte],
        "contribuciones": contribuciones[recorte],
        "detalle": detalle,
        "tabla_completa": tabla,
        "agregacion": agregacion,
        "direccion": direccion,
        "diag_firma": diag_firma,
    }


def descomponer_dia(resultado: dict, fecha=None, n: int = 2) -> dict:
    """
    Los n componentes que más han aportado al CAMBIO del día.
    Esto es el contenido editorial: el titular es el valor, la noticia es
    de dónde viene.
    """
    contrib = resultado["contribuciones"]
    if fecha is None:
        fecha = contrib.dropna(how="all").index[-1]
    fecha = pd.Timestamp(fecha)

    delta = contrib.diff().loc[fecha].dropna()
    nivel = contrib.loc[fecha].dropna()
    orden = delta.abs().sort_values(ascending=False)

    fila = resultado["tabla"].loc[fecha]
    return {
        "fecha": str(fecha.date()),
        "version": config.VERSION,
        # "valor" es el índice oficial y desde la 0.10.0 es el crudo.
        # "valor_crudo" se mantiene con el mismo contenido para no romper
        # ningún consumidor que ya lo leyera, y "valor_tendencia" expone el
        # suavizado, que antes ocupaba "valor". Ninguna clave desaparece.
        "valor": None if pd.isna(fila["ifg"]) else float(fila["ifg"]),
        "valor_crudo": None if pd.isna(fila["ifg"]) else float(fila["ifg"]),
        "valor_tendencia": (None if pd.isna(fila["ifg_suavizado"])
                            else float(fila["ifg_suavizado"])),
        "variacion": None if pd.isna(fila["variacion"]) else float(fila["variacion"]),
        "tramo": fila["tramo"],
        "cobertura": float(fila["cobertura"]),
        "parcial": bool(fila["parcial"]),
        "motores": [
            {"componente": c,
             "aporte_cambio": round(float(delta[c]), 4),
             "aporte_nivel": round(float(nivel.get(c, np.nan)), 4)}
            for c in orden.index[:n]
        ],
        "componentes_activos": list(contrib.loc[fecha].dropna().index),
    }
