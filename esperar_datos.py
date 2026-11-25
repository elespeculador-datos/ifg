"""esperar_datos.py — antes de publicar el IFG, espera a que Yahoo tenga los cierres de la última sesión.

POR QUÉ. A las 03:15 de Madrid, Yahoo devuelve con frecuencia la última sesión SIN renta variable (IBEX, Stoxx,
ACWI, acciones) y a veces el histórico del gas TTF recortado a una sola sesión. El resultado era un índice que
publicaba sistemáticamente la penúltima sesión (vigilancias del 3 al 6 y del 17 de noviembre de 2026).
Las 16:30 del mismo día los datos ya están. No cambia ninguna regla del índice: el corte sigue siendo el cierre
de Wall Street de la sesión anterior y la publicación sigue dentro de la ventana de publicar_diario.py (03-05 h).
Solo se espera, como mucho hasta las 04:45, comprobando cada 10 minutos.

Si a las 04:45 siguen faltando, sale igualmente (código 0) y lo deja escrito: se publica como hasta ahora.
Cada intento queda en el registro con su hora, así se sabe a qué hora llegan de verdad los datos.

Uso: python esperar_datos.py      (lo llama ifg-diario.sh antes de publicar_diario.py)
Dependencias: pandas, yfinance (las del IFG).
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ZONA = ZoneInfo("Europe/Madrid")
LIMITE = (4, 45)            # hora:minuto de Madrid; la ventana de publicación cierra a las 05:00
PAUSA = 600                 # segundos entre intentos
TESTIGOS = ["^IBEX", "^STOXX", "ACWI", "IAG.MC"]   # renta variable: la clase que faltaba
MIN_GAS = 2000              # sesiones de TTF=F por debajo de las cuales la descarga está recortada


def sesion_esperada(ahora: datetime) -> date:
    """Último día laborable anterior (lunes a viernes). Si fue festivo, nunca llegará y se publica al límite."""
    d = ahora.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def estado(fecha: date) -> tuple[dict[str, bool], int | None]:
    df = yf.download(TESTIGOS, period="10d", interval="1d", progress=False, auto_adjust=False)["Close"]
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    fila = df[df.index == pd.Timestamp(fecha)]
    testigos = {t: bool(not fila.empty and pd.notna(fila[t].iloc[0])) for t in TESTIGOS}
    try:
        gas = len(yf.Ticker("TTF=F").history(period="max", auto_adjust=False))
    except Exception:            # noqa: BLE001  (solo informativo: el histórico lo protege fuentes.py)
        gas = None
    return testigos, gas


def main() -> int:
    ahora = datetime.now(ZONA)
    fecha = sesion_esperada(ahora)
    limite = ahora.replace(hour=LIMITE[0], minute=LIMITE[1], second=0, microsecond=0)
    intento = 0
    while True:
        intento += 1
        ahora = datetime.now(ZONA)
        try:
            testigos, gas = estado(fecha)
        except Exception as e:   # noqa: BLE001
            testigos, gas = {t: False for t in TESTIGOS}, None
            print(f"{ahora:%H:%M} esperar_datos: error al consultar Yahoo ({e})", flush=True)
        faltan = [t for t, ok in testigos.items() if not ok]
        gas_ok = gas is not None and gas >= MIN_GAS
        print(f"{ahora:%H:%M} esperar_datos: intento {intento}, sesión {fecha}: "
              f"{'renta variable completa' if not faltan else 'faltan ' + ', '.join(faltan)}; "
              f"TTF=F {gas} sesiones{'' if gas_ok else ' (recortado)'}", flush=True)
        if not faltan and gas_ok:
            print(f"{ahora:%H:%M} esperar_datos: datos completos, se publica", flush=True)
            return 0
        if ahora >= limite:
            print(f"{ahora:%H:%M} esperar_datos: AVISO límite de las {LIMITE[0]:02d}:{LIMITE[1]:02d} alcanzado "
                  f"con datos incompletos; se publica igualmente", flush=True)
            return 0
        time.sleep(min(PAUSA, max(30, (limite - ahora).total_seconds())))


if __name__ == "__main__":
    sys.exit(main())
