"""
Comprobaciones de la descarga del rastreador de cortos. No tocan la red.

Cubren los fallos del 21, 26, 29, 30 y 31 de octubre de 2026 (incidencia #65):
la CNMV cerraba la conexión sin responder («Remote end closed connection
without response») y los cuatro intentos de entonces, en poco más de tres
minutos, no bastaban. `requests.get` se sustituye aquí por una función que
falla las veces que se le diga y luego devuelve un .xls válido.

Uso:  python cortos/pruebas_descarga.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rastreador as r  # noqa: E402

fallos: list[str] = []
XLS = b"\xd0\xcf\x11\xe0" + b"\x00" * 60  # cabecera OLE2 de un .xls


def comprobar(descripcion: str, condicion: bool) -> None:
    print(("  ok  " if condicion else "FALLO ") + descripcion)
    if not condicion:
        fallos.append(descripcion)


class Respuesta:
    def __init__(self, status_code: int, content: bytes):
        self.status_code, self.content = status_code, content


def simular(fallos_previos: int, respuesta_final=None):
    """Devuelve un sustituto de requests.get que falla `fallos_previos` veces."""
    llamadas = {"n": 0}

    def get(url, timeout=None, headers=None):
        llamadas["n"] += 1
        if llamadas["n"] <= fallos_previos:
            raise requests.ConnectionError("('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))")
        return respuesta_final or Respuesta(200, XLS)

    return get, llamadas


dormido: list[int] = []
sin_esperar = dormido.append  # registra las esperas en vez de dormir

# ----------------------------------------------- la CNMV responde a la tercera
get, llamadas = simular(2)
r.requests.get = get
dormido.clear()
contenido = r.descargar(dormir=sin_esperar)
comprobar("dos cortes y luego el fichero: devuelve el .xls", contenido == XLS)
comprobar("dos cortes y luego el fichero: tres peticiones, ni una más", llamadas["n"] == 3)
comprobar("dos cortes y luego el fichero: espera 10 s y 20 s entre intentos", dormido == [10, 20])

# ----------------------------------------------- la CNMV responde al séptimo
get, llamadas = simular(6)
r.requests.get = get
dormido.clear()
contenido = r.descargar(dormir=sin_esperar)
comprobar("seis cortes seguidos: el séptimo intento aún se hace", contenido == XLS and llamadas["n"] == 7)
comprobar("seis cortes seguidos: las esperas suman seis minutos", sum(dormido) == 340 and dormido == r.ESPERAS)

# ----------------------------------------------- la CNMV no responde nunca
get, llamadas = simular(99)
r.requests.get = get
dormido.clear()
try:
    r.descargar(dormir=sin_esperar)
    comprobar("siete cortes: se rinde con DatosRaros", False)
except r.DatosRaros as e:
    comprobar("siete cortes: se rinde con DatosRaros", True)
    comprobar("siete cortes: el mensaje dice cuántos intentos y el último error",
              "7 intentos" in str(e) and "Remote end closed" in str(e))
comprobar("siete cortes: no hay un octavo intento", llamadas["n"] == 7)

# ----------------------------------------------- respuesta que no es un .xls
get, llamadas = simular(0, Respuesta(200, b"<html>mantenimiento</html>"))
r.requests.get = get
dormido.clear()
try:
    r.descargar(esperas=[1, 1], dormir=sin_esperar)
    comprobar("HTML en vez de .xls: se rinde con DatosRaros", False)
except r.DatosRaros as e:
    comprobar("HTML en vez de .xls: se rinde con DatosRaros", True)
    comprobar("HTML en vez de .xls: el mensaje enseña la cabecera recibida", "cabecera" in str(e))
comprobar("HTML en vez de .xls: respeta la lista de esperas que se le pasa", llamadas["n"] == 3 and dormido == [1, 1])

# ----------------------------------------------- el fichero llega a la primera
get, llamadas = simular(0)
r.requests.get = get
dormido.clear()
comprobar("sin cortes: una sola petición y ninguna espera", r.descargar(dormir=sin_esperar) == XLS and llamadas["n"] == 1 and dormido == [])

print()
if fallos:
    print(f"{len(fallos)} comprobación(es) han fallado.")
    sys.exit(1)
print("Todas las comprobaciones pasan.")
