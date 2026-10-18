# -*- coding: utf-8 -*-
"""
Sonda de profundidad histórica de las fuentes.

Mide cuánta historia da realmente cada ticker que el índice usa, para decidir
con hechos hasta dónde puede llegar hacia atrás la serie. Es el paso previo
obligatorio del protocolo (PROTOCOLO_VALIDACION.md, sección 3): sin esto, la
fecha de inicio de la extensión sería una suposición.

NO calcula el índice ni modifica nada. Solo descarga y mide.

Este script necesita red hacia Yahoo Finance, así que normalmente se ejecuta
desde el flujo de GitHub Actions con workflow_dispatch, no en local.

Uso:
    python sonda_historia.py
    python sonda_historia.py --desde 1990-01-01 --salida sonda.csv
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import config

# Candidatos para sustituir a los que no llegan atrás. La columna "motivo"
# explica por qué se propone, para que la sustitución quede justificada y no
# parezca oportunista.
SUSTITUTOS = {
    "sp500":     ("^GSPC",  "factor de mercado con historia desde 1927, "
                            "reemplaza a ACWI (ETF de 2008)"),
    "wti":       ("CL=F",   "crudo con historia muy anterior a BZ=F (2007); "
                            "discontinuidad declarada frente al Brent"),
    "msci_world": ("^990100-USD-STRD",
                            "índice MSCI World, alternativa al S&P 500 si "
                            "diera más historia utilizable"),
    "oro_lbma":  ("XAUUSD=X", "oro al contado, por si GC=F no llega atrás"),
    "nat":       ("NAT",    "Nordic American: la pata más antigua de la "
                            "cesta de fletes"),
}


def medir(ticker: str, desde: str) -> dict:
    """Primera y última sesión, número de observaciones y huecos."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance no instalado"}
    try:
        d = yf.download(ticker, start=desde, progress=False,
                        auto_adjust=False, threads=False)
    except Exception as e:                      # noqa: BLE001
        return {"error": str(e)[:60]}
    if d is None or d.empty:
        return {"error": "sin datos"}
    s = d["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = s.dropna()
    if s.empty:
        return {"error": "solo NaN"}
    # Mayor racha sin dato, en sesiones de calendario de la propia serie.
    dias = s.index.to_series().diff().dt.days.fillna(1)
    return {
        "desde": str(s.index[0].date()),
        "hasta": str(s.index[-1].date()),
        "obs": len(s),
        "hueco_max_dias": int(dias.max()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="1985-01-01")
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    # Todo lo que el índice usa hoy, más los sustitutos propuestos.
    objetivo: dict[str, tuple[str, str]] = {}
    for k, t in config.TICKERS.items():
        objetivo[k] = (t, "en uso")
    for k, t in config.CESTA_DEFENSA.items():
        objetivo[k] = (t, "cesta de defensa")
    for k, t in config.CESTA_FLETES.items():
        objetivo[k] = (t, "cesta de fletes")
    objetivo.update(SUSTITUTOS)

    filas = []
    print(f"Sondeando {len(objetivo)} series desde {args.desde}...\n")
    print(f"{'clave':>14} {'ticker':>22} {'desde':>12} {'obs':>7} "
          f"{'hueco':>6}  papel")
    for clave, (ticker, papel) in objetivo.items():
        r = medir(ticker, args.desde)
        if "error" in r:
            print(f"{clave:>14} {ticker:>22} {'ERROR':>12} {'':>7} {'':>6}  "
                  f"{r['error']}")
            filas.append({"clave": clave, "ticker": ticker, "papel": papel,
                          "desde": None, "obs": 0, "error": r["error"]})
            continue
        print(f"{clave:>14} {ticker:>22} {r['desde']:>12} {r['obs']:>7} "
              f"{r['hueco_max_dias']:>6}  {papel}")
        filas.append({"clave": clave, "ticker": ticker, "papel": papel,
                      **r, "error": None})

    t = pd.DataFrame(filas)

    # --- Qué fecha de inicio permite cada nivel de cobertura ---------------
    print()
    print("=" * 78)
    print("FECHA DE INICIO VIABLE SEGÚN QUÉ COMPONENTES SE EXIJAN")
    print("=" * 78)
    print("  Al inicio de cada serie hay que sumarle el calentamiento de la")
    print("  normalización. Con MODO_TRANSFORMACION='mixto', neutralización de")
    print("  beta y z-score posterior, el apilamiento medido en la auditoría")
    print("  es de unas 900 sesiones, es decir del orden de 3,5 años.")
    print()
    usables = t[t["desde"].notna()].copy()
    if usables.empty:
        print("  Sin datos: no se puede concluir nada.")
        return 1
    usables["inicio"] = pd.to_datetime(usables["desde"])
    usables = usables.sort_values("inicio")
    calent = pd.Timedelta(days=365 * 3.5)
    for pct in (0.5, 0.7, 0.9, 1.0):
        n = max(1, int(round(pct * len(usables))))
        corte = usables["inicio"].iloc[n - 1]
        print(f"  para el {pct:.0%} de las series: datos desde "
              f"{corte.date()}  ->  índice desde "
              f"{(corte + calent).date()}")

    print()
    print("  Las series que más tarde empiezan, que son las que marcan el")
    print("  límite si se exige cobertura completa:")
    for _, r in usables.tail(6).iterrows():
        print(f"    {r['clave']:>14} ({r['ticker']}): {r['desde']}")

    if args.salida:
        t.to_csv(args.salida, index=False)
        print(f"\nResultado guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
