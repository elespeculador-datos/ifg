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
import dividendos_cnmv as dv  # noqa: E402
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
    for f in (cn.SIN_REGISTRO, cn.SIN_RESPUESTA):
        if f.exists():
            f.unlink()


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
    f = cn.leer_ficha(pagina("oir-41510"), "OIR", 41510)
    ok(f is not None and f["nreg"] == 41510 and f["emisor"] == "MIQUEL Y COSTAS & MIQUEL, S.A." and f["fecha"] == "2026-06-23T12:04:00"
       and "Número de registro: 41507" in f["texto"], "una subsanación que cita otro número en el título se lee con su propio número")
    ok(cn.leer_ficha(pagina("oir-41510"), "OIR", 41507) is None, "y no se toma por la comunicación que cita")
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


def pruebas_atras() -> None:
    """Relleno hacia atrás hasta doce meses (registro oficial de las fichas)."""
    hoy = datetime(2026, 11, 21, 9, 0, tzinfo=MADRID)
    base = pagina("oir-43552")

    def ficha_con(n: int, dia: str) -> str:  # la ficha real de Endesa con otro número y otra fecha
        return base.replace("43552", str(n)).replace("09/11/2026", dia)

    h = _h([("OIR", n, "2026-11-10T10:00:00") for n in range(100, 106)] + [("IP", 50, "2026-11-12T10:00:00")])
    paginas = {("OIR", 99): ficha_con(99, "01/11/2026"), ("OIR", 98): pagina("oir-99999"), ("OIR", 97): ficha_con(97, "20/10/2026"),
               ("IP", 49): pagina("ip-3413").replace("3413", "49").replace("07/11/2026", "01/10/2026")}
    pedidos: list = []

    def bajar(canal, n):
        pedidos.append((canal, n))
        if (canal, n) not in paginas:
            raise cn.requests.ConnectionError("sin respuesta")
        return paginas[(canal, n)]

    limpiar()
    filas, estado, problema = cn.rellenar_atras(h, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok([(f["canal"], f["nreg"]) for f in filas] == [("IP", 49), ("OIR", 99), ("OIR", 97)] and estado == {"IP": "completo", "OIR": "completo"}
       and problema is None, f"hacia atrás: primero IP, luego OIR, hasta el primer comunicado anterior al objetivo ({estado})")
    ok(pedidos == [("IP", 49), ("OIR", 99), ("OIR", 98), ("OIR", 97)], f"hacia atrás: número a número, sin saltos ({pedidos})")
    ok(cn.leer_sin_registro() == {("OIR", 98): {"consultado": "2026-11-21", "intentos": 2}}, "hacia atrás: el número inexistente se anota y no se repite")
    h2 = pd.concat([h, pd.DataFrame(filas, columns=cn.COLUMNAS).astype(str)], ignore_index=True)
    pedidos.clear()
    filas2, estado2, _ = cn.rellenar_atras(h2, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok(filas2 == [] and pedidos == [] and estado2 == {"IP": "completo", "OIR": "completo"}, "con el histórico completo hacia atrás, no se pide nada")
    ok(cn.resumen_historico(h2, hoy, dias=30) == {"IP": {"desde": "2026-10-01", "completo": True}, "OIR": {"desde": "2026-10-20", "completo": True}}
       and cn.resumen_historico(h, hoy, dias=30)["OIR"] == {"desde": "2026-11-10", "completo": False}, "resumen del histórico: desde cuándo y si está completo")

    limpiar()
    pedidos.clear()
    del paginas[("OIR", 98)]
    filas, estado, problema = cn.rellenar_atras(h, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok([f["nreg"] for f in filas] == [49, 99] and estado["OIR"] == "parado" and problema is None and not cn.leer_sin_registro()
       and cn.leer_sin_respuesta() == {("OIR", 98): {"consultado": "2026-11-21", "intentos": 1}},
       "hacia atrás: si una ficha no responde, ese canal se para y se anota el fallo, no como número inexistente")
    h3 = pd.concat([h, pd.DataFrame(filas, columns=cn.COLUMNAS).astype(str)], ignore_index=True)
    pedidos.clear()
    cn.rellenar_atras(h3, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok(pedidos[:1] == [("OIR", 98)], f"la pasada siguiente empieza por el número que falló ({pedidos[:1]})")
    pedidos.clear()
    filas3, estado3, _ = cn.rellenar_atras(h3, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok(pedidos == [("OIR", 98)] and estado3["OIR"] == "parado" and cn.saltadas() == ["OIR 98"],
       f"tercer fallo de la misma ficha: se anota como saltada ({pedidos}, {cn.saltadas()})")
    pedidos.clear()
    filas4, estado4, _ = cn.rellenar_atras(h3, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok(pedidos == [("OIR", 97)] and [f["nreg"] for f in filas4] == [97] and estado4["OIR"] == "completo",
       f"con tres fallos, el relleno la salta y sigue hasta completar ({pedidos}, {estado4})")
    limpiar()
    cn.guardar_sin_respuesta({("OIR", 98): {"consultado": "2026-11-20", "intentos": 2}})
    paginas[("OIR", 98)] = ficha_con(98, "25/10/2026")
    filas5, _, _ = cn.rellenar_atras(h3, [], hoy, bajar=bajar, pausa=0, dias=30)
    ok([f["nreg"] for f in filas5][:1] == [98] and cn.leer_sin_respuesta() == {} and cn.saltadas() == [],
       "una ficha que falló y luego responde se guarda y sale de la lista de fallos")
    del paginas[("OIR", 98)]

    limpiar()
    pedidos.clear()
    paginas[("OIR", 98)] = pagina("oir-99999")
    filas, estado, _ = cn.rellenar_atras(h, [], hoy, bajar=bajar, limite=2, pausa=0, dias=30)
    ok(len(pedidos) == 2 and estado == {"IP": "completo", "OIR": "en curso"}, f"hacia atrás: límite por pasada ({estado}, {pedidos})")

    limpiar()
    raras = lambda canal, n: '<html><div id="ctl00_H1">x</div><p>Otra cosa</p></html>'  # noqa: E731
    filas, estado, problema = cn.rellenar_atras(h, [], hoy, bajar=raras, pausa=0, dias=30)
    ok(problema is not None and filas == [] and estado["OIR"] == "parado" and not cn.leer_sin_registro(),
       "hacia atrás: una ficha con forma desconocida para el relleno y da error, sin anotar nada")


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
    ok(cn.clasificar("Sobre planes estratégicos y previsiones", "Nota de prensa relativa a la presentación de planes estratégicos y objetivos "
                     "en el Investor Day, y a la política de retribución al accionista") == ("dividendos", "Política de dividendos"),
       "anuncio de la política de retribución: «Política de dividendos», no un pago")
    ok(cn.clasificar("Sobre negocio y situación financiera", "Aprobación por el consejo de administración de un dividendo complementario "
                     "en efectivo conforme a la política de retribución") == ("dividendos", "Dividendo"), "un pago concreto sigue siendo «Dividendo»")
    ok(dv.extraer("dividendo de 0,30 euros brutos por acción", __import__("datetime").date(2026, 2, 25), "Política de dividendos")["extraccion"]
       == "sin pago: ver comunicado", "política de dividendos: no se lee importe")
    # Recompras de deuda (vistas al rellenar doce meses, 22/11/2026): no son programas de recompra de acciones
    for texto in ("Unicaja informa de una oferta de recompra de las Obligaciones Verdes Ordinarias No Preferentes ISIN: ES0380907065",
                  "Mapfre, S.A. informa de una oferta de recompra en efectivo dirigida a todos los titulares de obligaciones subordinadas de la emisión",
                  "Santander anuncia el lanzamiento de una oferta de recompra con contraprestación en efectivo de hasta 850.000.000 USD de la emisión en circulación",
                  "Oferta de recompra de bonos convertibles senior no garantizados de importe nominal 825.000.000 € con vencimiento en 2028",
                  "Unicaja informa de una oferta de recompra de las Participaciones Preferentes perpetuas no acumulativas de nivel adicional 1"):
        ok(cn.clasificar("Sobre instrumentos financieros", texto) is None, f"recompra de deuda fuera de «recompras»: «{texto[:50]}…»")
    for cat, texto in (("Programas de recompra de acciones, estabilización y autocartera", "Compras del 20 al 26 de octubre de 2026"),
                       ("Otra información relevante", "Finalización del Programa de Recompra y próxima reducción de capital social"),
                       ("Otra información relevante", "Programa de recompra de acciones para amortizar y atender obligaciones de planes de retribución"),
                       ("Otra información relevante", "Banco Sabadell comunica información sobre programa de recompra.")):
        ok(cn.clasificar(cat, texto) == ("recompras", "Programa de recompra"), f"recompra de acciones sigue dentro: «{texto[:50]}…»")
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


# --------------------------------------------------------------------------- 3 bis. dividendos leídos del comunicado
# Valores comprobados a mano en cada PDF el 22/11/2026 (segunda lectura independiente del analizador).
DIVIDENDOS_REALES = {
    "OIR-43348": (0.08, "EUR", "2026-11-24", "2026-11-25", "2026-11-26", "completa"),    # Mapfre
    "OIR-43351": (0.204, "EUR", "2027-01-05", "2027-01-06", "2027-01-07", "completa"),   # Redeia
    "IP-3391": (0.56, "EUR", "2027-01-12", "2027-01-13", "2027-01-14", "completa"),      # Repsol: 0,53 + 0,03; viñetas con la fecha delante
    "IP-3397": (0.0642, "EUR", "2026-12-15", "2026-12-16", "2026-12-17", "completa"),    # Unicaja: 6,42 céntimos
    "OIR-43416": (0.1844, "EUR", "2026-11-04", None, "2026-11-06", "completa"),          # CaixaBank
    "OIR-43452": (0.15, "EUR", None, None, "2026-12-04", "parcial"),                     # Grifols: sin fecha ex
    "OIR-43510": (0.053, "EUR", "2026-12-03", "2026-12-04", "2026-12-07", "completa"),   # IAG: importe del título
    "OIR-43702": (0.4, "EUR", "2026-12-14", "2026-12-15", "2026-12-16", "completa"),     # Enagás
}


# Lector del 22/11/2026, con la revisión de los 32 comunicados de dividendo de doce meses del IBEX 35 (comprobados
# uno a uno contra su texto): cada caso fija una forma de escribir el calendario o una cifra que no es la del pago.
MAS_DIVIDENDOS_REALES = {
    "IP-2967": (0.5, "EUR", "2026-01-12", "2026-01-13", "2026-01-14", "completa"),       # Repsol: viñetas; el ex-date de los ADR no cuenta
    "IP-3004": (0.30121021, "EUR", "2025-11-28", "2025-12-01", "2025-12-02", "completa"),  # Bankinter: tabla de cabeceras y valores
    "IP-3064": (0.3321, "EUR", None, None, None, "parcial"),                            # CaixaBank: el total del año (0,50) no cuenta
    "IP-3099": (0.551, "EUR", None, None, None, "parcial"),                             # Repsol: ni el total de 2026 ni lo pagado en enero
    "IP-3115": (0.125, "EUR", "2026-04-30", "2026-05-04", "2026-05-05", "completa"),    # Santander: céntimos; fechas sin año
    "IP-3150": (None, None, None, None, None, "sin datos"),                             # Repsol: dos repartos en la junta: ninguno
    "IP-3249": (0.1, "EUR", "2026-06-29", "2026-06-30", "2026-07-01", "completa"),      # Sacyr: viñetas con el día de la semana
    "IP-3327": (0.0844, "EUR", "2026-09-22", "2026-09-23", "2026-09-24", "completa"),   # Unicaja: «8,44 céntimos brutos»
    "IP-3356": (0.127, "EUR", "2026-10-29", "2026-10-30", "2026-11-02", "completa"),    # Santander: «cotizará ex-dividendo el…»
    "OIR-41518": (0.6, "EUR", "2026-06-30", "2026-07-01", "2026-07-02", "completa"),    # Enagás: el 0,4 ya pagado no cuenta
    "OIR-41586": (0.9594, "EUR", "2026-07-13", "2026-07-14", "2026-07-15", "completa"),  # Rovi: fechas sin año
    "OIR-41650": (5.74867096, "EUR", "2026-07-07", "2026-07-08", "2026-07-09", "completa"),  # Acciona: ajustado por la autocartera
    "OIR-43553": (0.33, "EUR", "2026-12-08", "2026-12-09", "2026-12-10", "completa"),   # Fluidra: segundo pago; el primero ya pasó
    "OIR-43636": (0.2, "EUR", "2026-11-20", "2026-11-23", "2026-12-10", "completa"),    # Merlin: «(0,20€) brutos por acción»
    "OIR-43701": (0.080248, "EUR", "2026-11-24", "2026-11-25", "2026-11-26", "completa"),  # Mapfre: importe ajustado
}


def pruebas_dividendos() -> None:
    from datetime import date
    fuentes = {r["fichero"][:-4]: r for r in csv.DictReader((PRUEBAS / "dividendos" / "fuentes.csv").open(encoding="utf-8"))}
    for nombre, (imp, mon, ex, reg, pago, ext) in {**DIVIDENDOS_REALES, **MAS_DIVIDENDOS_REALES}.items():
        f = fuentes[nombre]
        texto = f["titulo"] + "\n" + (PRUEBAS / "dividendos" / f"{nombre}.txt").read_text(encoding="utf-8")
        r = dv.extraer(texto, date.fromisoformat(f["fecha_comunicado"]), "Dividendo")
        leido = (r["importe_bruto"], r["moneda"], *(str(r[k]) if r[k] else None for k in ("fecha_ex", "fecha_registro", "fecha_pago")), r["extraccion"])
        ok(leido == (imp, mon, ex, reg, pago, ext), f"dividendo real {nombre} ({f['empresa']}): {leido}")
    com = date(2026, 10, 20)
    usd = dv.extraer("ArcelorMittal announces a quarterly dividend of US$0.125 per share. Ex-dividend date: November 18, 2026. "
                     "Payment date: December 9, 2026.", com)
    ok((usd["importe_bruto"], usd["moneda"], usd["extraccion"]) == (0.125, "USD", "completa"), "dividendo en dólares: moneda USD, no EUR")
    sin = dv.extraer("Importe bruto por acción: 0,25. Fecha ex-dividendo 15/12/2026. Fecha de pago 17/12/2026", com)
    ok(sin["importe_bruto"] is None and sin["moneda"] is None and sin["extraccion"] == "parcial", "importe sin moneda escrita: no se publica")
    ok(dv.extraer("Iberdrola Retribución Flexible", com, "Dividendo flexible")["extraccion"] == "flexible: ver comunicado", "flexible: no se lee importe")
    mal = dv.extraer("dividendo de 0,30 euros brutos por acción. Fecha ex-dividendo: 20 de diciembre de 2026. Fecha de pago: 10 de diciembre de 2026.", com)
    ok(mal["fecha_ex"] is None and mal["fecha_pago"] is None and mal["importe_bruto"] == 0.3, "fecha ex posterior al pago: fuera las fechas, queda el importe")
    viejo = dv.extraer("dividendo de 0,30 euros brutos por acción. Fecha de pago: 10 de enero de 2025.", com)
    ok(viejo["fecha_pago"] is None, "fecha de pago anterior al comunicado: fuera")
    largo = dv.extraer("Informe de resultados. " * 1500 + "Dividendo de 0,30 euros brutos por acción. Fecha de pago: 10 de diciembre de 2026.", com)
    ok(largo["importe_bruto"] is None and largo["fecha_pago"] is None and largo["extraccion"] == "sin datos",
       "documento largo (informe de resultados): no se lee nada")
    dos = dv.extraer("Dividendo de 0,30 euros brutos por acción el 10 de diciembre de 2026 y otro de 0,40 euros brutos por acción en 2027.", com)
    ok(dos["importe_bruto"] is None, "dos importes distintos sin regla segura: ninguno")
    ajuste = dv.extraer("Dividendo de 0,25 euros brutos por acción, que tras la autocartera queda en 0,2531 euros brutos por acción.", com)
    ok(ajuste["importe_bruto"] == 0.2531, "importe aprobado y ajustado por la autocartera: el ajustado")
    lejos = dv.extraer("Dividendo de 0,25 euros brutos por acción, frente a 0,2531 euros brutos por acción el año pasado y 0,26 euros brutos por acción antes.", com)
    ok(lejos["importe_bruto"] is None, "tres importes que no suman: ninguno")
    sin_ano = dv.extraer("Dividendo de 0,25 euros brutos por acción. Fecha de pago: 15 de enero.", com)
    ok(str(sin_ano["fecha_pago"]) == "2027-01-15", "fecha sin año en un comunicado de octubre: enero del año siguiente")
    sin_ano = dv.extraer("Dividendo de 0,25 euros brutos por acción. Fecha de pago: 15 de junio.", com)
    ok(sin_ano["fecha_pago"] is None, "fecha sin año que no puede ser posterior al comunicado: fuera")
    suma = dv.extraer("El pago de 0,30 euros brutos por acción se suma al dividendo de 0,20 euros brutos por acción de junio.", com)
    ok(suma["importe_bruto"] == 0.3, "«se suma al dividendo de…»: esa cifra es de otro pago")
    frases = dv.extraer("El consejo se reunió el 27 de octubre de 2026. Se informará de la fecha de pago más adelante. "
                        "El dividendo se aprobó el 28 de octubre de 2026. La record date se fijará en diciembre.", com)
    ok(frases["fecha_pago"] is None and frases["fecha_registro"] is None, "fecha delante de una frase que no es una viñeta: no es del calendario")
    vineta = dv.extraer("Las acciones cotizarán sin derecho al dividendo (ex-date).\n- 14 de diciembre de 2026: junta general.", com)
    ok(vineta["fecha_ex"] is None, "la fecha de la viñeta siguiente no es la de la etiqueta anterior")

    # actualizar(): una fila por comunicado de dividendo (canal y número), sin repetir lecturas
    datos = TMP / "div" / "cnmv" / "datos"
    datos.mkdir(parents=True, exist_ok=True)
    cab = "canal,nreg,fecha,emisor,categoria,texto,enlace,isin,empresa,ficha,caja,etiqueta,periodo,grupo\n"
    filas = [f"{fuentes[n]['canal']},{fuentes[n]['nreg']},{fuentes[n]['fecha_comunicado']}T10:00:00,X,Dividendos,\"{fuentes[n]['titulo']}\",{fuentes[n]['enlace']},ES0,{fuentes[n]['empresa']},f,dividendos,Dividendo,,g{i}"
             for i, n in enumerate(DIVIDENDOS_REALES)]
    filas += ["OIR,43244,2026-10-21T08:29:27,IBERDROLA,Otros,Iberdrola Retribución Flexible,https://x,ES0144580Y14,Iberdrola,iberdrola,dividendos,Dividendo flexible,,gf",
              "OIR,3391,2020-06-01T10:00:00,OTRA,Otros,Resultados,https://y,ES1,Otra,otra,resultados,Resultados,1T 2020,gr"]
    (datos / "ibex35.csv").write_text(cab + "\n".join(filas) + "\n", encoding="utf-8")
    pedidos: list = []

    def texto_de(canal, nreg, enlace):
        pedidos.append((canal, nreg))
        nombre = f"{canal}-{nreg}"
        if nombre == "OIR-43452" and pedidos.count((canal, nreg)) == 1:
            return None   # la primera vez no hay documento
        return (PRUEBAS / "dividendos" / f"{nombre}.txt").read_text(encoding="utf-8")

    r1 = dv.actualizar(datos, limite=5, texto_de=texto_de)
    tabla = {(r["canal"], r["nreg"]): r for r in csv.DictReader((datos / "dividendos.csv").open(encoding="utf-8"))}
    ok(r1["leidos"] == 5 and r1["pendientes"] == 4 and tabla[("OIR", "43452")]["extraccion"] == "sin documento",
       f"límite por pasada: 5 leídos y 4 pendientes; el que no tenía documento queda así ({r1})")
    n_antes = len(pedidos)
    r2 = dv.actualizar(datos, limite=20, texto_de=texto_de)
    tabla = {(r["canal"], r["nreg"]): r for r in csv.DictReader((datos / "dividendos.csv").open(encoding="utf-8"))}
    ok(r2["leidos"] == 5 and ("OIR", "43452") in pedidos[n_antes:] and tabla[("OIR", "43452")]["extraccion"] == "parcial"
       and tabla[("OIR", "43452")]["intentos"] == "2", "pasada siguiente: los pendientes y otra vez el que no tenía documento, que ahora se lee")
    ok(len(tabla) == 9 and ("OIR", "3391") not in tabla and ("IP", "3391") in tabla, "una fila por comunicado de dividendo; IP 3391 y OIR 3391 no se confunden")
    ok(("OIR", "43244") not in pedidos and tabla[("OIR", "43244")]["extraccion"] == "flexible: ver comunicado", "el flexible no se descarga")
    ok(tabla[("OIR", "43510")]["importe_bruto"] == "0.053" and tabla[("OIR", "43510")]["moneda"] == "EUR", "IAG: importe del título del registro")
    n_antes = len(pedidos)
    ok(dv.actualizar(datos, limite=20, texto_de=texto_de)["leidos"] == 0 and len(pedidos) == n_antes, "con todo leído, no se pide nada")
    ok(all(r["lector"] == dv.LECTOR for r in tabla.values()), "cada fila guarda la versión del lector que la leyó")
    # una fila leída con un lector anterior (sin columna «lector») se vuelve a leer
    vieja = pd.read_csv(datos / "dividendos.csv", dtype=str, keep_default_na=False)
    vieja.loc[vieja["nreg"] == "3391", ["importe_bruto", "extraccion"]] = ["9.99", "parcial"]
    vieja.drop(columns=["lector"]).to_csv(datos / "dividendos.csv", index=False)
    r3 = dv.actualizar(datos, limite=20, texto_de=texto_de)
    tabla = {(r["canal"], r["nreg"]): r for r in csv.DictReader((datos / "dividendos.csv").open(encoding="utf-8"))}
    ok(r3["leidos"] == 9 and tabla[("IP", "3391")]["importe_bruto"] == "0.56" and tabla[("IP", "3391")]["lector"] == dv.LECTOR,
       f"lector nuevo: se vuelve a leer todo (desde la caché) y se corrige lo que leía mal el anterior ({r3['leidos']})")


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
        pruebas_atras()
        pruebas_clasificacion()
        pruebas_dividendos()
        pruebas_paridad_y_bme()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
