"""Comprobaciones sin red del colector de accionistas (indicador 13): solo personas jurídicas.

  python accionistas/pruebas_accionistas.py

El clasificador por la forma del nombre, el filtro que cuenta y descarta a las personas físicas, la frase por
empresa, la huella y la escritura (el CSV y el JSON no llevan ninguna persona física).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import duenos as d  # noqa: E402

FALLOS: list[str] = []
N = 0


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


JURIDICAS = ["BLACKROCK INC.", "TUSSEN DE GRACHTEN BV", "WIT EUROPESE INVESTERING, BV", "ACCIONA, S.A.", "ARCONAS INTERNATIONAL LTD",
             "CORPORACION FINANCIERA ALBA, S.A.", "FUNDACIO PRIVADA DANIEL BRAVO ANDREU", "INDUSTRIAL DEVELOPMENT CORPORATION (I.D.C.)",
             "THE GOLDMAN SACHS GROUP, INC.", "ACCION CONCERTADA", "CRITERIA CAIXA, S.A.U.", "FUNDACION BANCARIA CAIXA D ESTALVIS I PENSIONS DE BARCELONA",
             "ENAIRE", "FIDELITY INTERNATIONAL LIMITED", "THE CHILDREN'S INVESTMENT MASTER FUND", "NORGES BANK", "QATAR INVESTMENT AUTHORITY",
             "PONTEGADEA INVERSIONES, S.L.", "SOCIEDAD ESTATAL DE PARTICIPACIONES INDUSTRIALES (SEPI)", "AMUNDI", "T. ROWE PRICE ASSOCIATES, INC.",
             "KUTXABANK, S.A.", "CAPITAL RESEARCH AND MANAGEMENT COMPANY", "MUTUA MADRILEÑA AUTOMOVILISTA", "STATE STREET CORPORATION",
             "GOBIERNO DE NORUEGA", "ELLIOTT", "BANK OF AMERICA CORPORATION", "MELIA, S.A.", "UBS GROUP AG", "DODGE & COX", "FROB", "SONATRACH"]
FISICAS = ["PEREZ RODRIGUEZ, FLORENTINO", "FERGUSON , SCOTT DAVID", "HOHN , CHRISTOPHER ANTHONY", "ORTEGA GAONA , AMANCIO", "KING , JOHN",
           "DEL PINO Y CALVO-SOTELO , RAFAEL", "GRIFOLS ROURA , VICTOR", "MARTINEZ SAMPEDRO , FERNANDO", "ESCRIBANO , ANGEL", "GARCIA , MARIA",
           "SANTANDER", "JUAN ROIG ALFONSO", "ANDERSEN , MARC P.", "COHEN , STEVE A."]


def prueba_clasificador():
    for n in JURIDICAS:
        ok(d.persona_juridica(n), f"jurídica no reconocida: {n}")
    for n in FISICAS:
        if n == "SANTANDER":
            continue
        ok(not d.persona_juridica(n), f"persona física tomada por jurídica: {n}")
    ok(d.persona_juridica("BANCO SANTANDER, S.A.") and not d.persona_juridica("SANTANDER , ANA"), "palabras enteras: Santander como banco sí, como apellido no")
    ok(not d.persona_juridica("KING , JOHN"), "ING no vale dentro de KING")


def datos_simulados() -> dict:
    fila = lambda nombre, a, b, fecha: {"accionista": nombre, "acciones": a, "directo": a, "indirecto": 0.0, "instrumentos": b, "total": round(a + b, 3), "fecha": fecha, "info": ""}  # noqa: E731
    return {"empresas": [
        {"isin": "ES0167050915", "empresa": "ACS", "nombre_cnmv": "ACS, ACTIVIDADES DE CONSTRUCCION Y SERVICIOS, S.A.", "fuera": False, "consulta": "2026-11-18",
         "accionistas": [fila("ACCION CONCERTADA", 4.774, 0.0, "2026-05-21"), fila("BLACKROCK INC.", 4.641, 0.416, "2025-07-04"),
                         fila("CRITERIA CAIXA, S.A.U.", 10.648, 0.0, "2026-05-21"), fila("PEREZ RODRIGUEZ, FLORENTINO", 15.015, 0.0, "2026-08-10")],
         "derechos_voto": 277097885, "fecha_derechos_voto": "2026-07-16"},
        {"isin": "ES0148396007", "empresa": "Inditex", "nombre_cnmv": "INDUSTRIA DE DISEÑO TEXTIL, S.A.", "fuera": False, "consulta": "2026-11-18",
         "accionistas": [fila("PONTEGADEA INVERSIONES, S.L.", 50.01, 0.0, "2015-01-01"), fila("ORTEGA GAONA , AMANCIO", 59.29, 0.0, "2015-01-01"),
                         fila("BLACKROCK INC.", 2.3, 0.1, "2026-01-01")],
         "derechos_voto": 3116652000, "fecha_derechos_voto": "2015-01-01"},
        {"isin": "ES0105777017", "empresa": "Puig", "nombre_cnmv": "PUIG BRANDS, S.A.", "fuera": False, "consulta": "2026-11-18",
         "accionistas": [fila("PUIG GUASCH , MARC", 1.5, 0.0, "2024-05-03")], "derechos_voto": 100, "fecha_derechos_voto": "2024-05-03"},
        {"isin": "NL0015001FS8", "empresa": "Ferrovial", "fuera": True, "pais": "Países Bajos", "supervisor": "la AFM, el supervisor neerlandés"},
    ]}


def prueba_filtro_y_escritura():
    datos = d.solo_juridicas(datos_simulados())
    acs, ind, puig = datos["empresas"][0], datos["empresas"][1], datos["empresas"][2]
    ok([f["accionista"] for f in acs["accionistas"]] == ["ACCION CONCERTADA", "BLACKROCK INC.", "CRITERIA CAIXA, S.A.U."] and acs["fisicas_excluidas"] == 1, f"filtro ACS: {acs}")
    ok([f["accionista"] for f in ind["accionistas"]] == ["PONTEGADEA INVERSIONES, S.L.", "BLACKROCK INC."] and ind["fisicas_excluidas"] == 1, "filtro Inditex")
    ok(ind["accionistas"] and d.principal(ind)[0]["accionista"] == "PONTEGADEA INVERSIONES, S.L.", "principal: la mayor jurídica")
    ok(puig["accionistas"] == [] and puig["fisicas_excluidas"] == 1, "filtro Puig: vacía")
    ok("fisicas_excluidas" not in datos["empresas"][3], "las de fuera no se tocan")
    frase = d.frase_empresa(acs)
    ok("participación de una persona física, que no se muestra aquí" in frase and "PEREZ" not in frase, f"frase ACS: {frase}")
    ok("no recoge participaciones significativas de personas jurídicas; las 1 que recoge son de personas físicas" in d.frase_empresa(puig), f"frase Puig: {d.frase_empresa(puig)}")
    raiz = Path(tempfile.mkdtemp())
    cambia = d.escribir(datos, "2026-11-19", raiz)
    ok(cambia, "escribir: primera vez")
    for nombre in ("fragmento-wp.html", "index.html", "datos/ultima.json", "datos/accionistas.csv"):
        texto = (raiz / nombre).read_text(encoding="utf-8")
        ok(not any(x in texto for x in ("PEREZ RODRIGUEZ", "ORTEGA GAONA", "PUIG GUASCH")), f"{nombre}: sin personas físicas")
    frag = (raiz / "fragmento-wp.html").read_text(encoding="utf-8")
    ok("Solo personas jurídicas" in frag and "las 3 participaciones de personas físicas del registro se cuentan" in frag, "fragmento: aviso de cabecera")
    ok("no se publican, por decisión editorial" in frag, "fragmento: pie")
    h1 = d.huella(datos, "2026-11-19")
    datos2 = d.solo_juridicas(datos_simulados())
    datos2["empresas"][0]["fisicas_excluidas"] = 2
    ok(h1 != d.huella(datos2, "2026-11-19") and h1 == d.huella(d.solo_juridicas(datos_simulados()), "2026-11-19"), "huella: cuenta las excluidas y es estable")
    j = json.loads((raiz / "datos" / "ultima.json").read_text(encoding="utf-8"))
    ok(j["empresas"][0]["fisicas_excluidas"] == 1 and len(j["empresas"][0]["accionistas"]) == 3, "JSON: cuenta sin nombres")


if __name__ == "__main__":
    prueba_clasificador()
    prueba_filtro_y_escritura()
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
