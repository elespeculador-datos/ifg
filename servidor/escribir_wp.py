"""Copia el fragmento de un colector a su página de WordPress, solo entre sus marcas. Sustituye a los escenarios DIARIO
de Make (paso 4 del circuito previsto en el cambio de plataforma del 11/11/2026: el servidor escribe en la web).

  servidor/escribir_wp.py <colector>

Lo llama servidor/ejecutar.sh después de cada pasada correcta. Hace lo mismo que el escenario DIARIO, con los mismos
filtros y alguno más:

  1. Solo actúa sobre las páginas de servidor/paginas_wp.csv (lista cerrada: páginas de datos de Datos; nunca fichas
     de valores, Evergreen ni nada de Tecnología) y solo si la escritura está encendida en el entorno del servidor:
     ESPEC_WP_ESCRIBIR=1, ESPEC_WP_USUARIO y ESPEC_WP_CLAVE (contraseña de aplicación). ESPEC_WP_SOLO (opcional) limita
     los colectores, separados por comas, para encenderlo poco a poco.
  2. El fragmento tiene que empezar por <!-- marca:inicio HUELLA -->, acabar en <!-- marca:fin --> y pasar del mínimo
     de caracteres de su página.
  3. La página tiene que existir, no estar en la papelera y llevar cada marca exactamente una vez, en orden.
  4. Si la página ya lleva la primera línea del fragmento (la huella), no escribe: así puede convivir con Make, que
     hace la misma comprobación, sin que ninguno de los dos escriba dos veces.
  5. Sustituye solo lo que hay entre las marcas (ambas incluidas): el resto de la página queda byte a byte igual.
  6. Antes de la primera escritura de cada pasada comprueba que el usuario puede publicar HTML sin filtrar
     (unfiltered_html): sin ese permiso WordPress quitaría los gráficos SVG y el JSON-LD. Sin él, no escribe.
  7. Después de escribir, relee la página: si lo guardado no es exactamente lo enviado, devuelve la página a como
     estaba y termina con error.

Salida: 0 = escrita o ya al día; 10 = no le toca (escritura apagada, colector sin página o fuera de ESPEC_WP_SOLO);
1 = fallo (ejecutar.sh abre la incidencia <colector>-web-fallido). Deja el estado en
$ESPEC_DATOS_DIR/estado/<colector>-web.json (sin secretos). Nunca imprime la contraseña.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
PAGINAS = AQUI / "paginas_wp.csv"
NO_TOCA = 10
ESPERAS = (5, 15)
MAXIMO = 600_000  # caracteres de un fragmento; los de hoy van de 4.700 a 36.000


class Rechazo(Exception):
    """La página o el fragmento no cumplen las condiciones: no se escribe nada."""


def cargar_paginas(ruta: Path = PAGINAS) -> dict[str, dict]:
    paginas = {}
    for fila in csv.DictReader(ruta.open(encoding="utf-8")):
        paginas[fila["colector"].strip()] = {"pagina": int(fila["pagina"]), "marca": fila["marca"].strip(), "minimo": int(fila["minimo"])}
    return paginas


def validar_fragmento(texto: str, marca: str, minimo: int) -> str:
    t = texto.lstrip("﻿").rstrip("\n")
    primera = t.split("\n", 1)[0]
    if not primera.startswith(f"<!-- {marca}:inicio ") or not primera.endswith(" -->"):
        raise Rechazo(f"el fragmento no empieza por <!-- {marca}:inicio HUELLA -->")
    if not t.endswith(f"<!-- {marca}:fin -->"):
        raise Rechazo(f"el fragmento no acaba en <!-- {marca}:fin -->")
    if t.count(f"<!-- {marca}:inicio") != 1 or t.count(f"<!-- {marca}:fin -->") != 1:
        raise Rechazo("el fragmento lleva sus marcas más de una vez")
    if not minimo <= len(t) <= MAXIMO:
        raise Rechazo(f"el fragmento tiene {len(t)} caracteres (mínimo {minimo}, máximo {MAXIMO})")
    return t


def sustituir(raw: str, fragmento: str, marca: str) -> str | None:
    """Contenido nuevo de la página, o None si ya lleva la huella del fragmento. Solo cambia lo que hay entre las marcas."""
    inicio, fin = f"<!-- {marca}:inicio", f"<!-- {marca}:fin -->"
    if raw.count(inicio) != 1 or raw.count(fin) != 1:
        raise Rechazo(f"la página lleva {raw.count(inicio)} marcas de inicio y {raw.count(fin)} de fin (tiene que llevar una de cada)")
    i, j = raw.index(inicio), raw.index(fin)
    if j < i:
        raise Rechazo("en la página, la marca de fin va antes que la de inicio")
    if fragmento.split("\n", 1)[0] in raw:
        return None
    return raw[:i] + fragmento + raw[j + len(fin):]


class WordPress:
    def __init__(self, base: str, usuario: str, clave: str, sesion=None, dormir=time.sleep):
        self.base = base.rstrip("/") + "/wp-json/wp/v2"
        self.s = sesion or requests.Session()
        self.s.auth = (usuario, clave)
        self.s.headers.update({"User-Agent": "El Especulador, colectores de Datos (smpro-datos-1)"})
        self.dormir = dormir

    def _pedir(self, metodo: str, ruta: str, **kw) -> dict:
        ultimo = None
        for intento in range(len(ESPERAS) + 1):
            try:
                r = self.s.request(metodo, self.base + ruta, timeout=(15, 60), **kw)
                if r.status_code == 200:
                    return r.json()
                ultimo = f"HTTP {r.status_code}: {r.text[:200]!r}"
                if r.status_code in (400, 401, 403, 404):
                    break  # no se arregla reintentando
            except (requests.RequestException, ValueError) as e:
                ultimo = str(e)[:200]
            if intento < len(ESPERAS):
                self.dormir(ESPERAS[intento])
        raise RuntimeError(f"{metodo} {ruta}: {ultimo}")

    def puede_html(self) -> bool:
        yo = self._pedir("GET", "/users/me", params={"context": "edit", "_fields": "id,capabilities"})
        return bool((yo.get("capabilities") or {}).get("unfiltered_html"))

    def leer(self, pagina: int) -> dict:
        return self._pedir("GET", f"/pages/{pagina}", params={"context": "edit", "_fields": "id,status,content,modified"})

    def guardar(self, pagina: int, contenido: str) -> dict:
        return self._pedir("POST", f"/pages/{pagina}", params={"context": "edit", "_fields": "id,status,content,modified"},
                           json={"content": contenido})


def escribir(colector: str, entorno: dict, wp: WordPress | None = None, paginas: dict | None = None) -> tuple[int, dict]:
    paginas = cargar_paginas() if paginas is None else paginas
    estado = {"colector": colector, "momento": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if colector not in paginas:
        return NO_TOCA, {**estado, "resultado": "sin_pagina"}
    p = paginas[colector]
    estado.update({"pagina": p["pagina"], "marca": p["marca"]})
    solo = {c.strip() for c in entorno.get("ESPEC_WP_SOLO", "").split(",") if c.strip()}
    if entorno.get("ESPEC_WP_ESCRIBIR") != "1" or not entorno.get("ESPEC_WP_USUARIO") or not entorno.get("ESPEC_WP_CLAVE"):
        return NO_TOCA, {**estado, "resultado": "desactivada"}
    if solo and colector not in solo:
        return NO_TOCA, {**estado, "resultado": "fuera_de_ESPEC_WP_SOLO"}
    ruta = Path(entorno["ESPEC_DATOS_DIR"]) / colector / "fragmento-wp.html"
    if not ruta.exists():
        raise Rechazo(f"no existe {ruta}")
    fragmento = validar_fragmento(ruta.read_text(encoding="utf-8"), p["marca"], p["minimo"])
    estado["huella"] = fragmento.split("\n", 1)[0]
    wp = wp or WordPress(entorno.get("ESPEC_WP_URL", "https://elespeculador.com"), entorno["ESPEC_WP_USUARIO"], entorno["ESPEC_WP_CLAVE"])
    pag = wp.leer(p["pagina"])
    if pag.get("status") == "trash" or pag.get("id") != p["pagina"]:
        raise Rechazo(f"la página {p['pagina']} no está disponible (estado {pag.get('status')!r})")
    raw = (pag.get("content") or {}).get("raw")
    if raw is None:
        raise Rechazo("WordPress no devuelve el contenido en bruto (¿usuario sin permiso de edición?)")
    nuevo = sustituir(raw, fragmento, p["marca"])
    if nuevo is None:
        return 0, {**estado, "resultado": "al_dia", "estado_pagina": pag.get("status")}
    if not wp.puede_html():
        raise Rechazo("el usuario de WordPress no tiene unfiltered_html: WordPress quitaría los gráficos y el JSON-LD")
    guardada = wp.guardar(p["pagina"], nuevo)
    if (guardada.get("content") or {}).get("raw") != nuevo:
        try:
            wp.guardar(p["pagina"], raw)
            vuelta = "devuelta a como estaba"
        except RuntimeError as e:
            vuelta = f"NO se ha podido devolver a como estaba ({e}); revisarla a mano o con sus revisiones de WordPress"
        raise Rechazo(f"WordPress no ha guardado exactamente lo enviado; página {vuelta}")
    return 0, {**estado, "resultado": "escrita", "estado_pagina": guardada.get("status"), "caracteres": len(nuevo)}


def guardar_estado(entorno: dict, colector: str, estado: dict) -> None:
    carpeta = Path(entorno.get("ESPEC_DATOS_DIR", ".")) / "estado"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        tmp = carpeta / f".{colector}-web.json.tmp"
        tmp.write_text(json.dumps(estado, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, carpeta / f"{colector}-web.json")
    except OSError as e:
        print(f"AVISO  no se pudo escribir el estado web de {colector}: {e}")


def main(argv: list[str] | None = None, entorno: dict | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    entorno = dict(os.environ) if entorno is None else entorno
    if len(argv) != 1:
        print("Uso: servidor/escribir_wp.py <colector>")
        return 2
    colector = argv[0]
    try:
        codigo, estado = escribir(colector, entorno)
    except (Rechazo, RuntimeError, OSError, ValueError, KeyError) as e:
        estado = {"colector": colector, "momento": datetime.now(timezone.utc).isoformat(timespec="seconds"), "resultado": "fallo",
                  "motivo": str(e)[:300]}
        guardar_estado(entorno, colector, estado)
        print(f"ERROR  escritura en WordPress de {colector}: {e}")
        return 1
    if codigo != NO_TOCA:  # apagada o sin página: no deja estado (nada que vigilar)
        guardar_estado(entorno, colector, estado)
    print(f"web    {colector}: {estado['resultado']}" + (f" (página {estado['pagina']})" if "pagina" in estado else ""))
    return codigo


if __name__ == "__main__":
    sys.exit(main())
