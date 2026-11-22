"""Comunicados a la CNMV de las empresas del IBEX 35, clasificados para la página del IBEX de El Especulador.

Cada hora de los días hábiles lee los dos canales RSS públicos de la CNMV (información privilegiada y otra
información relevante). Cada canal solo muestra lo comunicado desde el cierre de la sesión anterior, así que
el script va acumulando todo en un histórico y, a partir de él, publica:

  docs/cnmv/datos/comunicados.csv   todos los comunicados leídos, de cualquier emisor, sin clasificar
  docs/cnmv/datos/ibex35.csv        los del IBEX 35, con su tipo y el grupo (operación) al que pertenecen
  docs/cnmv/datos/ultima.json       resumen
  docs/cnmv/cajas.html              los cuatro recuadros de la página del IBEX 35 (resultados, dividendos,
                                    recompras, OPVs y ampliaciones), entre <!-- cnmv:inicio … --> y <!-- cnmv:fin -->
  docs/cnmv/index.html              página propia con los mismos datos

Regla de duplicados: dos comunicados distintos de la CNMV nunca se pisan (cada uno tiene su número de registro).
Lo que se agrupa es la operación: misma empresa, mismo tipo y misma operación (los informes semanales de un
programa de recompra, los dos comunicados de una misma ampliación, el anuncio de fecha y la publicación de unos
resultados) se muestran como una sola entrada con el último comunicado y el número de comunicados. Una ampliación
y un dividendo de la misma empresa son dos entradas distintas, cada una en su recuadro.

Relleno por número de registro (21/11/2026): el RSS no deja recuperar lo pasado ni trae los comunicados de los fondos
de titulización. En cada pasada, los números de registro que faltan entre los comunicados de los últimos 45 días se
piden uno a uno a la ficha pública de la CNMV (como ya hacía el colector de WordPress, fragmento 64). Así se recupera
cualquier hueco: el del 07/11 al 15/11/2026, cuando no corría ningún colector, y los que vengan.

Uso:
  python cnmv/comunicados.py                         descarga, rellena huecos y publica si hay novedades
  python cnmv/comunicados.py --local IP.xml OIR.xml  usa canales ya descargados (pruebas; sin relleno)
  python cnmv/comunicados.py --forzar                reescribe aunque no haya comunicados nuevos
  python cnmv/comunicados.py --sin-relleno           solo el RSS
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

CANALES = {
    "IP": "https://www.cnmv.es/portal/Informacion-Privilegiada/RSS.asmx/GetNoticiasCNMV",
    "OIR": "https://www.cnmv.es/portal/Otra-Informacion-Relevante/RSS.asmx/GetNoticiasCNMV",
}
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept": "application/rss+xml, application/xml, text/xml, */*"}
MADRID = ZoneInfo("Europe/Madrid")
RAIZ = Path(__file__).resolve().parent.parent
# Carpeta de salida. Por defecto, docs/cnmv del repositorio (GitHub Pages); en el
# servidor, ESPEC_DATOS_DIR apunta a la carpeta que sirve datos.elespeculador.com,
# fuera del git, para que git pull nunca choque con los datos.
SALIDA = Path(os.environ.get("ESPEC_DATOS_DIR", RAIZ / "docs")) / "cnmv"
DATOS = SALIDA / "datos"
HISTORICO = DATOS / "comunicados.csv"
EMPRESAS = Path(__file__).resolve().parent / "empresas.csv"
IBEX35 = RAIZ / "dividendos" / "ibex35.csv"      # la misma composición que usa el calendario de dividendos
IBEX35_VALIDA_HASTA = "2026-12-20"                 # mover junto con la de dividendos/calendario.py tras cada revisión
FICHAS = "https://elespeculador.com/ibex35/"
# Dirección pública de esta salida. Por defecto, GitHub Pages; en el servidor
# smpro-datos-1, la variable de entorno ESPEC_DATOS_BASE vale
# "https://datos.elespeculador.com/". Siempre termina en barra.
PAGES = os.environ.get("ESPEC_DATOS_BASE", "https://elespeculador-datos.github.io/ifg/").rstrip("/") + "/cnmv/"
DIAS_CAJA = 60          # antigüedad máxima de lo que sale en los recuadros
POR_CAJA = 6            # entradas por recuadro
COLUMNAS = ["canal", "nreg", "fecha", "emisor", "categoria", "texto", "enlace"]
# Ficha pública de cada comunicado por número de registro (relleno de huecos) y forma del enlace que guarda el RSS.
FICHA_CNMV = {"IP": "https://www.cnmv.es/portal/Informacion-Privilegiada/Resultado-IP?nreg={}",
              "OIR": "https://www.cnmv.es/portal/Otra-Informacion-Relevante/Resultado-OIR?nreg={}"}
ENLACE_CNMV = {"IP": "https://www.cnmv.es/Portal/Informacion-Privilegiada/Resultado-IP.aspx?nreg={}",
               "OIR": "https://www.cnmv.es/Portal/Otra-Informacion-Relevante/Resultado-OIR.aspx?nreg={}"}
SIN_REGISTRO = DATOS / "numeros_sin_registro.csv"   # números que la CNMV no enseña: dos consultas en días distintos y no más
DIAS_HUECOS = 45        # se buscan huecos de numeración desde el primer comunicado de los últimos 45 días
MAX_RELLENO = 200       # fichas como máximo por pasada (el primer relleno del 07/11-15/11 son unas 200)
PAUSA_RELLENO = 0.5     # segundos entre dos fichas, por cortesía con la CNMV
DIAS_HISTORICO = 400    # hacia atrás, el histórico se completa hasta el primer comunicado anterior a hoy − 400 días
MAX_ATRAS = 300         # fichas como máximo por pasada en el relleno hacia atrás (unas 7.000 en total para un año)

CAJAS = [  # clave (igual que el id del panel en la plantilla de la web), título, descripción del recuadro
    ("resultados", "Resultados", "Cuentas y fechas de publicación comunicadas a la CNMV."),
    ("dividendos", "Dividendos", "Anuncios de dividendo y dividendos flexibles."),
    ("recompras", "Recompras", "Programas de recompra en curso y su último informe."),
    ("opvs-ampliaciones", "OPVs y ampliaciones", "Ampliaciones de capital, colocaciones y salidas a bolsa."),
    ("opas", "OPAs", "Ofertas públicas de adquisición sobre empresas del IBEX 35 o lanzadas por ellas."),
]
# Tipos que tienen recuadro en /ibex-35/ y página propia en la web. Un tipo nuevo se publica antes en GitHub
# Pages y solo se añade aquí cuando existen su recuadro y su página /ibex-35/<tipo>/ con [espec_cnmv_listado].
# «opas»: recuadro creado por el fragmento 41 a partir de data-caja="opas" y página /ibex-35/opas/ (02/11/2026).
EN_WEB = {"resultados", "dividendos", "recompras", "opvs-ampliaciones", "opas"}
VENTANA = {"resultados": 30, "dividendos": 10, "recompras": 45, "opvs-ampliaciones": 10, "opas": 120}  # días para seguir en la misma operación
DIAS_LISTADO = 365      # antigüedad máxima de lo que sale en las páginas de cada tipo
# Páginas de elespeculador.com con el listado completo de cada tipo (shortcode espec_cnmv_listado) y texto del botón
# que lleva a ellas desde cada recuadro. Con BOTONES = False el botón no se publica (páginas aún en borrador).
BOTONES = True
LISTADOS = {
    "resultados": ("https://elespeculador.com/ibex-35/resultados/", "Ver todos los resultados"),
    "dividendos": ("https://elespeculador.com/ibex-35/dividendos/", "Ver todos los dividendos"),
    "recompras": ("https://elespeculador.com/ibex-35/recompras/", "Ver todas las recompras"),
    "opvs-ampliaciones": ("https://elespeculador.com/ibex-35/ampliaciones-y-opvs/", "Ver todas las ampliaciones y OPVs"),
    "opas": ("https://elespeculador.com/ibex-35/opas/", "Ver todas las OPAs"),
}
INTRO = {
    "resultados": "Publicaciones de resultados y anuncios de la fecha en que se van a presentar, tal como las comunican a la CNMV las empresas del IBEX 35. Cuando una empresa anuncia la fecha y después publica las cuentas del mismo periodo, sale una sola línea con lo último.",
    "dividendos": "Anuncios de dividendo comunicados a la CNMV por las empresas del IBEX 35, incluidos los dividendos flexibles (ampliaciones liberadas).",
    "recompras": "Programas de recompra de acciones de las empresas del IBEX 35. Mientras dura un programa, la empresa informa cada semana de las compras que ha hecho: aquí sale una sola línea por programa, con el último informe y el número de comunicados.",
    "opvs-ampliaciones": "Ampliaciones de capital, colocaciones de acciones y salidas a bolsa comunicadas a la CNMV por las empresas del IBEX 35.",
    "opas": "Ofertas públicas de adquisición comunicadas a la CNMV por las empresas del IBEX 35: las que reciben y las que lanzan, incluidas las de exclusión. Los comunicados de una misma oferta salen en una línea.",
}


class DatosRaros(Exception):
    """La respuesta no tiene la forma esperada: mejor parar que publicar basura."""


def ahora_madrid() -> datetime:
    return datetime.now(MADRID)


# --------------------------------------------------------------------------- lectura de los canales
def _plano(x: str) -> str:
    x = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", x or "", flags=re.S)
    x = re.sub(r"<br\s*/?>", "\n", x, flags=re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    x = html.unescape(x)
    return re.sub(r"[ \t\r\f\v]+", " ", x).strip()


def leer_canal(xml: str, canal: str) -> list[dict]:
    if "<rss" not in xml[:500].lower():
        raise DatosRaros(f"El canal {canal} no devuelve un RSS")
    filas = []
    for item in re.findall(r"<item>(.*?)</item>", xml, flags=re.S | re.I):
        def campo(nombre: str) -> str:
            m = re.search(rf"<{nombre}[^>]*>(.*?)</{nombre}>", item, flags=re.S | re.I)
            return m.group(1) if m else ""
        enlace = _plano(campo("link"))
        nreg = re.search(r"nreg=(\d+)", enlace)
        if not nreg:
            continue
        fecha = parsedate_to_datetime(_plano(campo("pubDate"))).astimezone(MADRID)
        lineas = [l.strip() for l in _plano(campo("description")).split("\n") if l.strip()]
        # primera línea: "17:54 19/10/2026 Programas de recompra de acciones, estabilización y autocartera"
        cabecera = re.sub(r"^\d{1,2}:\d{2}\s+\d{2}/\d{2}/\d{4}\s*", "", lineas[0]) if lineas else ""
        filas.append({"canal": canal, "nreg": int(nreg.group(1)), "fecha": fecha.strftime("%Y-%m-%dT%H:%M:%S"),
                      "emisor": _plano(campo("title")), "categoria": cabecera, "texto": " ".join(lineas[1:]),
                      "enlace": enlace})
    return filas


def _bajar(canal: str, url: str) -> str:
    ultimo = ""
    # Presupuesto acotado: 3 intentos de hasta 40 s más 30 s de espera por canal (unos 2,5 min), para que los dos
    # canales quepan con holgura en el tiempo máximo del flujo aunque la CNMV vaya lenta.
    for intento in range(3):
        if intento:
            time.sleep(10 * intento)
        try:
            r = requests.get(url, headers=CABECERAS, timeout=(10, 30))
        except requests.RequestException as e:
            ultimo = f"{type(e).__name__}: {e}"
            continue
        if r.status_code == 200:
            r.encoding = "utf-8"
            return r.text
        ultimo = f"HTTP {r.status_code}: {r.text[:200]!r}"
    raise DatosRaros(f"La CNMV no responde en el canal {canal} tras 3 intentos ({ultimo})")


def descargar() -> list[dict]:
    """Cada canal por separado: si uno falla se publica con el otro (la hora siguiente lo recupera, porque el
    canal guarda todo lo del día). Solo se para si fallan los dos."""
    filas, fallos = [], []
    for canal, url in CANALES.items():
        try:
            filas += leer_canal(_bajar(canal, url), canal)
        except DatosRaros as e:
            print(f"::warning::{e}")
            fallos.append(canal)
    if len(fallos) == len(CANALES):
        raise DatosRaros("No responde ningún canal de la CNMV")
    return filas


# --------------------------------------------------------------------------- relleno por número de registro
def _campo(bloque: str, patron: str) -> str:
    m = re.search(patron, bloque, flags=re.S)
    return re.sub(r"\s+", " ", _plano(m.group(1))).strip() if m else ""


def leer_ficha(pagina: str, canal: str, nreg: int) -> dict | None:
    """La fila del histórico (mismos campos que el RSS) a partir de la ficha pública de un comunicado, o None si la
    página no muestra ese número de registro. La hora de la ficha no trae segundos."""
    art = re.search(r'<article class="block-content-pdf block-content">(.*?)</article>', pagina, flags=re.S)
    if not art:
        return None
    for li in re.findall(r'<li id="[^"]*_elementoPrimerNivel"[^>]*>(.*?)</ul>\s*</li>', art.group(1), flags=re.S):
        m = re.search(r"N[úu]mero de registro:\s*(\d+)", _plano(li))
        if not m or int(m.group(1)) != nreg:
            continue
        dia = _campo(li, r'class="fecha-con-hora"[^>]*>(.*?)</li>')
        hora = _campo(li, r'class="time"[^>]*>(.*?)</li>')
        emisor = _campo(li, r'class="tit-small"[^>]*>(.*?)</span>')
        try:
            fecha = datetime.strptime(f"{dia} {hora}", "%d/%m/%Y %H:%M")
        except ValueError:
            raise DatosRaros(f"Ficha {canal} {nreg} de la CNMV con fecha inesperada: {dia!r} {hora!r}")
        if not emisor:
            raise DatosRaros(f"Ficha {canal} {nreg} de la CNMV sin emisor")
        return {"canal": canal, "nreg": nreg, "fecha": fecha.strftime("%Y-%m-%dT%H:%M:00"), "emisor": emisor,
                "categoria": _campo(li, r'class="negrita"[^>]*>(.*?)</span>'),
                "texto": _campo(li, r'_subtituloRegistroEnlace"[^>]*>(.*?)</a>'),
                "enlace": ENLACE_CNMV[canal].format(nreg)}
    return None


def pagina_sin_registro(pagina: str) -> bool:
    """Página normal de la CNMV que dice que ese número no existe (y no una página de error o de mantenimiento)."""
    return 'id="ctl00_H1"' in pagina and "block-content-pdf" not in pagina and "No se han encontrado datos disponibles" in pagina


def leer_sin_registro() -> dict[tuple[str, int], dict]:
    if not SIN_REGISTRO.exists():
        return {}
    d = pd.read_csv(SIN_REGISTRO, dtype=str, keep_default_na=False)
    return {(r.canal, int(r.nreg)): {"consultado": r.consultado, "intentos": int(r.intentos)} for r in d.itertuples()}


def guardar_sin_registro(sin: dict[tuple[str, int], dict]) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    filas = [{"canal": c, "nreg": n, **v} for (c, n), v in sorted(sin.items())]
    tmp = SIN_REGISTRO.with_suffix(".tmp")
    pd.DataFrame(filas, columns=["canal", "nreg", "consultado", "intentos"]).to_csv(tmp, index=False)
    os.replace(tmp, SIN_REGISTRO)


def huecos(h: pd.DataFrame, nuevas: list[dict], hoy: datetime, saltar: set) -> dict[str, list[int]]:
    """Números de registro que faltan en cada canal, de los más recientes a los más antiguos: entre el primero de los
    comunicados de los últimos DIAS_HUECOS días y el último conocido (histórico más lo que acaba de traer el RSS)."""
    desde = (hoy - timedelta(days=DIAS_HUECOS)).strftime("%Y-%m-%d")
    out = {}
    for canal in CANALES:
        conocidos = {int(n) for n in h.loc[h["canal"] == canal, "nreg"]} | {int(f["nreg"]) for f in nuevas if f["canal"] == canal}
        recientes = [int(n) for n, f in zip(h.loc[h["canal"] == canal, "nreg"], h.loc[h["canal"] == canal, "fecha"]) if str(f)[:10] >= desde]
        recientes += [int(f["nreg"]) for f in nuevas if f["canal"] == canal and str(f["fecha"])[:10] >= desde]
        if not recientes:
            out[canal] = []
            continue
        out[canal] = [n for n in range(max(conocidos), min(recientes) - 1, -1) if n not in conocidos and (canal, n) not in saltar]
    return out


def _bajar_ficha(sesion: requests.Session, canal: str, nreg: int) -> str:
    r = sesion.get(FICHA_CNMV[canal].format(nreg), headers={**CABECERAS, "Accept": "text/html,application/xhtml+xml"}, timeout=(10, 30))
    if r.status_code != 200:
        raise requests.RequestException(f"HTTP {r.status_code}")
    r.encoding = "utf-8"
    return r.text


def rellenar(h: pd.DataFrame, nuevas: list[dict], hoy: datetime, bajar=None, limite: int = MAX_RELLENO,
             pausa: float = PAUSA_RELLENO) -> tuple[list[dict], dict[str, int], str | None]:
    """Pide a la CNMV la ficha de cada número que falta (los más recientes primero, hasta `limite`). Devuelve las filas
    recuperadas, los huecos que quedan por canal y, si la CNMV ha cambiado la forma de sus fichas, el motivo (el colector
    publica igual y después sale con error para que se abra la incidencia). Un fallo de red no para nada: el número se
    vuelve a pedir en la pasada siguiente."""
    sin = leer_sin_registro()
    hoy_txt = hoy.strftime("%Y-%m-%d")
    saltar = {k for k, v in sin.items() if v["intentos"] >= 2 or v["consultado"] == hoy_txt}
    pend = huecos(h, nuevas, hoy, saltar)
    cola = [(c, n) for c in CANALES for n in pend[c]][:limite]
    if bajar is None:
        sesion = requests.Session()
        bajar = lambda c, n: _bajar_ficha(sesion, c, n)  # noqa: E731
    filas, raras, seguidos, problema, pedidos = [], [], 0, None, 0
    for i, (canal, n) in enumerate(cola):
        if i and pausa:
            time.sleep(pausa)
        pedidos += 1
        try:
            pagina = bajar(canal, n)
        except Exception as e:  # red, tiempo agotado, HTTP 5xx: se reintenta en la pasada siguiente
            seguidos += 1
            print(f"::warning::Ficha {canal} {n} de la CNMV no disponible ({type(e).__name__}: {e})")
            if seguidos >= 5:
                print("::warning::Cinco fichas seguidas sin respuesta de la CNMV: el relleno sigue en la pasada siguiente")
                break
            continue
        seguidos = 0
        try:
            fila = leer_ficha(pagina, canal, n)
        except DatosRaros as e:
            raras.append(str(e))
            continue
        if fila:
            filas.append(fila)
        elif pagina_sin_registro(pagina):
            previo = sin.get((canal, n), {"intentos": 0})
            sin[(canal, n)] = {"consultado": hoy_txt, "intentos": previo["intentos"] + 1}
        else:
            raras.append(f"Ficha {canal} {n}: página de la CNMV con una forma que el colector no reconoce")
    if cola:
        guardar_sin_registro(sin)
    leidas = len(filas) + len(raras)
    if raras and len(raras) >= max(3, leidas // 2):
        problema = f"{len(raras)} de {leidas} fichas de la CNMV no se pueden leer (¿ha cambiado la página?): {raras[0]}"
    for r in raras[:5]:
        print(f"::warning::{r}")
    quedan = {c: len(pend[c]) for c in CANALES}
    for f in filas:
        quedan[f["canal"]] -= 1
    if cola:
        print(f"Relleno por número de registro: {len(filas)} comunicados recuperados de {pedidos} números pedidos; "
              f"quedan {quedan['IP']} en IP y {quedan['OIR']} en OIR.")
    return filas, quedan, problema


def rellenar_atras(h: pd.DataFrame, nuevas: list[dict], hoy: datetime, bajar=None, limite: int = MAX_ATRAS,
                   pausa: float = PAUSA_RELLENO, dias: int = DIAS_HISTORICO) -> tuple[list[dict], dict[str, str], str | None]:
    """Completa el histórico hacia atrás, número a número, desde el primer número conocido de cada canal hasta el
    primer comunicado anterior a hoy − `dias` (el registro oficial de las fichas cubre doce meses). Primero IP, que
    tiene pocos, luego OIR; hasta `limite` fichas por pasada. Si una ficha falla (red, CNMV), para ese canal: la
    pasada siguiente sigue por el mismo número, así que nunca deja huecos. Devuelve las filas, el estado de cada
    canal (completo, en curso, parado) y, si la CNMV ha cambiado la forma de sus fichas, el motivo."""
    objetivo = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
    sin = leer_sin_registro()
    hoy_txt = hoy.strftime("%Y-%m-%d")
    if bajar is None:
        sesion = requests.Session()
        bajar = lambda c, n: _bajar_ficha(sesion, c, n)  # noqa: E731
    filas, estado, problema, pedidos, cambia_sin = [], {}, None, 0, False
    for canal in CANALES:
        fechas = [str(f)[:10] for f in h.loc[h["canal"] == canal, "fecha"]] + [str(f["fecha"])[:10] for f in nuevas if f["canal"] == canal]
        if not fechas:
            estado[canal] = "sin datos"
            continue
        if min(fechas) < objetivo:
            estado[canal] = "completo"
            continue
        conocidos = ({int(n) for n in h.loc[h["canal"] == canal, "nreg"]} | {int(f["nreg"]) for f in nuevas if f["canal"] == canal}
                     | {n for (c, n) in sin if c == canal})
        n = min(conocidos) - 1
        estado[canal] = "en curso"
        while n > 0:
            if pedidos >= limite:
                break
            if pedidos and pausa:
                time.sleep(pausa)
            pedidos += 1
            try:
                pagina = bajar(canal, n)
            except Exception as e:  # se para el canal y la pasada siguiente sigue por este mismo número
                print(f"::warning::Relleno hacia atrás parado en la ficha {canal} {n} ({type(e).__name__}: {e})")
                estado[canal] = "parado"
                break
            try:
                fila = leer_ficha(pagina, canal, n)
            except DatosRaros as e:
                problema = str(e)
                estado[canal] = "parado"
                break
            if fila:
                filas.append(fila)
                if fila["fecha"][:10] < objetivo:
                    estado[canal] = "completo"
                    break
            elif pagina_sin_registro(pagina):
                sin[(canal, n)] = {"consultado": hoy_txt, "intentos": 2}  # hacia atrás no se vuelve a preguntar
                cambia_sin = True
            else:
                problema = f"Ficha {canal} {n}: página de la CNMV con una forma que el colector no reconoce (relleno hacia atrás)"
                estado[canal] = "parado"
                break
            n -= 1
    if cambia_sin:
        guardar_sin_registro(sin)
    if pedidos:
        print(f"Relleno hacia atrás (hasta el {objetivo}): {len(filas)} comunicados de {pedidos} números pedidos; "
              f"IP {estado.get('IP')}, OIR {estado.get('OIR')}.")
    return filas, estado, problema


def resumen_historico(h: pd.DataFrame, hoy: datetime, dias: int = DIAS_HISTORICO) -> dict:
    """Desde qué fecha tiene el histórico cada canal y si ya cubre los `dias` hacia atrás."""
    objetivo = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
    out = {}
    for canal in CANALES:
        f = [str(x)[:10] for x in h.loc[h["canal"] == canal, "fecha"]]
        out[canal] = {"desde": min(f) if f else None, "completo": bool(f) and min(f) < objetivo}
    return out


def leer_historico() -> pd.DataFrame:
    return pd.read_csv(HISTORICO, dtype=str, keep_default_na=False) if HISTORICO.exists() else pd.DataFrame(columns=COLUMNAS)


def acumular(nuevas: list[dict]) -> tuple[pd.DataFrame, int]:
    previo = leer_historico()
    n = pd.DataFrame(nuevas, columns=COLUMNAS).astype(str)
    d = pd.concat([previo, n], ignore_index=True).drop_duplicates(["canal", "nreg"], keep="first")
    d = d.sort_values(["fecha", "canal", "nreg"], ascending=False).reset_index(drop=True)
    return d[COLUMNAS], len(d) - len(previo)


# --------------------------------------------------------------------------- empresas del IBEX 35
def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", x)).strip()


def empresas_ibex(hoy: pd.Timestamp) -> pd.DataFrame:
    if hoy > pd.Timestamp(IBEX35_VALIDA_HASTA):
        raise DatosRaros(f"La composición del IBEX 35 venció el {IBEX35_VALIDA_HASTA}: actualiza dividendos/ibex35.csv y la fecha")
    miembros = set(pd.read_csv(IBEX35, dtype=str)["isin"])
    e = pd.read_csv(EMPRESAS, dtype=str)
    sin_alias = miembros - set(e["isin"])
    if sin_alias:
        print(f"::warning::Empresas del IBEX 35 sin alias en cnmv/empresas.csv: {sorted(sin_alias)}")
    return e[e["isin"].isin(miembros)].reset_index(drop=True)


def identificar(emisor: str, e: pd.DataFrame) -> pd.Series | None:
    n = _norm(emisor)
    for _, x in e.iterrows():
        if re.search(x["patron"], n):
            return x
    return None


# --------------------------------------------------------------------------- clasificación
def _t(x: str) -> str:
    return " " + _norm(x).lower() + " "


def _hay(texto: str, *frases: str) -> bool:
    return any(f in texto for f in frases)


# «resultados de los nueve primeros meses», «primeros seis meses»: el colector de WordPress (fragmento 64) ya los
# reconocía y este no (Aena, Cellnex y Ferrovial del 27/10 al 05/11 quedaban sin clasificar; comparación del 21/11/2026).
MESES_ACUMULADOS = r"(nueve|seis|tres) primeros meses|primeros (nueve|seis|tres) meses"


def clasificar(categoria: str, texto: str) -> tuple[str, str] | None:
    """(caja, etiqueta) o None si no es de ninguno de los cuatro recuadros."""
    c, t = _t(categoria), _t(texto)
    todo = c + t
    if _hay(c, " contratos de liquidez "):
        return None
    deuda = _hay(todo, " bonos ", " obligaciones ", " pagares ", " notas ", " warrants ", " turbos ",
                 " certificados ", " renta fija ", " cedulas ")
    if not deuda and _hay(todo, " oferta publica de adquisicion ", " ofertas publicas de adquisicion ", " opa ", " opas ",
                          " tender offer ", " takeover bid ", " oferta publica voluntaria ", " oferta publica obligatoria "):
        return "opas", ("OPA de exclusión" if _hay(todo, " exclusion ") else "OPA")
    if _hay(todo, " ampliacion de capital liberada ", " aumento de capital liberado ", " dividendo flexible ",
            " retribucion flexible ", " scrip ", " derechos de asignacion gratuita "):
        return "dividendos", "Dividendo flexible"
    # «planes estratégicos … y política de retribución al accionista» (Santander, 25/02/2026): es la política, no un pago
    if _hay(t, " politica de retribucion ", " politica de dividendos ", " politica de remuneracion ") and \
            not _hay(t, " a cuenta ", " complementario ", " pago ", " abono ", " importe ", " euros "):
        return "dividendos", "Política de dividendos"
    if _hay(todo, " dividendo ", " dividendos ", " retribucion al accionista ", " pago a cuenta ",
            " devolucion de prima ", " distribucion de prima "):
        return "dividendos", "Dividendo"
    if _hay(todo, " estabilizacion ") and _hay(todo, " oferta ", " colocacion ", " opv "):
        return "opvs-ampliaciones", "Colocación"
    if _hay(todo, " recompra ", " autocartera ") or (_hay(t, " acciones propias ") and _hay(t, " adquisicion ", " compra ", " bloque ")):
        # Una oferta de recompra de bonos, obligaciones o preferentes no es un programa de recompra de acciones
        # (Unicaja, Mapfre, Santander e IAG en 2026, vistos al rellenar doce meses el 22/11/2026): queda fuera.
        if (deuda or _hay(todo, " preferentes ", " convertibles ", " emision en circulacion ", " emisiones en circulacion ")) \
                and not _hay(t, " acciones ", " autocartera "):
            return None
        return "recompras", "Programa de recompra"
    valores_deuda = _hay(todo, " bonos ", " obligaciones ", " pagares ", " notas ", " warrants ", " turbos ",
                         " certificados ", " renta fija ", " cedulas ")
    if not valores_deuda:
        if _hay(todo, " oferta publica de venta ", " opv ", " salida a bolsa ", " oferta publica de suscripcion "):
            return "opvs-ampliaciones", "OPV"
        if _hay(todo, " ampliacion de capital ", " aumento de capital ", " nuevas acciones ", " emision de acciones "):
            return "opvs-ampliaciones", "Ampliación de capital"
        if _hay(todo, " colocacion acelerada ", " accelerated bookbuild ", " colocacion privada ", " colocacion de acciones "):
            return "opvs-ampliaciones", "Colocación"
    if _hay(todo, " junta ") and not _hay(todo, " resultados del ", " resultados de la sociedad "):
        return None
    if _hay(t, " resultados ", " resultado ") and _hay(t, " fecha ", " calendario ", " presentara ", " publicara ") \
            and _hay(t, " publicacion ", " presentacion ", " calendario ", " presentara ", " publicara "):
        return "resultados", "Fecha de resultados"
    # «Aena anuncia la celebración de la presentación de resultados…», «Anuncio webcast seguimiento de la actividad 9M»
    trimestral = rf"\b(trimestre|trimestral|semestre|semestral|nueve meses|{MESES_ACUMULADOS}|9m|[1-4]t(\d\d)?|q[1-4]|[12]s(\d\d)?|h[12])\b"
    if re.search(r"\b(anuncia|anuncio|convoca|convocatoria|celebracion|webcast)\b", t) and \
            (_hay(t, " resultados ") or re.search(trimestral, t)):
        return "resultados", "Fecha de resultados"
    if _hay(todo, " resultados ", " cuentas ", " informe financiero ", " informacion financiera ", " beneficio ") and re.search(
            rf"\b(trimestre|trimestral|semestre|semestral|ejercicio|anual|anuales|nueve meses|{MESES_ACUMULADOS}|9m|[1-4]t(\d\d)?|q[1-4]|[12]s(\d\d)?|h[12]|situacion financiera)\b", t):
        return "resultados", "Resultados"
    return None


PERIODOS = [(r"\b(primer|1er) trimestre\b|\b1t(\d\d)?\b|\bq1\b|\btres primeros meses\b|\bprimeros tres meses\b", "1T"), (r"\bsegundo trimestre\b|\b2t(\d\d)?\b|\bq2\b", "2T"),
            (r"\b(tercer|3er) trimestre\b|\b3t(\d\d)?\b|\bq3\b|\bnueve meses\b|\bnueve primeros meses\b|\bprimeros nueve meses\b|\b9m\b", "3T"), (r"\bcuarto trimestre\b|\b4t(\d\d)?\b|\bq4\b", "4T"),
            (r"\b(primer )?semestre\b|\b1s(\d\d)?\b|\bh1\b|\bseis primeros meses\b|\bprimeros seis meses\b", "1S"), (r"\b(ejercicio|anuales?|anual)\b", "año")]


def periodo(texto: str, fecha: str) -> str:
    t = _norm(texto).lower()
    anio = re.search(r"\b(20\d\d)\b", t)
    for patron, p in PERIODOS:
        m = re.search(patron, t)
        if m:
            corto = re.search(r"[1-4][ts](\d\d)\b", m.group(0))
            return f"{p} {anio.group(1) if anio else ('20' + corto.group(1) if corto else fecha[:4])}"
    return ""


def agrupar(d: pd.DataFrame) -> pd.DataFrame:
    """Asigna a cada comunicado del IBEX 35 su operación (grupo)."""
    d = d.sort_values(["fecha", "canal", "nreg"]).reset_index(drop=True)
    abiertos: dict[tuple, dict] = {}
    grupo = []
    for x in d.itertuples():
        f = pd.Timestamp(x.fecha)
        clave = (x.isin, x.caja, x.periodo if x.caja == "resultados" else "")
        g = abiertos.get(clave)
        if g is None or (f - g["ultima"]).days > VENTANA[x.caja]:
            g = {"id": f"{x.caja}-{x.isin}-{x.nreg}", "ultima": f}
            abiertos[clave] = g
        g["ultima"] = f
        grupo.append(g["id"])
    d["grupo"] = grupo
    return d.sort_values(["fecha", "canal", "nreg"], ascending=False).reset_index(drop=True)


def clasificados(h: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for x in h.itertuples():
        emp = identificar(x.emisor, e)
        if emp is None:
            continue
        c = clasificar(x.categoria, x.texto)
        if c is None:
            continue
        filas.append({**x._asdict(), "isin": emp["isin"], "empresa": emp["nombre"], "ficha": emp["ficha"], "caja": c[0],
                      "etiqueta": c[1], "periodo": periodo(x.texto, x.fecha) if c[0] == "resultados" else ""})
    cols = COLUMNAS + ["isin", "empresa", "ficha", "caja", "etiqueta", "periodo", "grupo"]
    if not filas:
        return pd.DataFrame(columns=cols)
    d = pd.DataFrame(filas).drop(columns=["Index"])
    return agrupar(d)[cols]


# --------------------------------------------------------------------------- salida
def _e(x) -> str:
    return html.escape(str(x)).replace("$", "&#36;")


def _f(fecha: str) -> str:
    return pd.Timestamp(fecha).strftime("%d/%m/%Y")


def _corto(t: str, n: int = 190) -> str:
    t = t.strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def entradas(c: pd.DataFrame, caja: str, hoy: pd.Timestamp, dias: int = DIAS_CAJA) -> list[dict]:
    x = c[(c["caja"] == caja) & (pd.to_datetime(c["fecha"]) >= hoy - pd.Timedelta(days=dias))]
    out = []
    for gid, g in x.groupby("grupo", sort=False):
        g = g.sort_values("fecha", ascending=False)
        ult = g.iloc[0]
        etiqueta = ult.etiqueta
        if caja == "resultados":
            publicado = g[g["etiqueta"] == "Resultados"]
            if not publicado.empty:
                ult, etiqueta = publicado.iloc[0], "Resultados"
            if ult.periodo:
                etiqueta += f" {ult.periodo}"
        out.append({"grupo": gid, "empresa": ult.empresa, "ficha": ult.ficha, "fecha": g.iloc[0].fecha,
                    "etiqueta": etiqueta, "texto": ult.texto or ult.categoria, "enlace": ult.enlace, "n": len(g),
                    "todos": [(y.nreg, y.enlace) for y in g.itertuples()]})
    out.sort(key=lambda r: r["fecha"], reverse=True)
    return out


def articulo(r: dict) -> str:
    meta = f"{_f(r['fecha'])} · {r['etiqueta']}" + (f" · {r['n']} comunicados" if r["n"] > 1 else "")
    return (f'<article class="efsec-item">'
            f'<h4 class="efsec-item-title"><a href="{FICHAS}{r["ficha"]}/">{_e(r["empresa"])}</a></h4>'
            f'<div class="efsec-item-meta">{_e(meta)}</div>'
            f'<p class="efsec-item-excerpt">{_e(_corto(r["texto"]))}</p>'
            f'<a class="efsec-item-link" href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">Ver el comunicado en la CNMV</a>'
            f'</article>')


def vacio(titulo: str, inicio: pd.Timestamp, hoy: pd.Timestamp) -> str:
    t = titulo if titulo.startswith("OP") else titulo.lower()
    if hoy - inicio >= pd.Timedelta(days=DIAS_CAJA):
        return f"Ninguna empresa del IBEX 35 ha comunicado a la CNMV {t} en los últimos {DIAS_CAJA} días."
    return f"Sin comunicados de {t} de empresas del IBEX 35 desde el {inicio.strftime('%d/%m/%Y')}, cuando empieza este registro."


def todos_html(r: dict) -> str:
    """Todos los comunicados de una operación, cada uno con su enlace a la CNMV: ningún hecho queda sin enlace."""
    if r["n"] <= 1:
        return ""
    enl = " · ".join(f'<a href="{_e(u)}" target="_blank" rel="noopener nofollow">nº {_e(n)}</a>' for n, u in r["todos"])
    return f"{r['n']} comunicados: {enl}"


def cajas_html(c: pd.DataFrame, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> str:
    bloques = []
    for clave, titulo, desc in CAJAS:
        if clave not in EN_WEB:
            continue
        es = entradas(c, clave, hoy)[:POR_CAJA]
        cuerpo = "\n".join(articulo(r) for r in es) or f'<p class="efsec-item-excerpt">{_e(vacio(titulo, inicio, hoy))}</p>'
        if BOTONES:
            url, texto = LISTADOS[clave]
            cuerpo += f'\n<p class="espec-ver-todo"><a class="efsec-item-link" href="{url}">{_e(texto)}</a></p>'
        bloques.append(f'<div data-caja="{clave}" data-desc="{_e(desc)}">\n{cuerpo}\n</div>')
    return f"<!-- cnmv:inicio {sello} -->\n" + "\n".join(bloques) + "\n<!-- cnmv:fin -->\n"


def navegacion(actual: str) -> str:
    enlaces = []
    for clave, titulo, _ in CAJAS:
        if clave not in EN_WEB and clave != actual:
            continue
        if clave == actual:
            enlaces.append(f"<strong>{_e(titulo)}</strong>")
        else:
            enlaces.append(f'<a href="{LISTADOS[clave][0]}">{_e(titulo)}</a>')
    return ('<p class="espec-cnmv-nav">' + " · ".join(enlaces) +
            ' · <a href="https://elespeculador.com/ibex-35/">Volver al IBEX 35</a></p>')


def listado_html(c: pd.DataFrame, clave: str, titulo: str, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> str:
    """Listado completo de un tipo para su página de elespeculador.com: tabla sin imágenes; cada fila lleva la
    empresa en data-empresa para que la página pueda filtrar por empresa."""
    es = entradas(c, clave, hoy, DIAS_LISTADO)
    filas = "\n".join(
        f'<tr data-empresa="{_e(r["empresa"])}"><td>{_f(r["fecha"])}</td>'
        f'<td><a href="{FICHAS}{r["ficha"]}/">{_e(r["empresa"])}</a></td><td>{_e(r["etiqueta"])}</td>'
        f'<td>{_e(_corto(r["texto"], 300))}</td>'
        f'<td><a href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">CNMV</a>'
        f'{" (" + todos_html(r) + ")" if r["n"] > 1 else ""}</td></tr>' for r in es)
    if not filas:
        filas = f'<tr><td colspan="5">{_e(vacio(titulo, inicio, hoy))}</td></tr>'
    desde = max(inicio, hoy - pd.Timedelta(days=DIAS_LISTADO))
    return (f"<!-- cnmv-listado:inicio {clave} {sello} -->\n"
            f"{navegacion(clave)}\n"
            "\n"
            f'<p class="espec-cnmv-intro">{_e(INTRO[clave])}</p>\n'
            f'<figure class="wp-block-table espec-cnmv-tabla"><table><thead><tr><th>Fecha</th><th>Empresa</th><th>Tipo</th>'
            f'<th>Comunicado</th><th>Fuente</th></tr></thead><tbody>\n{filas}\n</tbody></table></figure>\n'
            f'<p class="espec-cnmv-pie">Fuente: CNMV. Comunicados desde el {desde.strftime("%d/%m/%Y")}; se actualiza cada hora '
            f'en días hábiles (última actualización: {_e(sello[8:10] + "/" + sello[5:7] + "/" + sello[:4] + " a las " + sello[11:])}). '
            f'La clasificación es automática: el texto oficial de cada comunicado es el que publica la CNMV.</p>\n'
            f"<!-- cnmv-listado:fin -->\n")


# --------------------------------------------------------------------------- bloque de la ficha de cada empresa
NOMBRE_CAJA = {"resultados": "Resultados", "dividendos": "Dividendos", "recompras": "Recompra",
               "opvs-ampliaciones": "Ampliación u OPV", "opas": "OPA"}
FICHA_COMUNICADOS = 8   # líneas de comunicados en cada ficha


def _comunicados_empresa(c: pd.DataFrame, isin: str, hoy: pd.Timestamp) -> list[dict]:
    x = c[c["isin"] == isin]
    out = []
    for clave, _, _ in CAJAS:
        for r in entradas(x, clave, hoy, DIAS_LISTADO):
            out.append({**r, "caja": clave})
    out.sort(key=lambda r: r["fecha"], reverse=True)
    return out


def ficha_html(c: pd.DataFrame, emp: pd.Series, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> str:
    """Bloque para la ficha de una empresa en elespeculador.com/ibex35/<ficha>/: sus comunicados a la CNMV (también
    los anuncios de dividendo), en una lista sin imágenes con las mismas clases que el resto de la ficha (ef-card,
    ef-news, ef-note). Sin datos de BME: ni importes, ni rentabilidades, ni precios (21/11/2026)."""
    nombre = emp["nombre"]
    lineas = []
    for r in _comunicados_empresa(c, emp["isin"], hoy)[:FICHA_COMUNICADOS]:
        tipo = r["etiqueta"] if r["caja"] in ("resultados", "dividendos", "opas") else NOMBRE_CAJA[r["caja"]]
        extra = f" ({todos_html(r)})" if r["n"] > 1 else ""
        lineas.append(f'<li><time>{_f(r["fecha"])}</time><span><a href="{_e(r["enlace"])}" target="_blank" rel="noopener nofollow">'
                      f'{_e(_corto(r["texto"], 150))}</a><br><small>{_e(tipo)}{extra}</small></span></li>')
    if lineas:
        lista = '<ul class="ef-news">\n' + "\n".join(lineas) + "\n</ul>"
    else:
        cuando = ("en los últimos doce meses" if hoy - inicio >= pd.Timedelta(days=DIAS_LISTADO)
                  else f'desde el {inicio.strftime("%d/%m/%Y")}, cuando empieza este registro')
        lista = f'<p>{_e(nombre)} no ha comunicado a la CNMV resultados, dividendos, recompras, ampliaciones ni OPAs {cuando}.</p>'
    enlaces = " · ".join(f'<a href="{LISTADOS[k][0]}">{_e(t)}</a>' for k, t, _ in CAJAS if k in EN_WEB)
    bloques = [f'<div class="ef-card">\n<h2>Comunicados de {_e(nombre)} a la CNMV</h2>\n{lista}\n'
               f'<p class="ef-note">Resultados, dividendos, recompras, ampliaciones y OPAs de los últimos doce meses. '
               f'Los comunicados de una misma operación salen en una línea, con un enlace a cada uno. Todas las empresas del IBEX 35: {enlaces}.</p>\n</div>']

    return (f"<!-- ficha-cnmv:inicio {emp['ficha']} {sello} -->\n" + "\n".join(bloques) + "\n<!-- ficha-cnmv:fin -->\n")


def fichas(c: pd.DataFrame, e: pd.DataFrame, hoy: pd.Timestamp, sello: str, inicio: pd.Timestamp) -> int:
    carpeta = SALIDA / "empresas"
    carpeta.mkdir(parents=True, exist_ok=True)
    for emp in e.to_dict("records"):
        frag = ficha_html(c, pd.Series(emp), hoy, sello, inicio)
        assert "$" not in frag
        (carpeta / f"{emp['ficha']}.html").write_text(frag, encoding="utf-8")
    return len(e)


def pagina(c: pd.DataFrame, hoy: pd.Timestamp, sello: str) -> str:
    secciones = []
    for clave, titulo, desc in CAJAS:
        es = entradas(c, clave, hoy)
        filas = "\n".join(
            f"<tr><td>{_f(r['fecha'])}</td><td><a href=\"{FICHAS}{r['ficha']}/\">{_e(r['empresa'])}</a></td><td>{_e(r['etiqueta'])}</td>"
            f"<td>{_e(_corto(r['texto'], 260))}</td><td><a href=\"{_e(r['enlace'])}\" rel=\"nofollow\">CNMV</a>"
            f"{' (' + str(r['n']) + ')' if r['n'] > 1 else ''}</td></tr>" for r in es) or \
            '<tr><td colspan="5">Sin comunicados en el periodo.</td></tr>'
        secciones.append(f"<h2>{titulo}</h2><p>{_e(desc)}</p><figure><table><thead><tr><th>Fecha</th><th>Empresa</th><th>Tipo</th>"
                         f"<th>Comunicado</th><th>Fuente</th></tr></thead><tbody>\n{filas}\n</tbody></table></figure>")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comunicados a la CNMV de las empresas del IBEX 35 | El Especulador</title>
<meta name="description" content="Resultados, dividendos, recompras y ampliaciones comunicados a la CNMV por las empresas del IBEX 35 en los últimos {DIAS_CAJA} días.">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2733;max-width:1100px;margin:0 auto;padding:16px;line-height:1.45}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:1.6em}} figure{{margin:0;overflow-x:auto}}
table{{border-collapse:collapse;font-size:.88rem;margin:.6em 0}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #d7dde5;vertical-align:top}} th{{background:#f6f8fb}}
a{{color:#1f4e8c}} .pie{{color:#5b6675;font-size:.85rem;margin-top:2em}}
</style>
</head><body>
<h1>Comunicados a la CNMV de las empresas del IBEX 35</h1>
<p><strong>Actualizado el {_e(sello.replace('T', ' a las '))}.</strong> Los comunicados de una misma operación (por ejemplo, los informes semanales de un programa de recompra) se agrupan en una sola fila, con el último comunicado y, entre paréntesis, cuántos hay.</p>
{"".join(secciones)}
<h2>Datos abiertos</h2>
<p>CSV: <a href="datos/ibex35.csv">comunicados del IBEX 35 clasificados</a> · <a href="datos/comunicados.csv">todos los comunicados leídos</a> · <a href="datos/ultima.json">JSON</a>. Fuente: CNMV, comunicados de información privilegiada y otra información relevante, reproducidos fielmente (gratuitos en cnmv.es). La clasificación y el resumen de El Especulador se publican con licencia <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>, citando «El Especulador, a partir de datos de la CNMV».</p>
<p class="pie">Fuente: CNMV, canales de información privilegiada y de otra información relevante. La clasificación es automática; el texto oficial de cada comunicado es el de la CNMV. Contenido informativo; no constituye asesoramiento financiero.</p>
</body></html>
"""


def escribir(h: pd.DataFrame, c: pd.DataFrame, e: pd.DataFrame, nuevos: int, forzar: bool, extra: dict | None = None) -> bool:
    """Reescribe si hay comunicados nuevos o si ha cambiado el día (los recuadros dependen de la fecha)."""
    ahora = ahora_madrid()
    hoy = pd.Timestamp(ahora.date())
    sello = ahora.strftime("%Y-%m-%dT%H:%M")
    previo = json.loads((DATOS / "ultima.json").read_text(encoding="utf-8")) if (DATOS / "ultima.json").exists() else {}
    if (nuevos == 0 and not forzar and (SALIDA / "cajas.html").exists()
            and str(previo.get("actualizado", ""))[:10] == sello[:10]):
        return False
    DATOS.mkdir(parents=True, exist_ok=True)
    h.to_csv(HISTORICO, index=False)
    c.to_csv(DATOS / "ibex35.csv", index=False)
    inicio = pd.Timestamp(pd.Timestamp(h["fecha"].min()).date())
    cajas = cajas_html(c, hoy, sello, inicio)
    for clave, titulo, _ in CAJAS:
        lst = listado_html(c, clave, titulo, hoy, sello, inicio)
        assert "$" not in lst
        (SALIDA / f"listado-{clave}.html").write_text(lst, encoding="utf-8")
    assert "$" not in cajas
    (SALIDA / "cajas.html").write_text(cajas, encoding="utf-8")
    fichas(c, e, hoy, sello, inicio)
    (SALIDA / "index.html").write_text(pagina(c, hoy, sello), encoding="utf-8")
    (DATOS / "ultima.json").write_text(json.dumps({
        "actualizado": sello, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comunicados_leidos": int(len(h)), "comunicados_ibex35_clasificados": int(len(c)),
        "por_recuadro": {k: len(entradas(c, k, hoy)) for k, _, _ in CAJAS},
        "fuente": "CNMV, RSS de información privilegiada y otra información relevante, y ficha pública de cada comunicado por número de registro", "licencia": "Comunicados de la CNMV reproducidos fielmente (gratuitos en cnmv.es); clasificación y resumen de El Especulador con licencia CC BY 4.0",
        **(extra or {}),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", nargs="+", help="ficheros RSS ya descargados (el nombre debe contener IP u OIR)")
    ap.add_argument("--forzar", action="store_true", help="reescribir aunque no haya comunicados nuevos")
    ap.add_argument("--sin-relleno", action="store_true", help="no pedir a la CNMV los números de registro que faltan")
    ap.add_argument("--relleno-max", type=int, default=MAX_RELLENO, help="fichas como máximo por pasada")
    ap.add_argument("--atras-max", type=int, default=MAX_ATRAS, help="fichas como máximo por pasada hacia atrás (0 = no)")
    ap.add_argument("--dividendos-max", type=int, default=20, help="comunicados de dividendo que se leen por pasada (0 = no)")
    args = ap.parse_args()
    if args.local:
        filas = []
        for f in args.local:
            canal = "IP" if "IP" in Path(f).name.upper().replace("OIR", "") else "OIR"
            filas += leer_canal(Path(f).read_text(encoding="utf-8"), canal)
    else:
        filas = descargar()
    extra, problema = None, None
    if not args.local and not args.sin_relleno:
        previo = leer_historico()
        recuperadas, quedan, problema = rellenar(previo, filas, ahora_madrid(), limite=args.relleno_max)
        filas += recuperadas
        atras, _, problema_atras = rellenar_atras(previo, filas, ahora_madrid(), limite=args.atras_max) if args.atras_max else ([], {}, None)
        filas += atras
        problema = problema or problema_atras
        extra = {"huecos_pendientes": quedan}
    h, nuevos = acumular(filas)
    if extra is not None:
        extra["historico"] = resumen_historico(h, ahora_madrid())
    e = empresas_ibex(pd.Timestamp(ahora_madrid().date()))
    c = clasificados(h, e)
    if escribir(h, c, e, nuevos, args.forzar, extra):
        print(f"{nuevos} comunicados nuevos; {len(c)} del IBEX 35 clasificados en el histórico.")
    else:
        print(f"Sin comunicados nuevos en la CNMV ({len(h)} en el histórico): no se toca nada.")
    if not args.local and not args.sin_relleno and args.dividendos_max:
        try:  # importe y fechas de cada dividendo, leídos del propio comunicado (dividendos_cnmv.py)
            import dividendos_cnmv
            dividendos_cnmv.actualizar(DATOS, limite=args.dividendos_max)
        except Exception as e:  # no frena lo ya publicado, pero abre la incidencia
            problema = problema or f"dividendos de la CNMV: {type(e).__name__}: {e}"
    if problema:  # lo leído se publica igual; el error abre la incidencia cnmv-fallido
        raise DatosRaros(problema)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DatosRaros as e:
        print(f"::error::{e}")
        sys.exit(1)
    except Exception as e:  # que el motivo quede en el resumen de la ejecución
        print(f"::error::{type(e).__name__}: {e}")
        raise
