# -*- coding: utf-8 -*-
"""
Agregación por firma: el cambio de fondo de la versión 2.

El problema de la v1 era el agregador, no los componentes. Promediar colapsa
la configuración de los componentes en un número y tira justo la información
que distingue una crisis geopolítica de una caída de bolsa cualquiera. Durante
los hitos geopolíticos se forma un racimo coherente (defensa con GPR, refugios
con defensa); durante las caídas de mercado ese racimo se deshace y varias
parejas se invierten.

Este módulo mide, cada día, en qué grado la configuración actual coincide con
la de un shock geopolítico.

  1. DIRECCIÓN DISCRIMINANTE. Se estima como la diferencia entre el vector
     medio de z-scores durante los hitos y el vector medio durante los
     controles, usando SOLO episodios anteriores a la fecha de corte. Es un
     discriminante lineal al estilo de Fisher, sin la matriz de covarianzas,
     que con esta muestra sería imposible de estimar con sentido.

  2. ENCOGIMIENTO. Con once episodios de calibración y diez componentes, la
     dirección cruda tiene demasiados grados de libertad. Se encoge hacia el
     vector de pesos iguales en una proporción fijada DE ANTEMANO.

  3. PUNTUACIÓN. Proyección del vector del día sobre esa dirección,
     opcionalmente multiplicada por el coseno entre ambos, que premia el
     alineamiento al modo del parámetro de orden de Vicsek: un movimiento
     grande pero desalineado puntúa bajo.

Riesgo de este enfoque: la dirección se estima con pocos episodios y podría
estar recogiendo ruido. Por eso toda la validación es fuera de muestra y la
media ponderada se conserva como línea base de comparación.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config

log = logging.getLogger("ifg.firma")


def _indice_ventanas(idx: pd.DatetimeIndex, eventos, antes=2, despues=15,
                     hasta: str | None = None) -> pd.DatetimeIndex:
    """Índice de las sesiones dentro de las ventanas de una lista de eventos."""
    sel = pd.DatetimeIndex([])
    for item in eventos:
        f = pd.Timestamp(item[0])
        if hasta is not None and f >= pd.Timestamp(hasta):
            continue
        tramo = idx[(idx >= f - pd.Timedelta(days=antes))
                    & (idx <= f + pd.Timedelta(days=despues))]
        sel = sel.union(tramo)
    return sel


def estimar_direccion(componentes: pd.DataFrame,
                      hasta: str = None,
                      encogimiento: float = None,
                      solo_mayores: bool = False) -> tuple[pd.Series, dict]:
    """
    Estima la dirección discriminante con la muestra de calibración.

    Devuelve (dirección normalizada, diagnóstico). La dirección se congela:
    a partir de aquí no vuelve a tocarse, ni siquiera con datos nuevos.
    """
    hasta = hasta or config.FECHA_CORTE_CALIBRACION
    encogimiento = (config.ENCOGIMIENTO_FIRMA if encogimiento is None
                    else encogimiento)

    datos = componentes.dropna(how="all")
    idx = datos.index

    hitos = [h for h in config.HITOS if (h[2] or not solo_mayores)]
    v_hitos = _indice_ventanas(idx, hitos, hasta=hasta)
    v_ctrl = _indice_ventanas(idx, config.CONTROLES, hasta=hasta)

    n_h = sum(1 for h in hitos if pd.Timestamp(h[0]) < pd.Timestamp(hasta))
    n_c = sum(1 for c in config.CONTROLES if pd.Timestamp(c[0]) < pd.Timestamp(hasta))
    if n_h < 4 or n_c < 2:
        raise ValueError(
            f"Calibración insuficiente: {n_h} hitos y {n_c} controles antes "
            f"de {hasta}. Adelanta la fecha de corte.")

    media_h = datos.loc[idx.intersection(v_hitos)].mean()
    media_c = datos.loc[idx.intersection(v_ctrl)].mean()
    cruda = (media_h - media_c).fillna(0.0)

    # Encogimiento hacia pesos iguales. Ambos vectores se normalizan antes
    # de mezclarlos para que la proporción signifique lo que dice.
    def normalizar(v: pd.Series) -> pd.Series:
        n = np.sqrt((v ** 2).sum())
        return v / n if n > 0 else v

    iguales = pd.Series(1.0, index=cruda.index)
    direccion = normalizar(
        (1 - encogimiento) * normalizar(cruda) + encogimiento * normalizar(iguales)
    )

    diag = {
        "fecha_corte": str(hasta),
        "hitos_calibracion": n_h,
        "controles_calibracion": n_c,
        "sesiones_hitos": len(idx.intersection(v_hitos)),
        "sesiones_controles": len(idx.intersection(v_ctrl)),
        "encogimiento": encogimiento,
        "direccion_cruda": cruda.round(3).to_dict(),
        "direccion_final": direccion.round(3).to_dict(),
    }
    log.info("Dirección estimada con %d hitos y %d controles anteriores a %s",
             n_h, n_c, hasta)
    return direccion, diag


def direccion_iguales(componentes: pd.DataFrame) -> pd.Series:
    """
    Dirección de pesos iguales: la que quedó tras la validación de la v2.

    No estima nada, así que no hay nada que sobreajustar. Todo lo que
    rendía fuera de muestra venía de aquí, no de la dirección aprendida.
    """
    v = pd.Series(1.0, index=componentes.columns)
    return v / np.sqrt((v ** 2).sum())


def agregar_por_firma(componentes: pd.DataFrame,
                      direccion: pd.Series,
                      modo: str = None) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    """
    Puntúa cada día por su parecido con la firma geopolítica.

    Devuelve (puntuación, contribuciones por componente, coseno diario).

    Los días con componentes ausentes se tratan renormalizando la dirección
    sobre los disponibles, igual que la media reparte el peso que falta.
    """
    modo = modo or config.MODO_AGREGACION
    cols = [c for c in componentes.columns if c in direccion.index]
    if not cols:
        raise ValueError("Ningún componente coincide con la dirección estimada.")

    z = componentes[cols]
    d = direccion[cols]
    disponible = z.notna()

    # Dirección efectiva de cada día, renormalizada sobre lo disponible
    d_dia = disponible.mul(d, axis=1)
    norma_d = np.sqrt((d_dia ** 2).sum(axis=1)).replace(0, np.nan)

    contribuciones = z.fillna(0) * d_dia.div(norma_d, axis=0)
    proyeccion = contribuciones.sum(axis=1, min_count=1)

    norma_z = np.sqrt((z.fillna(0) ** 2).sum(axis=1)).replace(0, np.nan)
    coseno = proyeccion / norma_z

    if modo in ("firma", "iguales"):
        puntuacion = proyeccion
    elif modo in ("firma_cos", "iguales_cos"):
        # El valor absoluto del coseno conserva el signo de la proyección: un
        # día que apunta justo al revés de la firma debe puntuar negativo, no
        # positivo por doble cambio de signo.
        puntuacion = proyeccion * coseno.abs()
    else:
        raise ValueError(f"Modo de agregación desconocido: {modo}")

    return (puntuacion.rename("compuesto"),
            contribuciones,
            coseno.rename("coseno"))
