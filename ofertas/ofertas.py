"""OPAs sobre sociedades cotizadas en España, desde el registro oficial de la CNMV.

Indicador 11 del catálogo de Datos de El Especulador («Dividendos y OPAs (CNMV)», segunda parte). Sustituto legal
del registro de BME de la página «OPAs en la bolsa española» (8588, P3 del catálogo: datos de BME sin licencia).
Lee el registro oficial de OPAs de la CNMV (Real Decreto 1066/2007), que publica cada OPA desde 1998:

  ListaOPAS?fechaDesde&fechaHasta   OPAs presentadas y pendientes de autorización, y OPAs autorizadas con su número
                                    de registro oficial
  opa.aspx?numReg=N&vista=0         datos generales (tipo, valores afectados, contraprestación, volumen),
                                    calendario (autorización, plazo de aceptación, prórroga, desistimiento) y
                                    observaciones
  opa.aspx?numReg=N&vista=2         resultado (positivo o negativo), fecha de publicación y aceptaciones (% OPA)

y publica en <salida>/ (en el servidor, $ESPEC_DATOS_DIR/ofertas/):

  fragmento-wp.html     OPAs en marcha, OPAs por año y todas las OPAs desde 2015, entre <!-- opas:inicio HUELLA -->
                        y <!-- opas:fin --> (las marcas de la página 8588)
  index.html            página propia de la salida
  datos/opas.csv        una OPA autorizada por fila (también es la memoria del colector)
  datos/presentadas.csv OPAs presentadas y pendientes de autorización
  datos/ultima.json     resumen versionado

Cada pasada pide el listado completo (una petición) y la ficha de las OPAs nuevas, de las que siguen abiertas y de
las que se resolvieron hace menos de 45 días; el histórico se carga poco a poco (60 OPAs por pasada). Los nombres de
oferentes que son personas físicas no se guardan ni se publican (regla del colector de accionistas). Sin precios de
mercado ni recomendación: la contraprestación es la de la oferta, tal como la registra la CNMV.

Uso:
  python ofertas/ofertas.py --salida $ESPEC_DATOS_DIR/ofertas
  python ofertas/ofertas.py --salida /tmp/ofertas --max 300 --fecha 2026-11-22
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "1.0.0"
LECTOR = "2026-11-22b"  # versión del lector de fichas: si cambia, las fichas se releen poco a poco (hasta el máximo por pasada)
AQUI = Path(__file__).resolve().parent
MADRID = ZoneInfo("Europe/Madrid")
CNMV = "https://www.cnmv.es/portal/Consultas/Folletos/"
URL_LISTA = CNMV + "ListaOPAS?fechaDesde={desde}&fechaHasta={hasta}"
URL_FICHA = CNMV + "opa.aspx?numReg={n}&vista={v}"
URL_REGISTRO = "https://www.cnmv.es/portal/Consultas/busqueda?id=22"
PAGINA_WP = "https://elespeculador.com/opas-bolsa-espanola/"
FICHAS = "https://elespeculador.com/ibex35/"
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/ofertas/"
DESDE = date(1998, 1, 1)
MAX_OPAS = 60
PAUSA = 0.5
DIAS_REVISAR = 45
DIAS_SIN_RESULTADO = 30  # sin resultado 30 días después del plazo: el registro no lo tiene (OPAs antiguas), no está pendiente
# Formas y palabras de sociedad que la regla de accionistas no recoge y aparecen entre los oferentes de OPAs (alemanas,
# francesas y portuguesas, vehículos de adquisición). Con un nombre de una sola palabra tampoco hay persona física posible.
OTRAS_ENTIDADES = {"AKTIENGESELLSCHAFT", "GESELLSCHAFT", "COMPAGNIE", "COMPANIE", "SOCIETE", "SOCIETA", "SOCIEDADE", "SOCIEDAD", "SGPS",
                   "LDA", "LIMITADA", "SEC", "SCA", "SCS", "SNC", "BIDCO", "HOLDCO", "TOPCO", "MIDCO", "INVESTMENTS", "INVERSIONES",
                   "PARTICIPACIONES", "PARTNERS", "SOCIMI", "SICAV", "BANCO", "BANK", "FUNDACION"}
DESDE_TABLA = 2015
UA = {"User-Agent": "Mozilla/5.0 (compatible; ElEspeculadorDatos/1.0; +https://elespeculador.com; datos@elespeculador.com)"}
COLUMNAS = ["numreg", "sociedad", "nif", "isin", "oferentes", "personas_fisicas", "tipo", "contraprestacion", "precio_eur", "modificada",
            "contraprestacion_inicial",
            "valores_afectados_pct", "volumen_eur", "fecha_presentacion", "fecha_autorizacion", "inicio_plazo", "fin_plazo",
            "fin_prorroga", "fecha_desistimiento", "resultado", "fecha_resultado", "aceptacion_pct", "prorrateo_pct",
            "observaciones", "enlace", "leido", "lector"]
COLUMNAS_PRESENTADAS = ["sociedad", "nif", "mercado", "fecha_presentacion", "oferentes", "personas_fisicas"]
AVISOS: list[str] = []


class DatosRaros(Exception):
    """La CNMV no responde o ha cambiado la forma de sus páginas: no se publica nada."""


# --------------------------------------------------------------------------- lectura de las páginas
def _sin_tildes(x: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", x) if not unicodedata.combining(c))


def _clave(th: str) -> str:
    return re.sub(r"\s+", " ", _sin_tildes(html.unescape(th)).replace("\xa0", " ")).strip().lower()


def _texto(celda: str) -> str:
    x = re.sub(r"</li>|<br\s*/?>", "\n", celda)
    x = html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in x.splitlines() if l.strip())


def _lista(celda: str) -> list[str]:
    items = re.findall(r"<li[^>]*>(.*?)</li>", celda, re.S)
    return [t for t in (_texto(i) for i in items) if t] if items else [t for t in _texto(celda).splitlines() if t]


def tabla(pagina: str, id_contiene: str) -> list[dict] | None:
    """Filas de la tabla cuyo id contiene `id_contiene`, como {cabecera normalizada: html de la celda}; None si no está."""
    m = re.search(r'<table[^>]*id="[^"]*' + re.escape(id_contiene) + r'"[^>]*>(.*?)</table>', pagina, re.S)
    if not m:
        return None
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        celdas = re.findall(r'<td[^>]*data-th="([^"]*)"[^>]*>(.*?)</td>', tr, re.S)
        if celdas:
            filas.append({_clave(k): v for k, v in celdas})
    return filas


def recortar(pagina: str) -> str:
    """Solo la parte de la página con los datos (para guardar copias pequeñas en las pruebas)."""
    i = pagina.find("ctl00_ContentPrincipal")
    j = pagina.find("<footer", max(i, 0))
    return pagina[max(i - 200, 0): j if j > 0 else len(pagina)] if i >= 0 else pagina


def _iso(x: str | None) -> str | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (x or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _num(x: str | None) -> float | None:
    t = (x or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else None
    except ValueError:
        return None


def _precio(texto: str) -> tuple[str, float | None]:
    """«3,510 Euros por acción» -> («3,510 € por acción», 3.51). «*» o un canje: el texto y None."""
    t = re.sub(r"\s+", " ", texto or "").strip()
    m = re.fullmatch(r"([\d.]+(?:,\d+)?)\s+Euros?\s+(por .+)", t, re.I)
    if m:
        return f"{m.group(1)} € {m.group(2).lower()}", _num(m.group(1))
    return ("" if t in ("", "*") else t), None


_REGLA_JURIDICA = None


def _persona_juridica():
    """La regla del colector de accionistas (accionistas/duenos.py), sin copiarla: una sola definición."""
    ruta = AQUI.parent / "accionistas" / "duenos.py"
    spec = importlib.util.spec_from_file_location("duenos_para_ofertas", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.persona_juridica


def es_entidad(nombre: str) -> bool:
    """Entidad según la regla del colector de accionistas, o con una forma o palabra de sociedad de OTRAS_ENTIDADES, o de una
    sola palabra. Lo que no, cuenta como persona física y no se nombra (el lado seguro: una entidad dudosa queda oculta)."""
    global _REGLA_JURIDICA
    if _REGLA_JURIDICA is None:
        _REGLA_JURIDICA = _persona_juridica()
    palabras = re.sub(r"[^A-Z0-9& ]", " ", _sin_tildes(nombre or "").upper().replace(".", "")).split()
    return bool(_REGLA_JURIDICA(nombre)) or len(palabras) == 1 or bool(set(palabras) & OTRAS_ENTIDADES)


def oferentes(autores: list[str]) -> tuple[list[str], int]:
    """Los oferentes que son entidades, tal como los registra la CNMV, y cuántas personas físicas quedan fuera."""
    entidades = [a for a in autores if es_entidad(a)]
    return entidades, len(autores) - len(entidades)


def leer_lista(pagina: str) -> tuple[list[dict], list[dict]]:
    """OPAs presentadas (pendientes de autorización) y autorizadas del listado de la CNMV."""
    autorizadas = tabla(pagina, "wOPASAutorizadas_gridOPAS")
    if autorizadas is None:
        raise DatosRaros("el listado de la CNMV no trae la tabla de OPAs autorizadas: ¿ha cambiado la página?")
    presentadas = tabla(pagina, "wOPASPresentadas_gridOPAS") or []
    pres = []
    for f in presentadas:
        ofe, pf = oferentes(_lista(f.get("autor / autores de la oferta", "")))
        nif = re.search(r"nif=([^\"&]+)", f.get("entidad objeto", ""))
        pres.append({"sociedad": _texto(f.get("entidad objeto", "")), "nif": nif.group(1) if nif else "",
                     "mercado": _texto(f.get("tipo de centro de negociacion", "")),
                     "fecha_presentacion": _iso(_texto(f.get("fecha presentacion", ""))) or "",
                     "oferentes": " | ".join(ofe), "personas_fisicas": pf})
    aut = []
    for f in autorizadas:
        n = _texto(f.get("no registro oficial", ""))
        if not n.isdigit():
            raise DatosRaros(f"número de registro oficial ilegible en el listado de la CNMV: {n!r}")
        aut.append({"numreg": n, "sociedad": _texto(f.get("entidad objeto", ""))})
    if not aut:
        raise DatosRaros("el listado de la CNMV no trae ninguna OPA autorizada desde 1998")
    return pres, aut


def leer_ficha(numreg: str, p0: str, p2: str) -> dict:
    """La ficha de una OPA: datos generales y calendario (vista 0) y resultado (vista 2)."""
    cab = tabla(p0, "ContentPrincipal_gridDatos")
    if not cab or _texto(cab[0].get("num. registro oficial", "")) != numreg:
        raise DatosRaros(f"la ficha de la OPA {numreg} no trae su cabecera: ¿ha cambiado la página?")
    c = cab[0]
    gen = (tabla(p0, "gridDatosGenerales") or [{}])[0]
    cal = (tabla(p0, "gridCalendarioOpa") or [{}])[0]
    obs = re.search(r'_pnObservaciones"[^>]*>.*?<p[^>]*>(.*?)</p>', p0, re.S)
    ofe, pf = oferentes(_lista(c.get("autor / autores de la oferta", "")))
    contra, precio = _precio(_texto(gen.get("contraprestacion / precio", "")))
    o = {"numreg": numreg, "sociedad": _texto(c.get("entidad objeto", "")), "nif": "", "isin": "",
         "oferentes": " | ".join(ofe), "personas_fisicas": pf, "tipo": _texto(gen.get("tipo de opa", "")),
         "contraprestacion": contra, "precio_eur": precio,
         "valores_afectados_pct": _num(_texto(gen.get("valores afectados (% capital)", ""))),
         "volumen_eur": _num(_texto(gen.get("volumen efectivo teorico (EUR)", gen.get("volumen efectivo teorico (€)", "")))),
         "fecha_presentacion": _iso(_texto(c.get("fechapresentacion", ""))),
         "fecha_autorizacion": _iso(_texto(cal.get("fecha de autorizacion", ""))),
         "inicio_plazo": _iso(_texto(cal.get("inicio plazo aceptacion", ""))),
         "fin_plazo": _iso(_texto(cal.get("fin plazo aceptacion", ""))),
         "fin_prorroga": _iso(_texto(cal.get("fin prorroga plazo aceptacion (ultima)", ""))),
         "fecha_desistimiento": _iso(_texto(cal.get("fecha de desistimiento", ""))),
         "resultado": "", "fecha_resultado": None, "aceptacion_pct": None, "prorrateo_pct": None,
         "observaciones": re.sub(r"\s+", " ", _texto(obs.group(1))) if obs else "",
         "enlace": URL_FICHA.format(n=numreg, v=0)}
    mods = tabla(p0, "gridModificacionesOpa") or []
    o["modificada"] = bool(mods)
    o["contraprestacion_inicial"] = ""
    if mods:
        ultima = max(mods, key=lambda m: _iso(_texto(m.get("fecha autorizacion modificaciones", ""))) or "")
        contra2, precio2 = _precio(_texto(ultima.get("contraprestacion / precio", "")))
        if contra2 != o["contraprestacion"] or precio2 != o["precio_eur"]:
            o["contraprestacion_inicial"] = o["contraprestacion"]
            o["contraprestacion"], o["precio_eur"] = contra2, precio2
    if (tabla(p2, "ContentPrincipal_gridDatos") or [{}])[0].get("num. registro oficial") is None:
        raise DatosRaros(f"la pestaña de resultado de la OPA {numreg} no trae su cabecera: ¿ha cambiado la página?")
    res = tabla(p2, "gridResultado")
    if res:
        o["resultado"] = _texto(res[0].get("resultado", ""))
        o["fecha_resultado"] = _iso(_texto(res[0].get("publicacion del resultado", "")))
    valores = tabla(p2, "wOPAResultado_gridValores") or []
    acciones = [v for v in valores if _texto(v.get("tipo valor", "")).lower().startswith("acci")] or valores
    if acciones:
        v = acciones[0]
        o["isin"] = _texto(v.get("isin", ""))
        o["aceptacion_pct"] = _num(_texto(v.get("% opa", "")))
        o["prorrateo_pct"] = _num(_texto(v.get("coeficiente prorrateo %", "")))
    return o


# --------------------------------------------------------------------------- red y memoria
def descargar(url: str, sesion=None, intentos: int = 3) -> str:
    import requests
    s = sesion or requests.Session()
    ultimo = None
    for i in range(intentos):
        try:
            r = s.get(url, headers=UA, timeout=(10, 90))
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
            ultimo = f"HTTP {r.status_code}, {len(r.text)} caracteres"
        except requests.RequestException as e:  # red o servidor
            ultimo = f"{type(e).__name__}: {e}"
        time.sleep([5, 15, 30][min(i, 2)])
    raise DatosRaros(f"la CNMV no responde ({url}): {ultimo}")


def _csv_leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def cargar(ruta: Path) -> dict[str, dict]:
    """Memoria del colector: datos/opas.csv de la pasada anterior, por número de registro."""
    memoria = {}
    for r in _csv_leer(ruta):
        o = dict(r)
        for k in ("precio_eur", "valores_afectados_pct", "volumen_eur", "aceptacion_pct", "prorrateo_pct"):
            o[k] = _float(o.get(k))
        for k in ("fecha_presentacion", "fecha_autorizacion", "inicio_plazo", "fin_plazo", "fin_prorroga", "fecha_desistimiento",
                  "fecha_resultado"):
            o[k] = o.get(k) or None
        o["personas_fisicas"] = int(o.get("personas_fisicas") or 0)
        o["modificada"] = o.get("modificada") == "True"
        memoria[o["numreg"]] = o
    return memoria


def _float(x: str | None) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def abierta(o: dict, hoy: date) -> bool:
    """Sin resultado ni desistimiento y con el plazo vivo o recién terminado: hay que volver a leerla."""
    return situacion(o, hoy)[0] in ("en_plazo", "autorizada", "pendiente", "sin_dato")


def por_leer(autorizadas: list[dict], memoria: dict, hoy: date, maximo: int) -> list[str]:
    """Qué fichas pedir: las abiertas, las nuevas (de la más reciente a la más antigua) y las resueltas hace poco."""
    limite = (hoy - timedelta(days=DIAS_REVISAR)).isoformat()
    abiertas = [a["numreg"] for a in autorizadas if a["numreg"] in memoria and abierta(memoria[a["numreg"]], hoy)]
    nuevas = [a["numreg"] for a in sorted(autorizadas, key=lambda a: -int(a["numreg"])) if a["numreg"] not in memoria]
    recientes = [a["numreg"] for a in autorizadas if a["numreg"] in memoria and not abierta(memoria[a["numreg"]], hoy)
                 and (memoria[a["numreg"]].get("fecha_resultado") or memoria[a["numreg"]].get("fecha_desistimiento") or "") >= limite
                 and memoria[a["numreg"]].get("leido", "")[:10] < hoy.isoformat()]
    relectura = [a["numreg"] for a in sorted(autorizadas, key=lambda a: -int(a["numreg"]))
                 if a["numreg"] in memoria and memoria[a["numreg"]].get("lector") != LECTOR]
    vistos, orden = set(), []
    for n in abiertas + nuevas + recientes + relectura:
        if n not in vistos:
            vistos.add(n)
            orden.append(n)
    return orden[:maximo]


def actualizar(hoy: date, memoria: dict, maximo: int = MAX_OPAS, pausa: float = PAUSA, bajar=None) -> tuple[dict, list[dict], int]:
    """Una pasada: listado completo y fichas pendientes. Devuelve la memoria al día, las presentadas y el total del registro."""
    if bajar is None:
        import requests
        sesion = requests.Session()

        def bajar(url: str) -> str:
            return descargar(url, sesion)
    lista = bajar(URL_LISTA.format(desde=DESDE.strftime("%d/%m/%Y"), hasta=hoy.strftime("%d/%m/%Y")))
    presentadas, autorizadas = leer_lista(lista)
    pedir = por_leer(autorizadas, memoria, hoy, maximo)
    fallos, leidas = [], 0
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for n in pedir:
        try:
            p0 = bajar(URL_FICHA.format(n=n, v=0))
            time.sleep(pausa)
            p2 = bajar(URL_FICHA.format(n=n, v=2))
            time.sleep(pausa)
            o = leer_ficha(n, p0, p2)
        except DatosRaros as e:
            fallos.append(f"{n}: {e}")
            continue
        o["leido"], o["lector"] = ahora, LECTOR
        memoria[n] = o
        leidas += 1
    for f in fallos:
        AVISOS.append(f"OPA {f}")
    if fallos and not leidas and len(fallos) >= 3:
        raise DatosRaros(f"ninguna de las {len(fallos)} fichas pedidas se ha podido leer: {fallos[0]}")
    vigentes = {a["numreg"] for a in autorizadas}
    return {n: o for n, o in memoria.items() if n in vigentes}, presentadas, len(autorizadas)


# --------------------------------------------------------------------------- cálculo
def situacion(o: dict, hoy: date) -> tuple[str, str]:
    """(clave, texto) de la situación de una OPA autorizada."""
    h = hoy.isoformat()
    r = (o.get("resultado") or "").strip()
    fin = o.get("fin_prorroga") or o.get("fin_plazo")
    if r:
        clave = {"positivo": "positivo", "negativo": "negativo"}.get(r.lower(), "otro")
        return clave, r
    if o.get("fecha_desistimiento"):
        return "desistida", f"Desistida el {_f(o['fecha_desistimiento'])}"
    if o.get("inicio_plazo") and o["inicio_plazo"] > h:
        return "autorizada", f"Autorizada; plazo de aceptación del {_f(o['inicio_plazo'])} al {_f(fin)}"
    if fin and fin >= h:
        return "en_plazo", f"En plazo de aceptación hasta el {_f(fin)}"
    if re.search(r"(comunic[óo]|anunci[óo]|present[óo]) (su )?desistimiento|ha desistido", o.get("observaciones") or "", re.IGNORECASE):
        return "desistida", "Desistida (consta en las observaciones de la CNMV)"
    if fin and fin >= (hoy - timedelta(days=DIAS_SIN_RESULTADO)).isoformat():
        return "pendiente", f"Plazo terminado el {_f(fin)}; resultado pendiente"
    if fin:
        return "sin_resultado", "Sin resultado en el registro de la CNMV"
    return "sin_dato", "Sin calendario en el registro"


def calcular(memoria: dict, presentadas: list[dict], total_registro: int, hoy: date) -> dict:
    opas = sorted(memoria.values(), key=lambda o: -int(o["numreg"]))
    for o in opas:
        o["situacion"], o["situacion_texto"] = situacion(o, hoy)
        o["anio"] = int((o.get("fecha_autorizacion") or o.get("fecha_presentacion") or "0")[:4] or 0)
    en_marcha = [o for o in opas if o["situacion"] in ("en_plazo", "autorizada", "pendiente")]
    resueltas = sorted([o for o in opas if o["situacion"] in ("positivo", "negativo", "otro") and o.get("fecha_resultado")],
                       key=lambda o: (o["fecha_resultado"], int(o["numreg"])), reverse=True)
    completo = len(opas) == total_registro and total_registro > 0
    anios = {}
    if completo:
        for o in opas:
            a = anios.setdefault(o["anio"], {"anio": o["anio"], "autorizadas": 0, "positivas": 0, "negativas": 0, "desistidas": 0,
                                             "sin_resultado": 0})
            a["autorizadas"] += 1
            k = {"positivo": "positivas", "negativo": "negativas", "desistida": "desistidas"}.get(o["situacion"], "sin_resultado")
            a[k] += 1
    return {"fecha": hoy.isoformat(), "presentadas": presentadas, "en_marcha": en_marcha,
            "ultima_resuelta": resueltas[0] if resueltas else None,
            "desde_tabla": [o for o in opas if o["anio"] >= DESDE_TABLA],
            "por_anio": [anios[k] for k in sorted(anios, reverse=True) if k],
            "cobertura": {"registro": total_registro, "leidas": len(opas), "completa": completo,
                          "personas_fisicas_excluidas": sum(o.get("personas_fisicas") or 0 for o in opas)
                          + sum(p.get("personas_fisicas") or 0 for p in presentadas)},
            "todas": opas}


def huella(res: dict) -> str:
    campos = ("numreg", "sociedad", "oferentes", "tipo", "contraprestacion", "inicio_plazo", "fin_plazo", "fin_prorroga",
              "fecha_desistimiento", "resultado", "fecha_resultado", "aceptacion_pct", "situacion")
    base = {"version": VERSION, "presentadas": res["presentadas"], "cobertura": res["cobertura"],
            "opas": [[o.get(c) for c in campos] for o in res["todas"]]}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- textos
def _f(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso and len(iso) >= 10 else "—"


def _pct(x: float | None) -> str:
    if x is None:
        return "—"
    t = f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " %"
    return t + (" (oferta parcial sobresuscrita: hubo prorrateo)" if x > 100 else "")


def _alnum(x: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _sin_tildes((x or "").upper()))


def _oferente_txt(o: dict) -> str:
    nombres = [n for n in (o.get("oferentes") or "").split(" | ") if n]
    if len(nombres) == 1 and _alnum(nombres[0])[:9] == _alnum(o.get("sociedad"))[:9]:
        texto = "La propia sociedad"
    else:
        texto = " · ".join(html.escape(n) for n in nombres)
    pf = int(o.get("personas_fisicas") or 0)
    if pf:
        extra = f"{pf} persona{'s' if pf > 1 else ''} física{'s' if pf > 1 else ''}"
        texto = f"{texto} y {extra}" if texto else extra.capitalize()
    return texto or "—"


def _contra_txt(o: dict) -> str:
    if o.get("contraprestacion"):
        extra = f" (modificada; la inicial era {o['contraprestacion_inicial']})" if o.get("contraprestacion_inicial") else ""
        return html.escape(o["contraprestacion"] + extra)
    return f'<a href="{html.escape(o["enlace"])}">ver la ficha de la CNMV</a>' if o.get("enlace") else "—"


def frase(res: dict) -> str:
    pres, marcha = res["presentadas"], res["en_marcha"]
    n = len(pres) + len(marcha)
    if not n:
        texto = "Ahora mismo no hay ninguna OPA en marcha en el registro de la CNMV."
    else:
        partes = []
        if pres:
            nombres = ", ".join(html.escape(p["sociedad"]) for p in pres[:3]) + ("…" if len(pres) > 3 else "")
            partes.append(f"{len(pres)} presentada{'s' if len(pres) > 1 else ''} y pendiente{'s' if len(pres) > 1 else ''} de "
                          f"autorización ({nombres})")
        if marcha:
            nombres = ", ".join(html.escape(o["sociedad"]) for o in marcha[:3]) + ("…" if len(marcha) > 3 else "")
            partes.append(f"{len(marcha)} autorizada{'s' if len(marcha) > 1 else ''} y sin resultado todavía ({nombres})")
        texto = (f"Hay <strong>{n} OPA{'s' if n > 1 else ''} en marcha</strong> sobre sociedades cotizadas en España según el "
                 f"registro de la CNMV: " + " y ".join(partes) + ".")
    u = res.get("ultima_resuelta")
    if u:
        quien = _oferente_txt(u)
        quien = "la propia sociedad" if quien == "La propia sociedad" else quien
        texto += (f" La última con resultado es la de {quien} sobre {html.escape(u['sociedad'])}: "
                  f"{html.escape(u['resultado'].lower())}")
        if u.get("aceptacion_pct") is not None:
            texto += f", con el {_pct(u['aceptacion_pct']).split(' (')[0]} de los valores a los que se dirigía"
        texto += f" (resultado publicado el {_f(u['fecha_resultado'])})."
    return texto


def _tabla(cabeceras: list[str], filas: list[list[str]]) -> str:
    cab = "".join(f"<th>{c}</th>" for c in cabeceras)
    cuerpo = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return f'<figure class="wp-block-table"><table><thead><tr>{cab}</tr></thead><tbody>\n{cuerpo}\n</tbody></table></figure>'


def ld_wp(fecha: str) -> str:
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "OPAs sobre sociedades cotizadas en España, desde el registro oficial de la CNMV (El Especulador)",
        "description": "Ofertas públicas de adquisición registradas por la CNMV desde 1998: sociedad, oferente, tipo, contraprestación, "
                       "plazo de aceptación, resultado y porcentaje aceptado, y las OPAs presentadas pendientes de autorización.",
        "url": PAGINA_WP, "inLanguage": "es", "spatialCoverage": "España",
        "creator": {"@type": "Organization", "name": "El Especulador", "url": "https://elespeculador.com/"},
        "creditText": "El Especulador, a partir del registro oficial de OPAs de la CNMV", "isBasedOn": URL_REGISTRO,
        "license": "https://creativecommons.org/licenses/by/4.0/", "dateModified": fecha,
        "distribution": [{"@type": "DataDownload", "encodingFormat": t, "contentUrl": f"{PAGES}datos/{n}"}
                         for n, t in (("opas.csv", "text/csv"), ("presentadas.csv", "text/csv"), ("ultima.json", "application/json"))],
    }, ensure_ascii=False) + "</script>"


def fragmento(res: dict, fecha_pub: str) -> str:
    cob = res["cobertura"]
    partes = [f"<!-- opas:inicio {res['huella']} -->",
              (f'<p class="has-small-font-size">Actualizado el {_f(fecha_pub)}. Registro oficial de OPAs de la CNMV, revisado cada día '
               "hábil.</p>"),
              "<p>" + frase(res) + "</p>",
              "<h2>OPAs en marcha</h2>"]
    filas = [[html.escape(p["sociedad"]), _oferente_txt(p), f"Presentada el {_f(p['fecha_presentacion'])}; pendiente de autorización",
              "—", f'<a href="{URL_REGISTRO}">registro de la CNMV</a>'] for p in res["presentadas"]]
    filas += [[html.escape(o["sociedad"]), _oferente_txt(o), html.escape(o["situacion_texto"]), _contra_txt(o),
               f'<a href="{html.escape(o["enlace"])}">ficha {o["numreg"]}</a>'] for o in res["en_marcha"]]
    if filas:
        partes.append(_tabla(["Sociedad", "Oferente", "Situación", "Precio o contraprestación", "CNMV"], filas))
    else:
        partes.append("<p>Ahora mismo no hay ninguna OPA presentada ni en plazo de aceptación.</p>")
    if cob["completa"] and res["por_anio"]:
        partes.append("<h2>OPAs por año</h2>")
        partes.append('<p class="has-small-font-size">Por año de autorización. Desde 1998, el primer año del registro en línea de la '
                      "CNMV.</p>")
        partes.append(_tabla(["Año", "Autorizadas", "Positivas", "Negativas", "Desistidas", "Sin resultado"],
                             [[str(a["anio"]), str(a["autorizadas"]), str(a["positivas"]), str(a["negativas"]), str(a["desistidas"]),
                               str(a["sin_resultado"])] for a in res["por_anio"]]))
    partes.append(f"<h2>Todas las OPAs desde {DESDE_TABLA}</h2>")
    if not cob["completa"]:
        partes.append(f'<p class="has-small-font-size">Histórico en carga: {cob["leidas"]} de {cob["registro"]} OPAs del registro '
                      "leídas; se completa en las próximas pasadas.</p>")
    partes.append("<p>De la más reciente a la más antigua. La aceptación es la parte de los valores a los que se dirigía la oferta "
                  "que acudió a ella, según la CNMV; en una oferta parcial con prorrateo puede pasar del 100 %. Si la contraprestación "
                  "es un canje o tiene condiciones, el detalle está en la ficha de la CNMV.</p>")
    partes.append(_tabla(["Sociedad", "Oferente", "Tipo", "Precio o contraprestación", "Plazo de aceptación", "Aceptación", "Resultado"],
                         [[html.escape(o["sociedad"]), _oferente_txt(o), html.escape(o.get("tipo") or "—"), _contra_txt(o),
                           (f"{_f(o.get('inicio_plazo'))} – {_f(o.get('fin_prorroga') or o.get('fin_plazo'))}"
                            if o.get("inicio_plazo") else "—"),
                           _pct(o.get("aceptacion_pct")) if o.get("resultado") else "—",
                           f'<a href="{html.escape(o["enlace"])}">{html.escape(o["situacion_texto"])}</a>']
                          for o in res["desde_tabla"]]))
    partes.append('<h2 id="metodo">De dónde sale y cómo se lee</h2>'
                  "<p>Toda OPA sobre una sociedad cuyas acciones cotizan en la bolsa española necesita la autorización de la CNMV, que la "
                  "inscribe en su registro oficial con un número, el folleto, el calendario del plazo de aceptación y, al terminar, el "
                  "resultado. Las ofertas sobre valores de BME Growth o de Latibex no pasan por ese registro y no están aquí. El Especulador "
                  "lee el registro cada día hábil y lo ordena en tres partes: las presentadas que esperan autorización, las autorizadas que "
                  "aún no tienen resultado y el histórico. El precio es el que ofrece el oferente, tal como lo registra la CNMV en la autorización o en "
                  "la última modificación; no es una cotización, y si el folleto prevé ajustes (por ejemplo, por un dividendo pagado durante "
                  "la oferta), el pagado puede ser algo distinto. Los oferentes que son personas físicas no se nombran.</p>")
    partes.append('<p class="has-small-font-size">Fuente: CNMV, <a href="' + URL_REGISTRO + '">registro oficial de OPAs</a>, reproducido '
                  "fielmente (gratuito en cnmv.es). La selección y las tablas son de El Especulador y se publican con licencia "
                  '<a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>. Contenido informativo y educativo; no '
                  "es asesoramiento financiero ni recomendación de inversión.</p>")
    partes.append(ld_wp(fecha_pub))
    partes.append("<!-- opas:fin -->")
    return "\n".join(partes)


def pagina_index(frag: str, fecha: str) -> str:
    cuerpo = "\n".join(l for l in frag.split("\n")[1:-1] if "application/ld+json" not in l)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>OPAs en España desde el registro de la CNMV · El Especulador</title>
<meta name="description" content="OPAs sobre sociedades cotizadas en España desde el registro oficial de la CNMV: en marcha, por año y una a una.">
<style>body{{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:.3rem;text-align:left;font-size:.9rem}}.has-small-font-size{{font-size:.85rem;color:#555}}</style>
</head><body>
<h1>OPAs en España, desde el registro de la CNMV</h1>
{cuerpo}
<h2>Datos abiertos</h2>
<p><a href="datos/opas.csv">opas.csv</a> · <a href="datos/presentadas.csv">presentadas.csv</a> · <a href="datos/ultima.json">ultima.json</a> · versión {VERSION} · {fecha}</p>
</body></html>
"""


# --------------------------------------------------------------------------- escritura
def _atomico(ruta: Path, texto: str) -> None:
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def _csv_escribir(ruta: Path, filas: list[dict], columnas: list[str]) -> None:
    tmp = ruta.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        for r in filas:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columnas})
    os.replace(tmp, ruta)


def escribir(res: dict, hoy: date, salida: Path, forzar: bool = False) -> bool:
    """Escribe la memoria siempre (es el estado del colector) y lo publicado solo si cambia la huella o falta algo."""
    dd = salida / "datos"
    dd.mkdir(parents=True, exist_ok=True)
    _csv_escribir(dd / "opas.csv", res["todas"], COLUMNAS)
    _csv_escribir(dd / "presentadas.csv", res["presentadas"], COLUMNAS_PRESENTADAS)
    previo = dd / "ultima.json"
    try:
        antes = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    except ValueError:
        antes = {}
    cambia = antes.get("huella") != res["huella"]
    falta = not all((salida / n).exists() for n in ("fragmento-wp.html", "index.html")) or not previo.exists()
    if not (cambia or falta or forzar):
        return False
    fecha_pub = hoy.isoformat() if cambia else antes.get("fecha_publicacion", hoy.isoformat())
    resumen = {"version": VERSION, "fecha": res["fecha"], "fecha_publicacion": fecha_pub, "huella": res["huella"],
               "comprobado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "presentadas": res["presentadas"],
               "en_marcha": [{k: o.get(k) for k in COLUMNAS + ["situacion", "situacion_texto"] if k != "observaciones"}
                             for o in res["en_marcha"]],
               "ultima_resuelta": ({k: res["ultima_resuelta"].get(k) for k in COLUMNAS if k != "observaciones"}
                                   if res["ultima_resuelta"] else None),
               "por_anio": res["por_anio"], "cobertura": res["cobertura"], "avisos": AVISOS,
               "fuente": "CNMV, registro oficial de OPAs (" + URL_REGISTRO + ")",
               "condiciones": "Datos de la CNMV reproducidos fielmente (gratuitos en cnmv.es); selección y tablas de El Especulador "
                              "(CC BY 4.0). Sin nombres de personas físicas. Contenido informativo; no es asesoramiento financiero."}
    _atomico(previo, json.dumps(resumen, ensure_ascii=False, indent=1, allow_nan=False, default=str))
    frag = fragmento(res, fecha_pub)
    assert "$" not in frag and frag.count("<!-- opas:fin -->") == 1
    _atomico(salida / "fragmento-wp.html", frag + "\n")
    _atomico(salida / "index.html", pagina_index(frag, fecha_pub))
    return cambia


# --------------------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--max", type=int, default=MAX_OPAS, help="fichas de OPA por pasada (dos peticiones cada una)")
    ap.add_argument("--fecha", help="día de referencia AAAA-MM-DD (por defecto, hoy en Madrid)")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    salida = Path(a.salida)
    hoy = date.fromisoformat(a.fecha) if a.fecha else datetime.now(MADRID).date()
    try:
        memoria = cargar(salida / "datos" / "opas.csv")
        memoria, presentadas, total = actualizar(hoy, memoria, maximo=a.max)
    except DatosRaros as e:
        print(f"::error::ofertas: {e}")
        return 1
    res = calcular(memoria, presentadas, total, hoy)
    res["huella"] = huella(res)
    cambia = escribir(res, hoy, salida, forzar=a.forzar)
    for av in AVISOS:
        print(f"::warning::{av}")
    cob = res["cobertura"]
    print(f"OPAs del {hoy}: {len(presentadas)} presentadas pendientes de autorización, {len(res['en_marcha'])} autorizadas sin resultado; "
          f"histórico {cob['leidas']} de {cob['registro']} ({'completo' if cob['completa'] else 'en carga'}); "
          f"personas físicas excluidas de los oferentes: {cob['personas_fisicas_excluidas']}. {'Datos nuevos.' if cambia else 'Sin cambios.'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
