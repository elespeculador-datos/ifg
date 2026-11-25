"""Vigilancia de los comunicados de la CNMV: que ninguna empresa del IBEX 35 se quede sin comunicados.

Motivo (24/11/2026): Logista y Colonial firman hoy en la CNMV como «Logista Integral» y «Colonial SFL», y sus alias
de cnmv/empresas.csv eran los antiguos. El colector `cnmv` siguió terminando en «correcto» y sus fichas salieron
vacías durante trece meses sin que nada avisara. Esta pasada lee el listado que deja `cnmv`
(cnmv/datos/ibex35.csv, trece meses de comunicados de las empresas del IBEX 35 con su ISIN) y para con error, lo que
abre la incidencia `vigilancia-fallido`, si alguna empresa del IBEX 35:
  - no tiene ningún comunicado en el listado (alias que no reconoce su nombre actual), o
  - no tiene ninguno en los últimos DIAS_MAX días (150: en los trece meses hasta el 25/11/2026 el hueco más largo
    entre dos comunicados de una misma empresa fue de 110 días, el de Puig).

No descarga nada ni escribe en las salidas de otros colectores. Salida en --salida (en el servidor,
$ESPEC_DATOS_DIR/vigilancia/): datos/ultima.json, con el recuento y el último comunicado de cada empresa.

Uso: python3 vigilancia/vigilancia.py --salida <carpeta> [--cnmv <ruta o URL de ibex35.csv>] [--fecha AAAA-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cnmv"))
import comunicados as cn  # noqa: E402  (solo lectura: composición del IBEX y alias)

VERSION = "1.0.0"
DIAS_MAX = 150


def leer_listado(origen: str) -> list[dict]:
    """Filas de cnmv/datos/ibex35.csv (ruta local o URL)."""
    if origen.startswith("http"):
        import requests
        r = requests.get(origen, timeout=60)
        r.raise_for_status()
        texto = r.text
    else:
        texto = Path(origen).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(texto)))


def revisar(listado: list[dict], empresas: pd.DataFrame, hoy: date) -> dict:
    """Recuento y último comunicado por empresa del IBEX 35, y la lista de problemas (vacía si todo está bien)."""
    por_isin: dict[str, dict] = {}
    for r in listado:
        isin, f = (r.get("isin") or "").strip(), (r.get("fecha") or "")[:10]
        if not isin or len(f) != 10:
            continue
        x = por_isin.setdefault(isin, {"n": 0, "ultimo": f})
        x["n"] += 1
        x["ultimo"] = max(x["ultimo"], f)
    filas, problemas = [], []
    if not listado:
        problemas.append("el listado de la CNMV está vacío")
    for e in empresas.itertuples():
        x = por_isin.get(e.isin)
        if x is None:
            filas.append({"isin": e.isin, "empresa": e.nombre, "comunicados": 0, "ultimo": None, "dias": None})
            if listado:
                problemas.append(f"{e.nombre} ({e.isin}): ningún comunicado en el listado de la CNMV; revisa su alias en "
                                 f"cnmv/empresas.csv («{e.patron}») frente al nombre con el que firma hoy en la CNMV")
            continue
        dias = (hoy - date.fromisoformat(x["ultimo"])).days
        filas.append({"isin": e.isin, "empresa": e.nombre, "comunicados": x["n"], "ultimo": x["ultimo"], "dias": dias})
        if dias > DIAS_MAX:
            problemas.append(f"{e.nombre} ({e.isin}): último comunicado el {x['ultimo']}, hace {dias} días (más de {DIAS_MAX}); "
                             f"revisa si ha cambiado de nombre en la CNMV")
    return {"version": VERSION, "fecha": hoy.isoformat(), "dias_max": DIAS_MAX, "empresas": filas, "problemas": problemas,
            "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main() -> int:
    p = argparse.ArgumentParser(description="Vigilancia: ninguna empresa del IBEX 35 sin comunicados de la CNMV")
    p.add_argument("--salida", required=True)
    p.add_argument("--cnmv", default=None, help="ruta o URL de cnmv/datos/ibex35.csv (por defecto, <carpeta madre de --salida>/cnmv/datos/ibex35.csv)")
    p.add_argument("--fecha", default=None)
    a = p.parse_args()
    salida = Path(a.salida)
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(timezone.utc).astimezone().date()
    origen = a.cnmv or str(salida.resolve().parent / "cnmv" / "datos" / "ibex35.csv")
    try:
        listado = leer_listado(origen)
        empresas = cn.empresas_ibex(pd.Timestamp(hoy))
    except Exception as e:  # sin listado o composición vencida: también es un fallo que hay que ver
        print(f"::error::vigilancia: {type(e).__name__}: {e}")
        return 1
    res = revisar(listado, empresas, hoy)
    (salida / "datos").mkdir(parents=True, exist_ok=True)
    (salida / "datos" / "ultima.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    con = [f for f in res["empresas"] if f["comunicados"]]
    print(f"vigilancia: {len(con)} de {len(res['empresas'])} empresas del IBEX 35 con comunicados en el listado "
          f"({len(listado)} filas); problemas: {len(res['problemas'])}")
    for x in res["problemas"]:
        print(f"::error::vigilancia: {x}")
    return 1 if res["problemas"] else 0


if __name__ == "__main__":
    sys.exit(main())
