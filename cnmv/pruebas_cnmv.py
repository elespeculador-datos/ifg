"""Comprobaciones sin red del colector de comunicados de la CNMV.

  python cnmv/pruebas_cnmv.py

Cubre lo que cambió el 21/11/2026 para que el colector del servidor pueda sustituir al de WordPress
(fragmento 64) en las fichas del IBEX 35:

1. Relleno por número de registro: lectura de la ficha pública de cada comunicado (páginas reales de la
   CNMV del 21/11/2026 en pruebas_cnmv/), huecos de numeración, números que no existen y fallos de red.
2. Regla de resultados: «nueve primeros meses» y parecidos.
3. Ni rastro de BME en las salidas.
4. Paridad con la web: el histórico real del servidor (20/11, 20:07) más los 13 comunicados del hueco del
   07/11 al 13/11 da, en las 35 fichas, los mismos comunicados y las mismas etiquetas que la web pintaba el
   21/11 (pruebas_cnmv/web-fichas-2026-11-21.json).
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

AQUI = Path(__file__).resolve().parent
PRUEBAS = AQUI / "pruebas_cnmv"
TMP = Path(tempfile.mkdtemp(prefix="pruebas_cnmv_"))
os.environ["ESPEC_DATOS_DIR"] = str(TMP)
sys.path.insert(0, str(AQUI))
import comunicados as cn  # noqa: E402
import pandas as pd  # noqa: E402

FALLOS: list[str] = []
N = 0
MADRID = ZoneInfo("Europe/Madrid")


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def pagina(nombre: str) -> str:
    return (PRUEBAS / f"{nombre}.html").read_text(encoding="utf-8")


def historico_servidor() -> pd.DataFrame:
    return pd.read_csv(PRUEBAS / "comunicados-servidor-2026-11-21.csv", dtype=str, keep_default_na=False)


def limpiar() -> None:
    if cn.SIN_REGISTRO.exists():
        cn.SIN_REGISTRO.unlink()


# --------------------------------------------------------------------------- 1. ficha por número de registro
def pruebas_ficha() -> None:
    h = historico_servidor().set_index(["canal", "nreg"])
    for canal, n, nombre in (("OIR", 43244, "oir-43244"), ("IP", 3408, "ip-3408")):
        f = cn.leer_ficha(pagina(nombre), canal, n)
        rss = h.loc[(canal, str(n))]
        ok(f is not None and all(f[k] == rss[k] for k in ("emisor", "categoria", "texto", "enlace")),
           f"ficha {canal} {n}: emisor, categoría, texto y enlace iguales a los del RSS")
        ok(f is not None and f["fecha"][:16] == rss["fecha"][:16] and f["fecha"].endswith(":00"),
           f"ficha {canal} {n}: misma fecha y hora que el RSS (sin segundos)")
    f = cn.leer_ficha(pagina("oir-43552"), "OIR", 43552)
    ok(f == {"canal": "OIR", "nreg": 43552, "fecha": "2026-11-09T19:59:00", "emisor": "ENDESA, S.A.",
             "categoria": "Programas de recompra de acciones, estabilización y autocartera",
             "texto": "Programa de recompra de acciones Sexto Tramo",
             "enlace": "https://www.cnmv.es/Portal/Otra-Informacion-Relevante/Resultado-OIR.aspx?nreg=43552"},
       "ficha OIR 43552 (Endesa, 09/11, dentro del hueco) leída entera")
    f = cn.leer_ficha(pagina("ip-3413"), "IP", 3413)
    ok(f is not None and f["fecha"] == "2026-11-07T12:37:00" and f["texto"] == "El Grupo ACS niega la OPA sobre Hochtief y la venta de Turner"
       and f["enlace"].endswith("Informacion-Privilegiada/Resultado-IP.aspx?nreg=3413"), "ficha IP 3413 (ACS, sábado 07/11) leída entera")
    ok(cn.leer_ficha(pagina("oir-43552"), "OIR", 43553) is None, "una ficha no se toma por otro número")
    for nombre, canal in (("oir-99999", "OIR"), ("ip-99999", "IP")):
        ok(cn.leer_ficha(pagina(nombre), canal, 99999) is None and cn.pagina_sin_registro(pagina(nombre)),
           f"número inexistente ({canal}): sin fila y reconocido como «sin registro»")
    error = "<html><body><h1>Servicio no disponible</h1></body></html>"
    ok(cn.leer_ficha(error, "OIR", 1) is None and not cn.pagina_sin_registro(error),
       "una página de error no se toma por «sin registro» (se vuelve a pedir)")
    ok(not cn.pagina_sin_registro(pagina("oir-43552")), "una ficha con datos no es «sin registro»")
    rota = pagina("oir-43552").replace("09/11/2026", "9 de noviembre")
    try:
        cn.leer_ficha(rota, "OIR", 43552)
        ok(False, "fecha con forma inesperada: DatosRaros")
    except cn.DatosRaros:
        ok(True, "fecha con forma inesperada: DatosRaros")


# --------------------------------------------------------------------------- 2. huecos y relleno
def _h(filas: list[tuple[str, int, str]]) -> pd.DataFrame:
    return pd.DataFrame([{"canal": c, "nreg": str(n), "fecha": f, "emisor": "X", "categoria": "", "texto": "", "enlace": ""}
                         for c, n, f in filas], columns=cn.COLUMNAS)


def pruebas_huecos() -> None:
    hoy = datetime(2026, 11, 21, 9, 0, tzinfo=MADRID)
    h = _h([("OIR", n, "2026-11-10T10:00:00") for n in range(100, 111) if n not in (104, 105)]
           + [("OIR", 50, "2026-09-01T10:00:00"), ("IP", 10, "2026-11-10T10:00:00"), ("IP", 12, "2026-11-11T10:00:00")])
    nuevas = [{"canal": "OIR", "nreg": 112, "fecha": "2026-11-21T08:00:00"}]
    hu = cn.huecos(h, nuevas, hoy, set())
    ok(hu == {"IP": [11], "OIR": [111, 105, 104]}, f"huecos por canal, de los más recientes a los más antiguos: {hu}")
    ok(cn.huecos(h, nuevas, hoy, {("OIR", 105)})["OIR"] == [111, 104], "un número marcado para saltar no se pide")
    ok(cn.huecos(_h([]), [], hoy, set()) == {"IP": [], "OIR": []}, "histórico vacío: ningún hueco")
    viejo = _h([("OIR", 1, "2026-08-01T10:00:00"), ("OIR", 5, "2026-08-02T10:00:00")])
    ok(cn.huecos(viejo, [], hoy, set())["OIR"] == [], "los huecos de más de 45 días no se piden")

    paginas = {("OIR", 111): "oir-43552", ("OIR", 105): "oir-99999", ("OIR", 104): "error", ("IP", 11): "ip-3413"}

    def bajar(canal, n):
        nombre = paginas[(canal, n)]
        if nombre == "error":
            raise cn.requests.ConnectionError("sin respuesta")
        texto = pagina(nombre)
        # cada página real lleva su propio número; aquí se le da el que se pide
        return texto.replace("43552", str(n)).replace("3413", str(n)) if nombre != "oir-99999" else texto

    limpiar()
    filas, quedan, problema = cn.rellenar(h, nuevas, hoy, bajar=bajar, pausa=0)
    ok(sorted((f["canal"], f["nreg"]) for f in filas) == [("IP", 11), ("OIR", 111)], "relleno: se recuperan las dos fichas que existen")
    ok(quedan == {"IP": 0, "OIR": 2} and problema is None, f"relleno: quedan el inexistente y el que no respondió ({quedan})")
    sin = cn.leer_sin_registro()
    ok(sin == {("OIR", 105): {"consultado": "2026-11-21", "intentos": 1}}, f"el número inexistente queda anotado una vez; el fallo de red no ({sin})")
    pedidos: list = []

    def contar(canal, n):
        pedidos.append((canal, n))
        return bajar(canal, n)

    cn.rellenar(h, nuevas + filas, hoy, bajar=contar, pausa=0)
    ok(pedidos == [("OIR", 104)], f"el mismo día no se repite el inexistente; el fallo de red sí se reintenta ({pedidos})")
    pedidos.clear()
    manana = datetime(2026, 11, 22, 9, 0, tzinfo=MADRID)
    cn.rellenar(h, nuevas + filas, manana, bajar=contar, pausa=0)
    ok(("OIR", 105) in pedidos and cn.leer_sin_registro()[("OIR", 105)]["intentos"] == 2, "al día siguiente se pregunta otra vez (segundo intento)")
    pedidos.clear()
    cn.rellenar(h, nuevas + filas, datetime(2026, 11, 23, 9, 0, tzinfo=MADRID), bajar=contar, pausa=0)
    ok(("OIR", 105) not in pedidos, "tras dos intentos en días distintos, no se vuelve a pedir")

    limpiar()
    pedidos.clear()
    cn.rellenar(h, nuevas, hoy, bajar=contar, limite=2, pausa=0)
    ok(len(pedidos) == 2 and pedidos[0] == ("IP", 11), f"límite por pasada respetado ({pedidos})")

    limpiar()
    h5 = _h([("OIR", n, "2026-11-10T10:00:00") for n in (200, 210)])
    caidas: list = []

    def caida(canal, n):
        caidas.append(n)
        raise cn.requests.Timeout("tiempo agotado")

    filas, quedan, problema = cn.rellenar(h5, [], hoy, bajar=caida, pausa=0)
    ok(len(caidas) == 5 and filas == [] and problema is None and not cn.leer_sin_registro(),
       "cinco fichas seguidas sin respuesta: se para, sin anotar nada y sin error (sigue la pasada siguiente)")

    limpiar()
    raras = lambda canal, n: '<html><div id="ctl00_H1">x</div><p>Otra cosa</p></html>'  # noqa: E731
    filas, quedan, problema = cn.rellenar(h5, [], hoy, bajar=raras, pausa=0)
    ok(problema is not None and filas == [] and not cn.leer_sin_registro(),
       "si la CNMV cambia la forma de sus fichas: se avisa con error (incidencia) y no se anota nada como inexistente")


# --------------------------------------------------------------------------- 3. regla de resultados
def pruebas_clasificacion() -> None:
    casos = [
        ("Sobre negocio y situación financiera", "La sociedad remite nota de prensa sobre los resultados de los nueve primeros meses de 2026", "3T 2026"),
        ("Sobre negocio y situación financiera", "La compañía remite presentación sobre sus resultados de los nueve primeros meses de 2026", "3T 2026"),
        ("Sobre resultados", "Ferrovial remite la presentación de resultados operativos correspondiente a los nueve primeros meses de 2026", "3T 2026"),
        ("Otra información relevante", "Resultados de los seis primeros meses de 2026", "1S 2026"),
        ("Otra información relevante", "Resultados correspondientes a los primeros tres meses de 2026", "1T 2026"),
    ]
    for cat, texto, per in casos:
        ok(cn.clasificar(cat, texto) == ("resultados", "Resultados") and cn.periodo(texto, "2026-11-05") == per,
           f"resultados acumulados: «{texto[:60]}…» → Resultados {per}")
    ok(cn.clasificar("Contratos de liquidez y contrapartida", "Información trimestral del contrato de liquidez") is None,
       "los contratos de liquidez siguen fuera")
    ok(cn.clasificar("Otra información relevante", "MERLIN - Dividendo a cuenta 2026") == ("dividendos", "Dividendo"), "los dividendos no cambian")
    # Con el histórico real del servidor: la clasificación del IBEX 35 es la misma que publicaba el servidor
    # (ibex35-servidor-2026-11-21.csv, código anterior) más las cuatro de «nueve primeros meses».
    e = cn.empresas_ibex(pd.Timestamp("2026-11-21"))
    nuevo = cn.clasificados(historico_servidor(), e)
    antes = pd.read_csv(PRUEBAS / "ibex35-servidor-2026-11-21.csv", dtype=str, keep_default_na=False)
    clave = lambda d: {(r.canal, str(r.nreg)): (r.caja, r.etiqueta, r.periodo) for r in d.itertuples()}  # noqa: E731
    a, b = clave(antes), clave(nuevo)
    añadidas = {k: v for k, v in b.items() if k not in a}
    ok(all(b.get(k) == v for k, v in a.items()), "histórico real: ninguna clasificación anterior del IBEX 35 cambia")
    ok(añadidas == {("OIR", "43360"): ("resultados", "Resultados", "3T 2026"), ("IP", "3408"): ("resultados", "Resultados", "3T 2026"),
                    ("IP", "3409"): ("resultados", "Resultados", "3T 2026"), ("IP", "3372"): ("resultados", "Resultados", "3T 2026")},
       f"histórico real: se añaden exactamente Aena 43360, Cellnex 3408 y 3409 y Ferrovial 3372 ({sorted(añadidas)})")


# --------------------------------------------------------------------------- 4. paridad con la web y BME
HUECO = ["oir-43549", "oir-43550", "oir-43551", "oir-43552", "oir-43553", "oir-43584", "oir-43585", "oir-43612",
         "oir-43613", "oir-43636", "oir-43653", "ip-3413", "ip-3417"]


def pruebas_paridad_y_bme() -> None:
    import re
    filas = []
    for nombre in HUECO:
        canal, n = nombre.split("-")
        filas.append(cn.leer_ficha(pagina(nombre), canal.upper(), int(n)))
    ok(all(filas) and all("2026-11-07" <= f["fecha"][:10] <= "2026-11-13" for f in filas),
       "los 13 comunicados que faltaban en el servidor son todos del 07/11 al 13/11 (el hueco sin colector)")
    h = pd.concat([historico_servidor(), pd.DataFrame(filas, columns=cn.COLUMNAS).astype(str)], ignore_index=True)
    h = h.sort_values(["fecha", "canal", "nreg"], ascending=False).reset_index(drop=True)
    e = cn.empresas_ibex(pd.Timestamp("2026-11-21"))
    c = cn.clasificados(h, e)
    web = json.loads((PRUEBAS / "web-fichas-2026-11-21.json").read_text(encoding="utf-8"))["fichas"]
    hoy, inicio = pd.Timestamp("2026-11-21"), pd.Timestamp("2026-10-19")
    distintas = []
    for emp in e.to_dict("records"):
        frag = cn.ficha_html(c, pd.Series(emp), hoy, "2026-11-21T09:00", inicio)
        nreg = sorted(set(re.findall(r"nreg=(\d+)", frag)), key=int)
        etiquetas = [x.strip() for x in re.findall(r"<small>([^<(]*)", frag)]
        w = web[emp["ficha"]]
        if nreg != w["nreg"] or etiquetas != w["etiquetas"]:
            distintas.append(emp["ficha"])
        if "BME" in frag or "rentabilidad" in frag.lower() or "Dividendos de" in frag:
            distintas.append(emp["ficha"] + " (BME)")
    ok(len(e) == 35 and not distintas, f"las 35 fichas: mismos comunicados y etiquetas que la web del 21/11 ({distintas})")
    ok(not hasattr(cn, "DIVIDENDOS_BME") and not hasattr(cn, "dividendos_bme"), "el colector ya no tiene código de BME")
    lst = cn.listado_html(c, "dividendos", "Dividendos", hoy, "2026-11-21T09:00", inicio)
    ok("BME" not in lst and "rentabilidad" not in lst.lower() and "nreg=43636" in lst, "listado de dividendos: solo comunicados de la CNMV (Merlin 43636 incluido)")
    # ultima.json: sin «bme» y con los huecos pendientes
    shutil.rmtree(cn.SALIDA, ignore_errors=True)
    cn.ahora_madrid = lambda: datetime(2026, 11, 21, 9, 0, tzinfo=MADRID)
    cn.escribir(h, c, e, len(filas), True, {"huecos_pendientes": {"IP": 0, "OIR": 0}})
    j = json.loads((cn.DATOS / "ultima.json").read_text(encoding="utf-8"))
    ok("bme" not in j and j["huecos_pendientes"] == {"IP": 0, "OIR": 0} and j["comunicados_ibex35_clasificados"] == 121,
       f"ultima.json sin «bme», con los huecos pendientes y 121 comunicados del IBEX 35 ({j.get('comunicados_ibex35_clasificados')})")
    todo = "".join(p.read_text(encoding="utf-8") for p in cn.SALIDA.rglob("*.html"))
    ok("BME" not in todo, "ninguna salida HTML menciona BME")


if __name__ == "__main__":
    try:
        pruebas_ficha()
        pruebas_huecos()
        pruebas_clasificacion()
        pruebas_paridad_y_bme()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
