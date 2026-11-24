"""Comprobaciones sin red de la escritura directa en WordPress (servidor/escribir_wp.py).

  python servidor/pruebas_escribir_wp.py

Un WordPress simulado en memoria (páginas, permisos, errores HTTP y un filtro que, como kses, quita los SVG a un usuario
sin unfiltered_html). Comprueba la lista cerrada de páginas, la validación del fragmento, que solo cambia lo que hay
entre las marcas (control: el mismo resultado que el patrón del escenario DIARIO de Make), que no escribe si la página
ya lleva la huella, los rechazos, la vuelta atrás si WordPress no guarda lo enviado, los reintentos, el estado que deja
y que la contraseña no sale nunca en la salida ni en el estado.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import escribir_wp as w

FALLOS: list[str] = []
N = 0
CLAVE = "abcd EFGH 1234 ijkl MNOP 5678"


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if cond:
        print(f"ok     {texto}")
    else:
        FALLOS.append(texto)
        print(f"FALLA  {texto}")


class Resp:
    def __init__(self, estado: int, cuerpo):
        self.status_code, self._c = estado, cuerpo
        self.text = json.dumps(cuerpo) if not isinstance(cuerpo, str) else cuerpo

    def json(self):
        if isinstance(self._c, str):
            raise ValueError("no es JSON")
        return self._c


class WPFalso:
    """Sesión de requests simulada: GET/POST de /pages/<id> y GET de /users/me."""

    def __init__(self, paginas: dict[int, dict], html_libre=True, altera=False, fallos: list[int] | None = None):
        self.paginas, self.html_libre, self.altera = paginas, html_libre, altera
        self.fallos = list(fallos or [])
        self.llamadas: list[tuple[str, str]] = []
        self.auth, self.headers = None, {}

    def request(self, metodo, url, timeout=None, params=None, json=None):
        ruta = url.split("/wp-json/wp/v2", 1)[1]
        self.llamadas.append((metodo, ruta))
        if self.fallos:
            return Resp(self.fallos.pop(0), "error simulado")
        if ruta == "/users/me":
            return Resp(200, {"id": 7, "capabilities": {"edit_pages": True, "unfiltered_html": self.html_libre}})
        m = re.fullmatch(r"/pages/(\d+)", ruta)
        if not m or int(m.group(1)) not in self.paginas:
            return Resp(404, {"code": "rest_post_invalid_id"})
        p = self.paginas[int(m.group(1))]
        if metodo == "POST":
            contenido = json["content"]
            if self.altera:  # como kses con un usuario sin unfiltered_html
                contenido = re.sub(r"<svg.*?</svg>", "", contenido, flags=re.S)
            p["raw"] = contenido
        return Resp(200, {"id": int(m.group(1)), "status": p["status"], "content": {"raw": p["raw"]}, "modified": "2026-11-24T03:00:00"})


def fragmento(marca: str, huella: str, cuerpo: str = "", relleno: int = 3200) -> str:
    return f"<!-- {marca}:inicio {huella} -->\n<p>{cuerpo}</p>\n<svg viewBox=\"0 0 10 10\"><circle r=\"1\"/></svg>\n<p>{'x' * relleno}</p>\n<!-- {marca}:fin -->\n"


def pagina(marca: str, huella: str) -> str:
    return ("<!-- wp:html -->\n<p>Entrada fija de la página.</p>\n" + fragmento(marca, huella, "viejo").rstrip("\n")
            + "\n\n<p class=\"pie\">Pie fijo.</p>\n<!-- /wp:html -->")


def entorno_base(tmp: Path, **extra) -> dict:
    e = {"ESPEC_DATOS_DIR": str(tmp), "ESPEC_WP_ESCRIBIR": "1", "ESPEC_WP_USUARIO": "colectores", "ESPEC_WP_CLAVE": CLAVE}
    e.update(extra)
    return e


def preparar(tmp: Path, colector: str, marca: str, huella: str) -> None:
    (tmp / colector).mkdir(parents=True, exist_ok=True)
    (tmp / colector / "fragmento-wp.html").write_text(fragmento(marca, huella, "nuevo"), encoding="utf-8")


def con_wp(falso: WPFalso) -> w.WordPress:
    return w.WordPress("https://elespeculador.com", "colectores", CLAVE, sesion=falso, dormir=lambda s: None)


def main() -> None:
    repo = AQUI.parent
    # ----- lista cerrada de páginas
    pag = w.cargar_paginas()
    ok(len(pag) == 17 and len({p["pagina"] for p in pag.values()}) == 17, "17 colectores con 17 páginas distintas")
    ok(pag["ofertas"] == {"pagina": 8588, "marca": "opas", "minimo": 3000} and pag["calendario"]["marca"] == "dividendos" and pag["calendario"]["pagina"] == 8578,
       "OPAs escribe en 8588 con las marcas opas y el calendario en 8578 con las marcas dividendos")
    ok(all((repo / c).is_dir() for c in pag), "cada colector de la lista existe en el repositorio")
    ok("cnmv" not in pag and "empresas" not in pag, "ni el colector de comunicados ni las fichas de empresa escriben en WordPress")

    # ----- fragmento
    f = fragmento("morosidad", "abc123")
    ok(w.validar_fragmento("﻿" + f, "morosidad", 3000) == f.rstrip("\n"), "fragmento válido: sin BOM ni salto final")
    for malo, texto in [(f.replace("<!-- morosidad:inicio", "<!-- otra:inicio"), "sin marca de inicio"),
                        (f.replace("<!-- morosidad:fin -->", ""), "sin marca de fin"),
                        (f + "<!-- morosidad:fin -->", "marca de fin repetida"),
                        (fragmento("morosidad", "abc", relleno=10), "demasiado corto")]:
        try:
            w.validar_fragmento(malo, "morosidad", 3000)
            ok(False, f"fragmento {texto}: rechazado")
        except w.Rechazo:
            ok(True, f"fragmento {texto}: rechazado")

    # ----- sustitución
    raw = pagina("morosidad", "viejo1")
    nuevo_f = fragmento("morosidad", "nuevo2", "nuevo").rstrip("\n")
    nuevo = w.sustituir(raw, nuevo_f, "morosidad")
    i = raw.index("<!-- morosidad:inicio")
    j = raw.index("<!-- morosidad:fin -->") + len("<!-- morosidad:fin -->")
    ok(nuevo[:i] == raw[:i] and nuevo.endswith(raw[j:]) and nuevo_f in nuevo, "solo cambia lo que hay entre las marcas: entrada y pie byte a byte")
    make = re.sub(r"<!-- morosidad:inicio[\s\S]*?<!-- morosidad:fin -->", lambda m: nuevo_f, raw, count=1)
    ok(nuevo == make, "control: el mismo resultado que el patrón del escenario DIARIO de Make")
    ok(w.sustituir(nuevo, nuevo_f, "morosidad") is None, "si la página ya lleva la huella, no hay nada que escribir")
    for malo, texto in [(raw.replace("<!-- morosidad:fin -->", ""), "página sin marca de fin"),
                        (raw + "\n<!-- morosidad:inicio x -->", "página con dos marcas de inicio"),
                        ("<!-- morosidad:fin -->" + raw.replace("<!-- morosidad:fin -->", "").replace("<p class=\"pie\">", "<!-- morosidad:inicio y --><p class=\"pie\">").replace("<!-- morosidad:inicio viejo1 -->", ""), "marcas en orden inverso")]:
        try:
            w.sustituir(malo, nuevo_f, "morosidad")
            ok(False, f"{texto}: rechazada")
        except w.Rechazo:
            ok(True, f"{texto}: rechazada")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        preparar(tmp, "morosidad", "morosidad", "nuevo2")
        # ----- cuándo no le toca
        falso = WPFalso({9502: {"status": "draft", "raw": pagina("morosidad", "viejo1")}})
        for ent, esperado, texto in [({"ESPEC_DATOS_DIR": t}, "desactivada", "sin ESPEC_WP_ESCRIBIR=1"),
                                     (entorno_base(tmp, ESPEC_WP_CLAVE=""), "desactivada", "sin contraseña"),
                                     (entorno_base(tmp, ESPEC_WP_SOLO="ciclo, agenda"), "fuera_de_ESPEC_WP_SOLO", "fuera de ESPEC_WP_SOLO")]:
            codigo, est = w.escribir("morosidad", ent, wp=con_wp(falso))
            ok(codigo == w.NO_TOCA and est["resultado"] == esperado and not falso.llamadas, f"{texto}: no le toca y no llama a WordPress")
        codigo, est = w.escribir("cnmv", entorno_base(tmp), wp=con_wp(falso))
        ok(codigo == w.NO_TOCA and est["resultado"] == "sin_pagina" and not falso.llamadas, "colector sin página (cnmv): no le toca")

        # ----- escribe
        codigo, est = w.escribir("morosidad", entorno_base(tmp, ESPEC_WP_SOLO="morosidad"), wp=con_wp(falso))
        guardado = falso.paginas[9502]["raw"]
        ok(codigo == 0 and est["resultado"] == "escrita" and "<!-- morosidad:inicio nuevo2 -->" in guardado
           and guardado.startswith("<!-- wp:html -->\n<p>Entrada fija de la página.</p>\n") and guardado.endswith("<p class=\"pie\">Pie fijo.</p>\n<!-- /wp:html -->"),
           "con la huella nueva escribe, y la entrada y el pie de la página siguen igual")
        ok([m for m, _ in falso.llamadas] == ["GET", "GET", "POST"] and ("GET", "/users/me") in falso.llamadas,
           "lee la página, comprueba el permiso de HTML y escribe una sola vez")
        falso.llamadas.clear()
        codigo, est = w.escribir("morosidad", entorno_base(tmp), wp=con_wp(falso))
        ok(codigo == 0 and est["resultado"] == "al_dia" and falso.llamadas == [("GET", "/pages/9502")], "la segunda vez ya está al día: solo lee")

        # ----- rechazos
        def rechaza(paginas: dict, texto: str, **kw) -> WPFalso:
            f2 = WPFalso(paginas, **kw)
            try:
                w.escribir("morosidad", entorno_base(tmp), wp=con_wp(f2))
                ok(False, texto)
            except (w.Rechazo, RuntimeError):
                ok(not any(m == "POST" for m, _ in f2.llamadas), texto)
            return f2
        rechaza({9502: {"status": "trash", "raw": pagina("morosidad", "viejo1")}}, "página en la papelera: no escribe")
        rechaza({9502: {"status": "publish", "raw": "<p>sin marcas</p>"}}, "página sin marcas: no escribe")
        rechaza({9502: {"status": "publish", "raw": pagina("morosidad", "viejo1")}}, "usuario sin unfiltered_html: no escribe", html_libre=False)
        rechaza({}, "página que no existe (404): no escribe")
        f3 = rechaza({9502: {"status": "publish", "raw": pagina("morosidad", "viejo1")}}, "error 500 en la lectura: no escribe", fallos=[500, 500, 500])
        ok(len(f3.llamadas) == 3, "error 500: tres intentos (dos reintentos)")
        f4 = rechaza({9502: {"status": "publish", "raw": pagina("morosidad", "viejo1")}}, "error 401: no escribe", fallos=[401])
        ok(len(f4.llamadas) == 1, "error 401: no reintenta")
        original = pagina("morosidad", "viejo1")
        f5 = WPFalso({9502: {"status": "publish", "raw": original}}, altera=True)
        try:
            w.escribir("morosidad", entorno_base(tmp), wp=con_wp(f5))
            ok(False, "WordPress guarda otra cosa: error")
        except w.Rechazo as e:
            ok("devuelta a como estaba" in str(e), "WordPress guarda otra cosa (quita el SVG): error")
        ok([m for m, _ in f5.llamadas].count("POST") == 2, "y devuelve la página a su contenido anterior (segundo envío)")
        (tmp / "morosidad" / "fragmento-wp.html").unlink()
        rechaza({9502: {"status": "publish", "raw": original}}, "sin fragmento en el servidor: no escribe")

        # ----- main: estado y secretos
        preparar(tmp, "ciclo", "ciclo", "h9")
        salida = io.StringIO()
        original_wp = w.WordPress
        falso6 = WPFalso({9504: {"status": "draft", "raw": pagina("ciclo", "h1")}})
        w.WordPress = lambda base, u, c: original_wp("https://elespeculador.com", u, c, sesion=falso6, dormir=lambda s: None)
        try:
            with contextlib.redirect_stdout(salida):
                r1 = w.main(["ciclo"], entorno_base(tmp))
                r2 = w.main(["morosidad"], entorno_base(tmp))
                r3 = w.main(["ciclo"], {"ESPEC_DATOS_DIR": t})
        finally:
            w.WordPress = original_wp
        e1 = json.loads((tmp / "estado" / "ciclo-web.json").read_text(encoding="utf-8"))
        e2 = json.loads((tmp / "estado" / "morosidad-web.json").read_text(encoding="utf-8"))
        ok(r1 == 0 and e1["resultado"] == "escrita" and e1["pagina"] == 9504, "main: escribe y deja estado/ciclo-web.json «escrita»")
        ok(r2 == 1 and e2["resultado"] == "fallo" and "fragmento" in e2["motivo"], "main: un fallo sale con 1 y deja el motivo en el estado")
        ok(r3 == w.NO_TOCA, "main: apagada sale con 10 (ejecutar.sh no abre incidencia)")
        todo = salida.getvalue() + json.dumps(e1) + json.dumps(e2)
        ok(CLAVE not in todo and "EFGH" not in todo, "la contraseña no sale ni en la salida ni en el estado")

    r = subprocess.run(["bash", "-n", str(AQUI / "ejecutar.sh")], capture_output=True, text=True, check=False)
    ok(r.returncode == 0, "servidor/ejecutar.sh sin errores de sintaxis")
    texto = (AQUI / "ejecutar.sh").read_text(encoding="utf-8")
    ok("escribir_wp.py" in texto and texto.index("escribir_wp.py") > texto.index("estado correcto 0"),
       "ejecutar.sh llama a la escritura solo después de dejar el estado «correcto» del colector")

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")


if __name__ == "__main__":
    main()
