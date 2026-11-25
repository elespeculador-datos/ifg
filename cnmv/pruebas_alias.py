"""Pruebas de los alias de cnmv/empresas.csv: cada empresa del IBEX 35 se reconoce por el nombre con el que hoy firma
en la CNMV, y ningún nombre se atribuye a dos empresas.

Motivo (24/11/2026): Logista firma como «LOGISTA INTEGRAL, S.A.» y Colonial como «COLONIAL SFL, SOCIMI, S.A.»; los
alias antiguos («LOGISTA HOLDINGS» e «INMOBILIARIA COLONIAL») no los reconocían y el colector no les atribuyó ninguno
de sus 88 comunicados de doce meses. El fichero de nombres sale del histórico del servidor del 24/11/2026
(cnmv/datos/comunicados.csv, 7.033 comunicados del 20/10/2025 al 24/11/2026).

Uso: python3 cnmv/pruebas_alias.py   (sin red)
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comunicados as cn  # noqa: E402

PRUEBAS = Path(__file__).resolve().parent / "pruebas_cnmv"
fallos = 0
total = 0


def ok(cond: bool, texto: str) -> None:
    global fallos, total
    total += 1
    if not cond:
        fallos += 1
    print(("ok     " if cond else "FALLO  ") + texto)


def comprobar(e: pd.DataFrame, nombres: pd.DataFrame) -> tuple[list, list, list]:
    """Devuelve (empresas sin nombre reconocido, nombres que no reconoce su empresa, nombres que reconocen dos)."""
    sin_nombre, no_reconocidos, dobles = [], [], []
    for x in e.itertuples():
        suyos = nombres[nombres["isin"] == x.isin]
        if suyos.empty:
            sin_nombre.append(x.nombre)
        for em in suyos.emisor:
            if not re.search(x.patron, cn._norm(em)):
                no_reconocidos.append((x.nombre, em))
    for em in nombres.emisor:
        quien = [x.nombre for x in e.itertuples() if re.search(x.patron, cn._norm(em))]
        if len(quien) > 1:
            dobles.append((em, quien))
    return sin_nombre, no_reconocidos, dobles


def main() -> int:
    e = cn.empresas_ibex(pd.Timestamp("2026-11-24"))
    nombres = pd.read_csv(PRUEBAS / "emisores-ibex-2026-11-24.csv", dtype=str, keep_default_na=False)
    ok(len(e) == 35, f"35 empresas en la composición ({len(e)})")
    ok(set(nombres["isin"]) == set(e["isin"]), "el fichero de nombres cubre exactamente las 35")
    sin_nombre, no_reconocidos, dobles = comprobar(e, nombres)
    ok(not sin_nombre, f"todas tienen al menos un nombre de la CNMV ({sin_nombre})")
    ok(not no_reconocidos, f"cada alias reconoce los nombres de su empresa ({no_reconocidos})")
    ok(not dobles, f"ningún nombre se atribuye a dos empresas ({dobles})")
    for isin, emisor in (("ES0105027009", "LOGISTA INTEGRAL, S.A."), ("ES0139140174", "COLONIAL SFL, SOCIMI, S.A."),
                         ("ES0105027009", "COMPAÑIA DE DISTRIBUCION INTEGRAL LOGISTA HOLDINGS, S.A."),
                         ("ES0139140174", "INMOBILIARIA COLONIAL, SOCIMI, S.A.")):
        x = cn.identificar(emisor, e)
        ok(x is not None and x["isin"] == isin, f"«{emisor}» → {isin} (nombre actual y anterior)")
    # Control: con los alias antiguos, la comprobación falla justo en Logista y Colonial.
    viejo = e.copy()
    viejo.loc[viejo["isin"] == "ES0105027009", "patron"] = "LOGISTA HOLDINGS"
    viejo.loc[viejo["isin"] == "ES0139140174", "patron"] = r"^INMOBILIARIA COLONIAL\b"
    _, nr, _ = comprobar(viejo, nombres)
    ok(sorted(n for n, _ in nr) == ["Colonial", "Logista"], f"con los alias antiguos fallan Logista y Colonial ({nr})")
    print(f"{total - fallos} de {total} comprobaciones superadas." if not fallos else f"{fallos} de {total} comprobaciones fallan.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
