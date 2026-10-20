"""Bloque «en datos» para las fichas de empresa del IBEX 35 de El Especulador.

Junta en una tabla corta lo que ya publicamos por separado y lo que da BME
para cada valor: capitalización y puesto en la bolsa, rentabilidad de la
acción (solo precio), dividendos de los últimos doce meses, posiciones cortas
publicadas, OPAs desde 2000 y tasa Tobin.

Reglas:
  - Un dato que falta o no cuadra no se muestra; si faltan más de dos, no se
    genera el bloque de esa empresa.
  - Nada de recomendaciones ni de valoraciones: solo datos con su fecha y su
    fuente.
  - El bloque va entre <!-- fichas:inicio AAAA-MM-DD --> y <!-- fichas:fin -->.

Uso (pruebas, sin red):
  python fichas/bloque.py --datos DIR --salida DIR [--slugs iberdrola,aena]
  DIR contiene cotizadas.json (ListedCompanies), historicos.json
  ({isin: [[fecha, cierre, facMult, facDivi], ...]}), paginas.json e itf_2026.json.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
PADRE_IBEX = 8258
METODOLOGIA = "https://elespeculador-datos.github.io/ifg/fichas/"
ENLACES = {
    "cortos": "https://elespeculador.com/posiciones-cortas-hoy/",
    "dividendos": "https://elespeculador.com/calendario-dividendos/",
    "opas": "https://elespeculador.com/opas-bolsa-espanola/",
    "tobin": "https://elespeculador.com/tasa-tobin-acciones-2026/",
}
# Fichas cuyo slug no basta para encontrar la acción en BME
SLUG_ISIN = {
    "iberdrola": "ES0144580Y14", "banco-santander": "ES0113900J37", "inditex": "ES0148396007",
    "aena": "ES0105046017", "bbva": "ES0113211835", "caixabank": "ES0140609019",
    "telefonica": "ES0178430E18", "repsol": "ES0173516115", "acs": "ES0167050915",
    "amadeus": "ES0109067019", "arcelormittal": "LU1598757687", "ferrovial": "NL0015001FS8",
    "iag": "ES0177542018", "naturgy": "ES0116870314", "endesa": "ES0130670112",
    "cellnex": "ES0105066007", "banco-sabadell": "ES0113860A34", "bankinter": "ES0113679I37",
    "redeia": "ES0173093024", "mapfre": "ES0124244E34", "grifols": "ES0171996087",
    "enagas": "ES0130960018", "acciona": "ES0125220311", "acciona-energia": "ES0105563003",
    "acerinox": "ES0132105018", "colonial": "ES0139140174", "fluidra": "ES0137650018",
    "indra": "ES0118594417", "logista": "ES0105027009", "merlin-properties": "ES0105025003",
    "puig": "ES0105777017", "rovi": "ES0157261019", "sacyr": "ES0182870214",
    "solaria": "ES0165386014", "unicaja": "ES0180907000", "cie-automotive": "ES0105630315",
}
# Empresas con otra clase de acción que no cotiza o que no está en la lista de BME:
# la capitalización de BME es solo la de la clase que cotiza.
UNA_CLASE = {"ES0171996087": "solo la clase A", "ES0105777017": "solo la clase B, la que cotiza"}


# Series cortas que no son una salida a bolsa
NOTA_HIST = {"NL0015001FS8": "la acción actual cotiza desde el cambio de sede a Países Bajos, en junio de 2023"}


# Nombres anteriores de la misma sociedad en el registro de OPAs de BME
OPAS_ALIAS = {"ES0139140174": ["INMOBILIARIA COLONIAL, S.A."]}


class SinDatos(Exception):
    pass


# --------------------------------------------------------------------------- formato
def _num(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x: float, signo: bool = True) -> str:
    s = _num(abs(x), 1) + " %"
    if not signo:
        return s
    return ("+" if x > 0 else "−" if x < 0 else "") + s


def _eur(x: float) -> str:
    t = _num(x, 3)
    return (t[:-1] if t.endswith("0") else t) + " €"


def _f(d: date | str) -> str:
    if isinstance(d, str):
        d = datetime.strptime(d.replace("-", "")[:8], "%Y%m%d").date()
    return d.strftime("%d/%m/%Y")


def _millones(eur: float) -> str:
    return f"{_num(eur / 1e6)} millones de euros"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    quita = {"SA", "S", "A", "SE", "SOCIMI", "SME", "GRUPO", "GROUP", "CIA", "DE", "DEL", "LA", "EL", "Y", "CORPORACION", "CANCELAD"}
    return " ".join(w for w in s.split() if w not in quita)


# --------------------------------------------------------------------------- datos
def cargar(datos: Path) -> dict:
    cot = json.loads((datos / "cotizadas.json").read_text(encoding="utf-8"))
    hist = json.loads((datos / "historicos.json").read_text(encoding="utf-8"))
    pag = json.loads((datos / "paginas.json").read_text(encoding="utf-8"))
    itf = set(json.loads((datos / "itf_2026.json").read_text(encoding="utf-8")))

    def leer(p: Path) -> list[dict]:
        return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []

    return {
        "cot": {c["isin"]: c for c in cot},
        "hist": hist, "itf": itf,
        "fichas": [p for p in pag if p["parent"] == PADRE_IBEX],
        "cortos": {r["isin"]: r for r in leer(DOCS / "cortos" / "datos" / "resumen_emisores.csv")},
        "rent": {r["isin"]: r for r in leer(DOCS / "dividendos" / "datos" / "rentabilidad.csv")},
        "prox": leer(DOCS / "dividendos" / "datos" / "proximos.csv"),
        "opas": leer(DOCS / "opas" / "datos" / "opas.csv"),
    }


def puesto(isin: str, cot: dict) -> tuple[int, int]:
    """Puesto de la empresa por capitalización entre todas las del mercado continuo (SIBE)."""
    por_empresa: dict[str, float] = {}
    for c in cot.values():
        if c.get("capitalisation"):
            por_empresa[c["companyKey"]] = por_empresa.get(c["companyKey"], 0) + float(c["capitalisation"])
    orden = sorted(por_empresa, key=lambda k: -por_empresa[k])
    return orden.index(cot[isin]["companyKey"]) + 1, len(orden)


def rentabilidades(serie: list) -> dict:
    """Rentabilidad de la acción a 1, 3 y 5 años, solo precio, con los cierres ajustados de BME.

    El cierre de referencia es el último del día equivalente de hace N años o de
    los diez días anteriores; si la serie empieza justo después (la API da cinco
    años exactos), vale el primero de los cinco días siguientes.
    """
    filas = sorted((datetime.strptime(str(f[0]), "%Y%m%d").date(), float(f[1])) for f in serie if f[1])
    if len(filas) < 200:
        raise SinDatos("pocos cierres")
    fin, ultimo = filas[-1]
    out = {"fecha": fin, "desde": filas[0][0]}
    for anios in (1, 3, 5):
        try:
            ref = fin.replace(year=fin.year - anios)
        except ValueError:  # 29 de febrero
            ref = fin.replace(year=fin.year - anios, day=28)
        antes = [(f, c) for f, c in filas if f <= ref]
        base = None
        if antes and (ref - antes[-1][0]).days <= 10:
            base = antes[-1][1]
        elif not antes and 0 < (filas[0][0] - ref).days <= 5:
            base = filas[0][1]
        if base:
            out[anios] = (ultimo / base - 1) * 100
    return out


def opas_de(nombre: str, opas: list[dict]) -> list[dict]:
    """OPAs cuya sociedad afectada es esta empresa: el mismo nombre de BME, o su
    comienzo cuando BME lo corta (unos 35 caracteres)."""
    n = _norm(nombre)
    salida = []
    for o in opas:
        s = _norm(o["sociedad"])
        if s and (s == n or (len(o["sociedad"]) >= 34 and n.startswith(s))):
            salida.append(o)
    return salida


# --------------------------------------------------------------------------- bloque
def bloque(slug: str, titulo: str, d: dict, hoy: date) -> str:
    isin = SLUG_ISIN.get(slug)
    c = d["cot"].get(isin or "")
    if not c:
        raise SinDatos(f"{slug}: sin cotización en BME")
    filas: list[tuple[str, str]] = []
    faltan = 0

    # capitalización y puesto
    try:
        n, total = puesto(isin, d["cot"])
        nota = f" ({UNA_CLASE[isin]})" if isin in UNA_CLASE else ""
        filas.append(("Capitalización", f"{_millones(float(c['capitalisation']))}{nota}: la {n}.ª de las {total} empresas del mercado continuo"))
    except (KeyError, ValueError, TypeError):
        faltan += 1

    # rentabilidad de la acción
    try:
        r = rentabilidades(d["hist"][isin])
        partes = [f"En {r['fecha'].year}, {_pct(float(c['annualDifference']) * 100)}"]
        for a in (1, 3, 5):
            if a in r:
                partes.append(f"a {a} año{'s' if a > 1 else ''}, {_pct(r[a])}")
        if 5 not in r:
            partes.append(NOTA_HIST.get(isin, f"cotiza desde el {_f(r['desde'])}"))
        filas.append(("Rentabilidad de la acción", "; ".join(p for p in partes if p) + ". Solo precio, sin dividendos"))
        fecha_datos = r["fecha"]
    except (KeyError, SinDatos, ValueError):
        faltan += 1
        fecha_datos = None

    # dividendos (el calendario solo lista las que han pagado en doce meses)
    rd = d["rent"].get(isin)
    prox = sorted((p for p in d["prox"] if p["isin"] == isin and p["fecha_ex"] >= hoy.isoformat()), key=lambda p: p["fecha_ex"])
    enlace = f' · <a href="{ENLACES["dividendos"]}">calendario</a>'
    if not d["rent"]:
        faltan += 1
    elif rd and float(rd["bruto_total"] or 0) > 0:
        total, ordin = float(rd["bruto_total"]), float(rd["bruto_ordinario"] or 0)
        pagos = "un pago" if rd["pagos"] == "1" else f"{rd['pagos']} pagos"
        txt = f"{_eur(total)} brutos por acción en {pagos}"
        if total - ordin > 0.0005:
            txt += (f", {_eur(total - ordin)} de ellos extraordinarios: un {_pct(float(rd['rentabilidad_pct']), False)} sobre el cierre, "
                    f"o un {_pct(float(rd['rentabilidad_ordinaria_pct']), False)} sin el extraordinario")
        else:
            txt += f": un {_pct(float(rd['rentabilidad_pct']), False)} sobre el cierre"
        if prox:
            txt += f". Próxima fecha ex: {_f(prox[0]['fecha_ex'])} ({_eur(float(prox[0]['bruto']))})"
        filas.append(("Dividendos de los últimos 12 meses", txt + enlace))
    else:
        txt = "Ninguno"
        if prox:
            txt += f". Próxima fecha ex: {_f(prox[0]['fecha_ex'])} ({_eur(float(prox[0]['bruto']))})"
        filas.append(("Dividendos de los últimos 12 meses", txt + enlace))

    # posiciones cortas
    co = d["cortos"].get(isin)
    if co and co["tenedores"] == "1":
        filas.append(("Posiciones cortas publicadas",
                      f"Una: {html.escape(co['mayor_tenedor'])}, con un {_pct(float(co['mayor_posicion_pct']), False)} del capital"
                      f' · <a href="{ENLACES["cortos"]}">todas las posiciones</a>'))
    elif co:
        filas.append(("Posiciones cortas publicadas",
                      f"{co['tenedores']} fondos con un {_pct(float(co['suma_publicada_pct']), False)} del capital en total; "
                      f"la mayor, {html.escape(co['mayor_tenedor'])}, con un {_pct(float(co['mayor_posicion_pct']), False)}"
                      f' · <a href="{ENLACES["cortos"]}">todas las posiciones</a>'))
    else:
        filas.append(("Posiciones cortas publicadas",
                      f'Ninguna: no hay posiciones del 0,5 % o más · <a href="{ENLACES["cortos"]}">todas las posiciones</a>'))

    # OPAs
    ops = opas_de(c["name"], d["opas"])
    for alias in OPAS_ALIAS.get(isin, []):
        ops += [o for o in opas_de(alias, d["opas"]) if o not in ops]
    if ops:
        ult = max(ops, key=lambda o: o["inicio_aceptacion"])
        filas.append(("OPAs sobre la empresa desde 2000",
                      f"{len(ops)}; la última, de {'la propia sociedad (recompra de acciones)' if ult['oferente'] == 'La propia sociedad' else html.escape(ult['oferente'])} en {ult['inicio_aceptacion'][:4]} ({ult['resultado'].lower()})"
                      f' · <a href="{ENLACES["opas"]}">registro</a>'))
    else:
        filas.append(("OPAs sobre la empresa desde 2000", f'Ninguna · <a href="{ENLACES["opas"]}">registro</a>'))

    # tasa Tobin
    if isin.startswith("ES"):
        filas.append(("Tasa Tobin en 2026", ("Sí: las compras pagan el 0,2 %" if isin in d["itf"] else "No: no está en la lista de la AEAT")
                      + f' · <a href="{ENLACES["tobin"]}">la lista</a>'))
    else:
        filas.append(("Tasa Tobin en 2026", "No: es una sociedad extranjera"))

    if faltan > 2 or not fecha_datos:
        raise SinDatos(f"{slug}: faltan {faltan} datos")
    cuerpo = "\n".join(f'<tr><th scope="row">{h}</th><td>{v}</td></tr>' for h, v in filas)
    nombre = html.escape(titulo.split(":")[0].strip())
    return (f"<!-- fichas:inicio {hoy.isoformat()} -->\n"
            f'<h2 class="wp-block-heading">{nombre} en datos</h2>\n'
            f'<figure class="wp-block-table"><table><tbody>\n{cuerpo}\n</tbody></table></figure>\n'
            f'<p class="has-small-font-size">Datos al cierre del {_f(fecha_datos)}. Fuentes: BME, CNMV y AEAT. '
            f'<a href="{METODOLOGIA}">Cómo se calcula cada dato</a>.</p>\n'
            f"<!-- fichas:fin -->")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--slugs", default="")
    ap.add_argument("--hoy", default=date.today().isoformat())
    a = ap.parse_args()
    d = cargar(Path(a.datos))
    hoy = date.fromisoformat(a.hoy)
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    quiero = set(filter(None, a.slugs.split(",")))
    hechos, fallos = [], []
    for f in d["fichas"]:
        if quiero and f["slug"] not in quiero:
            continue
        titulo = html.unescape(re.sub("<[^>]+>", "", f["title"] or f["slug"]))
        try:
            b = bloque(f["slug"], titulo, d, hoy)
            (out / f"{f['slug']}.html").write_text(b, encoding="utf-8")
            hechos.append(f["slug"])
        except SinDatos as e:
            fallos.append(str(e))
    print(f"{len(hechos)} bloques; sin bloque: {fallos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
