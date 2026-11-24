"""Comprobaciones sin red del colector de OPAs desde el registro de la CNMV (indicador 11, segunda parte).

  python ofertas/pruebas_ofertas.py

Usa páginas reales de la CNMV del 22/11/2026, recortadas a la parte con datos (`ofertas/pruebas_ofertas/`): el listado de
OPAs presentadas y autorizadas de 2025-2026 y las fichas (datos generales y resultado) de Ercros (431, positiva), Banco
Sabadell (426, negativa, canje), CIE Automotive (424, parcial sobre sí misma) y Corporación Financiera Alba (421, con una
persona física entre los oferentes, cuyo nombre se ha sustituido en la copia por uno ficticio), más Applus (413: precio
modificado y desistimiento que solo consta en las observaciones). Más casos simulados: OPA en plazo, autorizada sin empezar, plazo terminado sin
resultado, desistida, prorrateo; prioridades de lectura, memoria, huella, escritura, paradas y un caso de control con pandas.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ofertas as of

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 22)
FIJ = AQUI / "pruebas_ofertas"


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def pagina(nombre: str) -> str:
    return (FIJ / nombre).read_text(encoding="utf-8")


def bajar_fijo(url: str, sesion=None) -> str:
    """Sustituye a la red: sirve las páginas guardadas; las que no están, como si la CNMV no respondiera."""
    if "ListaOPAS" in url:
        return pagina("lista_2025_2026.html")
    n = url.split("numReg=")[1].split("&")[0]
    v = url.split("vista=")[1]
    ruta = FIJ / f"opa_{n}_v{v}.html"
    if not ruta.exists():
        raise of.DatosRaros(f"la CNMV no responde (prueba, OPA {n})")
    return ruta.read_text(encoding="utf-8")


def simulada(numreg: str, **k) -> dict:
    base = {"numreg": numreg, "sociedad": "SOCIEDAD SIMULADA, S.A.", "nif": "", "isin": "", "oferentes": "OFERENTE SIMULADO, S.L.",
            "personas_fisicas": 0, "tipo": "Total", "contraprestacion": "10,00 € por acción", "precio_eur": 10.0,
            "valores_afectados_pct": 100.0, "volumen_eur": 1.0e8, "fecha_presentacion": "2026-08-01", "fecha_autorizacion": None,
            "inicio_plazo": None, "fin_plazo": None, "fin_prorroga": None, "fecha_desistimiento": None, "resultado": "",
            "fecha_resultado": None, "aceptacion_pct": None, "prorrateo_pct": None, "observaciones": "",
            "enlace": of.URL_FICHA.format(n=numreg, v=0), "leido": "2026-11-21T08:00:00+00:00", "lector": of.LECTOR,
            "modificada": False, "contraprestacion_inicial": ""}
    base.update(k)
    return base


def main() -> None:
    # ---------------------------------------------------------------- listado
    pres, aut = of.leer_lista(pagina("lista_2025_2026.html"))
    ok([(p["sociedad"], p["fecha_presentacion"], p["oferentes"]) for p in pres]
       == [("AEDAS HOMES, S.A.", "2026-11-17", "NEINOR DMP BIDCO, S.A.U."), ("AZKOYEN, S.A.", "2026-08-24", "OHMNIA ELECTRONICS, S.L.")],
       f"listado: dos OPAs presentadas y pendientes de autorización ({pres})")
    ok([a["numreg"] for a in aut] == ["431", "430", "429", "428", "427", "426", "425", "424", "423", "422", "421"],
       "listado: once OPAs autorizadas desde 2025, del 431 al 421")
    try:
        of.leer_lista("<html><body>Aviso de cookies</body></html>")
        ok(False, "un listado sin la tabla de autorizadas debe parar")
    except of.DatosRaros:
        ok(True, "listado sin tabla: DatosRaros")

    # ---------------------------------------------------------------- fichas reales
    e = of.leer_ficha("431", pagina("opa_431_v0.html"), pagina("opa_431_v2.html"))
    ok((e["sociedad"], e["oferentes"], e["tipo"], e["contraprestacion"], e["precio_eur"], e["volumen_eur"])
       == ("ERCROS, S.A.", "BONDALTI IBERICA, S.L.U.", "Total", "3,510 € por acción", 3.51, 72796069.81),
       f"Ercros 431: datos generales ({e})")
    ok((e["fecha_presentacion"], e["fecha_autorizacion"], e["inicio_plazo"], e["fin_plazo"], e["fin_prorroga"], e["fecha_desistimiento"])
       == ("2026-07-01", "2026-07-22", "2026-07-24", "2026-09-10", None, None), "Ercros 431: calendario, «No tiene» es vacío")
    ok((e["resultado"], e["fecha_resultado"], e["aceptacion_pct"], e["isin"]) == ("Positivo", "2026-09-17", 37.86, "ES0125140A14"),
       "Ercros 431: resultado positivo, 37,86 % aceptado, publicado el 17/09/2026")
    s = of.leer_ficha("426", pagina("opa_426_v0.html"), pagina("opa_426_v2.html"))
    ok(s["contraprestacion"] == "" and s["precio_eur"] is None and s["fin_prorroga"] == "2025-10-10"
       and (s["resultado"], s["aceptacion_pct"]) == ("Negativo", 25.33) and "4,8376 acciones de Banco de Sabadell" in s["observaciones"],
       "Sabadell 426: canje («*»), prórroga hasta el 10/10/2025, resultado negativo con el 25,33 % y observaciones")
    c = of.leer_ficha("424", pagina("opa_424_v0.html"), pagina("opa_424_v2.html"))
    ok((c["tipo"], c["contraprestacion"], c["oferentes"], c["aceptacion_pct"]) == ("Parcial", "24,000 € por acción", "CIE AUTOMOTIVE, S.A.", 9.82),
       "CIE 424: OPA parcial sobre sí misma")
    a = of.leer_ficha("421", pagina("opa_421_v0.html"), pagina("opa_421_v2.html"))
    ok(a["oferentes"] == "CORPORACION FINANCIERA ALBA, S.A. | SON DAVIÚ, S.L.U" and a["personas_fisicas"] == 1,
       "Alba 421: la persona física entre los oferentes no se guarda, solo se cuenta")
    ap = of.leer_ficha("413", pagina("opa_413_v0.html"), pagina("opa_413_v2.html"))
    ok((ap["contraprestacion"], ap["precio_eur"], ap["modificada"], ap["contraprestacion_inicial"], ap["resultado"])
       == ("10,650 € por acción", 10.65, True, "9,500 € por acción", ""), "Applus 413: vale el precio de la última modificación y se guarda el inicial")
    ok(of.situacion(ap, HOY) == ("desistida", "Desistida (consta en las observaciones de la CNMV)"),
       "Applus 413: el desistimiento que solo está en las observaciones cuenta, con el plazo terminado")
    ok(s["modificada"] and s["contraprestacion"] == "" and s["contraprestacion_inicial"] == "", "Sabadell 426: modificada, canje antes y después")
    ok(all(of.es_entidad(n) for n in ("HOCHTIEF AKTIENGESELLSCHAFT", "VALDIM", "L´UNION ET COMPAGNIE", "SEC GOULET TURPIN",
                                       "QUARENTA MAIS QUATRO, SGPS, LDA.", "MANZANA SPAIN BIDCO, S.L.U."))
       and not any(of.es_entidad(n) for n in ("APELLIDOUNO APELLIDODOS NOMBRE", "GARCIA PEREZ, JUAN", "ANA MARIA LOPEZ RUIZ")),
       "oferentes: sociedades alemanas, francesas, portuguesas y de una palabra son entidades; los nombres de persona, no")
    try:
        of.leer_ficha("430", pagina("opa_431_v0.html"), pagina("opa_431_v2.html"))
        ok(False, "una ficha de otro número debe parar")
    except of.DatosRaros:
        ok(True, "ficha con otro número de registro: DatosRaros")
    ok(of._precio("*") == ("", None) and of._precio("1.234,5 Euros por acción") == ("1.234,5 € por acción", 1234.5)
       and of._precio("Canje: 1 acción nueva por cada 2") == ("Canje: 1 acción nueva por cada 2", None), "contraprestación: precio, «*» y canje")

    # ---------------------------------------------------------------- situación
    casos = {
        "positivo": simulada("1", resultado="Positivo", fecha_resultado="2026-10-01"),
        "negativo": simulada("2", resultado="Negativo", fecha_resultado="2026-10-01"),
        "desistida": simulada("3", fecha_autorizacion="2026-09-01", inicio_plazo="2026-09-03", fin_plazo="2026-10-01",
                              fecha_desistimiento="2026-09-20"),
        "en_plazo": simulada("4", fecha_autorizacion="2026-11-10", inicio_plazo="2026-11-12", fin_plazo="2026-11-22"),
        "autorizada": simulada("5", fecha_autorizacion="2026-11-20", inicio_plazo="2026-11-25", fin_plazo="2026-12-20"),
        "pendiente": simulada("6", fecha_autorizacion="2026-10-01", inicio_plazo="2026-10-03", fin_plazo="2026-11-02",
                              fin_prorroga="2026-11-16"),
        "sin_dato": simulada("7"),
        "sin_resultado": simulada("8", fecha_autorizacion="2015-05-26", inicio_plazo="2015-05-28", fin_plazo="2015-06-24"),
    }
    vistas = {k: of.situacion(o, HOY) for k, o in casos.items()}
    ok(all(vistas[k][0] == k for k in casos), f"situación de cada caso ({vistas})")
    ok(vistas["en_plazo"][1] == "En plazo de aceptación hasta el 22/11/2026" and vistas["pendiente"][1]
       == "Plazo terminado el 16/11/2026; resultado pendiente" and vistas["desistida"][1] == "Desistida el 20/09/2026",
       "situación: el último día del plazo cuenta, la prórroga manda sobre el plazo, desistimiento con fecha")
    ok(vistas["sin_resultado"][1] == "Sin resultado en el registro de la CNMV"
       and of.situacion(dict(casos["pendiente"], fin_prorroga=None, fin_plazo="2026-10-23"), HOY)[0] == "pendiente"
       and of.situacion(dict(casos["pendiente"], fin_prorroga=None, fin_plazo="2026-10-22"), HOY)[0] == "sin_resultado",
       "sin resultado 30 días después del plazo: no está pendiente, el registro no lo tiene (OPAs antiguas)")
    ok(of.situacion(dict(casos["en_plazo"], observaciones="La oferente comunicó su desistimiento de la oferta anterior."), HOY)[0] == "en_plazo",
       "una OPA en plazo no pasa a desistida por lo que digan las observaciones")

    # ---------------------------------------------------------------- qué se pide en cada pasada
    memoria = {"431": dict(e, leido="2026-11-21T08:00:00+00:00", lector=of.LECTOR),
               "430": simulada("430", resultado="Positivo", fecha_resultado="2026-03-20"),
               "429": simulada("429", fecha_autorizacion="2026-11-10", inicio_plazo="2026-11-12", fin_plazo="2026-12-10"),
               "426": dict(s, leido="2026-11-21T08:00:00+00:00", lector=of.LECTOR)}
    autorizadas = [{"numreg": n, "sociedad": ""} for n in ("431", "430", "429", "428", "427", "426", "425")]
    ok(of.por_leer(autorizadas, memoria, HOY, 10) == ["429", "428", "427", "425"],
       "por leer: primero las abiertas, luego las nuevas de la más reciente a la más antigua; las cerradas hace tiempo, no")
    memoria["431"]["fecha_resultado"] = "2026-11-10"
    ok(of.por_leer(autorizadas, memoria, HOY, 10) == ["429", "428", "427", "425", "431"] and of.por_leer(autorizadas, memoria, HOY, 2) == ["429", "428"],
       "por leer: una resuelta hace menos de 45 días se relee una vez al día; el máximo por pasada se respeta")
    memoria["431"]["fecha_resultado"] = "2026-09-17"
    memoria["426"]["lector"] = "2026-11-22a"
    ok(of.por_leer(autorizadas, memoria, HOY, 10) == ["429", "428", "427", "425", "426"],
       "por leer: si cambia el lector, las fichas leídas con el anterior se releen, al final de la cola")
    memoria["426"]["lector"] = of.LECTOR

    # ---------------------------------------------------------------- una pasada con las páginas guardadas
    of.AVISOS.clear()
    mem, pres2, total = of.actualizar(HOY, {}, maximo=60, pausa=0, bajar=bajar_fijo)
    ok(sorted(mem) == ["421", "424", "426", "431"] and total == 11 and len(pres2) == 2,
       f"pasada: lee las cuatro fichas guardadas de las once del registro ({sorted(mem)})")
    ok(len(of.AVISOS) == 7 and all("no responde" in x for x in of.AVISOS), "pasada: las siete que no responden quedan en avisos para la siguiente")
    of.AVISOS.clear()

    def todo_falla(url: str, sesion=None) -> str:
        if "ListaOPAS" in url:
            return pagina("lista_2025_2026.html")
        raise of.DatosRaros("la CNMV no responde (prueba)")
    try:
        of.actualizar(HOY, {}, maximo=60, pausa=0, bajar=todo_falla)
        ok(False, "si no se lee ninguna ficha de varias pedidas, debe parar")
    except of.DatosRaros:
        ok(True, "ninguna ficha leída de varias pedidas: DatosRaros (incidencia en el servidor)")
    of.AVISOS.clear()

    # ---------------------------------------------------------------- cálculo y textos con el histórico en carga
    res = of.calcular(mem, pres2, total, HOY)
    res["huella"] = of.huella(res)
    ok(res["ultima_resuelta"]["numreg"] == "431" and not res["en_marcha"] and not res["cobertura"]["completa"]
       and res["por_anio"] == [] and res["cobertura"]["personas_fisicas_excluidas"] == 1,
       "cálculo: la última resuelta es Ercros; histórico en carga, sin tabla por años; una persona física excluida")
    f = of.fragmento(res, "2026-11-22")
    ok(f.startswith(f"<!-- opas:inicio {res['huella']} -->") and f.rstrip().endswith("<!-- opas:fin -->"), "fragmento: marcas de la página 8588")
    ok("Hay <strong>2 OPAs en marcha</strong> sobre sociedades cotizadas en España según el registro de la CNMV: 2 presentadas y pendientes de "
       "autorización (AEDAS HOMES, S.A., AZKOYEN, S.A.)." in f
       and "La última con resultado es la de BONDALTI IBERICA, S.L.U. sobre ERCROS, S.A.: positivo, con el 37,86 % de los valores a los que se "
           "dirigía (resultado publicado el 17/09/2026)." in f, "fragmento: frase del día")
    ok("Histórico en carga: 4 de 11 OPAs del registro leídas" in f and "<h2>OPAs por año</h2>" not in f, "fragmento: aviso de histórico en carga")
    ok("<td>La propia sociedad</td>" in f and "CORPORACION FINANCIERA ALBA, S.A. · SON DAVIÚ, S.L.U y 1 persona física" in f
       and "APELLIDOUNO" not in f, "fragmento: «La propia sociedad» y la persona física sin nombre")
    ok('<a href="https://www.cnmv.es/portal/Consultas/Folletos/opa.aspx?numReg=426&amp;vista=0">ver la ficha de la CNMV</a>' in f
       and "<td>3,510 € por acción</td>" in f and "<td>25,33 %</td>" in f and "08/09/2025 – 10/10/2025" in f,
       "fragmento: canje a la ficha, precio, aceptación y plazo con la prórroga")
    bajo = f.lower()
    ok("$" not in f and not any(p in bajo for p in ("datos de bme", "fuente: bme", "bolsasymercados", "yahoo", "cotiza a", "recomendamos", "le conviene", "conviene acudir"))
       and "no es asesoramiento financiero" in f and '<script type="application/ld+json">' in f and len(f) > 3000,
       "fragmento: sin BME ni recomendaciones, con aviso, JSON-LD y más de 3.000 caracteres")

    # ---------------------------------------------------------------- histórico completo y caso de control con pandas
    completa = dict(mem)
    for o in casos.values():
        completa[f"9{o['numreg']}"] = dict(o, numreg=f"9{o['numreg']}", fecha_autorizacion=o.get("fecha_autorizacion") or "2024-05-05")
    completa["9500"] = simulada("9500", fecha_autorizacion="2025-02-01", inicio_plazo="2025-02-03", fin_plazo="2025-02-20",
                                resultado="Positivo", fecha_resultado="2025-02-27", aceptacion_pct=951.71, tipo="Parcial")
    res2 = of.calcular(completa, [], len(completa), HOY)
    res2["huella"] = of.huella(res2)
    df = pd.DataFrame(res2["todas"])
    control = df.groupby("anio")["situacion"].value_counts().unstack(fill_value=0)
    propio = {a["anio"]: a for a in res2["por_anio"]}
    ok(res2["cobertura"]["completa"] and all(
        propio[y]["autorizadas"] == int(control.loc[y].sum()) and propio[y]["positivas"] == int(control.loc[y].get("positivo", 0))
        and propio[y]["negativas"] == int(control.loc[y].get("negativo", 0)) and propio[y]["desistidas"] == int(control.loc[y].get("desistida", 0))
        for y in control.index if y), "control con pandas: recuento por año y resultado")
    ok([o["numreg"] for o in res2["en_marcha"]] == ["96", "95", "94"], "en marcha: autorizada sin empezar, en plazo y plazo terminado sin resultado")
    f2 = of.fragmento(res2, "2026-11-22")
    ok(of._contra_txt(simulada("1", contraprestacion="49.75 (*)")) == ('49,75 (<a href="https://www.cnmv.es/portal/Consultas/Folletos/opa.aspx?numReg=1&amp;vista=0">'
                                                                       "condiciones en la ficha de la CNMV</a>)")
       and "ver la ficha de la CNMV" in of._contra_txt(simulada("2", contraprestacion="Ver observaciones generales"))
       and of._contra_txt(simulada("3", contraprestacion="18,360 € por acción", contraprestacion_inicial="Ver observaciones generales"))
       == "18,360 € por acción (modificada)", "contraprestación: «(*)», «Ver observaciones generales» y modificada sin precio inicial")
    ok([of._coma_decimal(x) for x in ("49.75", "3.5", "12.3456", "1.234", "3,510 € por acción", "*", "", " 49.75 ")]
       == ["49,75", "3,5", "12,3456", "1.234", "3,510 € por acción", "*", "", "49,75"],
       "coma decimal: número suelto con punto (no los de tres cifras, que pueden ser miles) y el resto sin tocar")
    ok(of._contra_txt(simulada("4", contraprestacion="49.75")) == "49,75", "contraprestación numérica sin «(*)»: coma decimal")
    ok("<h2>OPAs por año</h2>" in f2 and "Histórico en carga" not in f2 and "951,71 % (oferta parcial sobresuscrita: hubo prorrateo)" in f2
       and "Plazo terminado el 16/11/2026; resultado pendiente" in f2, "fragmento con el histórico completo: años, prorrateo y en marcha")
    ok("Hay <strong>3 OPAs en marcha</strong>" in of.frase(res2), "frase: tres en marcha sin presentadas")
    vacia = of.calcular({}, [], 0, HOY)
    ok(of.frase(vacia) == "Ahora mismo no hay ninguna OPA en marcha en el registro de la CNMV.", "frase sin OPAs")

    # ---------------------------------------------------------------- huella
    otra = of.calcular(mem, pres2, total, HOY)
    ok(of.huella(otra) == res["huella"], "huella estable con los mismos datos")
    otra2 = of.calcular(mem, pres2[:1], total, HOY)
    ok(of.huella(otra2) != res["huella"], "la huella cambia si una presentada sale del listado (autorizada o retirada)")
    plazo = {"9": simulada("9", fecha_autorizacion="2026-11-10", inicio_plazo="2026-11-12", fin_plazo="2026-11-21")}
    ok(of.huella(of.calcular(plazo, [], 1, date(2026, 11, 21))) != of.huella(of.calcular(plazo, [], 1, HOY)),
       "la huella cambia cuando termina un plazo de aceptación (en plazo → resultado pendiente)")

    # ---------------------------------------------------------------- escritura y memoria
    with tempfile.TemporaryDirectory() as t:
        salida = Path(t) / "ofertas"
        ok(of.escribir(res, HOY, salida) is True, "primera escritura: datos nuevos")
        ok(all((salida / p).exists() for p in ("fragmento-wp.html", "index.html", "datos/ultima.json", "datos/opas.csv", "datos/presentadas.csv")),
           "escribe fragmento, index, ultima.json, opas.csv y presentadas.csv")
        todo = "".join((salida / p).read_text(encoding="utf-8") for p in ("fragmento-wp.html", "index.html", "datos/ultima.json",
                                                                         "datos/opas.csv", "datos/presentadas.csv"))
        ok("APELLIDOUNO" not in todo, "ningún fichero publicado lleva el nombre de la persona física")
        u = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
        ok(u["huella"] == res["huella"] and u["cobertura"]["registro"] == 11 and u["ultima_resuelta"]["numreg"] == "431"
           and len(u["presentadas"]) == 2, "ultima.json: huella, cobertura, última resuelta y presentadas")
        vuelta = of.cargar(salida / "datos" / "opas.csv")
        ok(sorted(vuelta) == sorted(mem) and vuelta["431"]["aceptacion_pct"] == 37.86 and vuelta["426"]["precio_eur"] is None
           and vuelta["431"]["volumen_eur"] == 72796069.81 and vuelta["421"]["personas_fisicas"] == 1 and vuelta["431"]["fin_prorroga"] is None,
           "la memoria se lee igual que se escribió (números, vacíos y recuentos)")
        ok(of.huella(of.calcular(vuelta, pres2, total, HOY)) == res["huella"], "la huella no cambia al recargar la memoria")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        ok(of.escribir(res, HOY, salida) is False and (salida / "fragmento-wp.html").stat().st_mtime_ns == antes,
           "sin datos nuevos no reescribe lo publicado")
        (salida / "index.html").unlink()
        ok(of.escribir(res, HOY, salida) is False and (salida / "index.html").exists(), "si falta un fichero, lo rehace")
        # línea de órdenes con la red sustituida
        original = of.descargar
        of.descargar = bajar_fijo
        argv = sys.argv
        try:
            sys.argv = ["ofertas.py", "--salida", str(Path(t) / "cli"), "--fecha", "2026-11-22"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = of.main()
            ok(rc == 0 and "2 presentadas pendientes de autorización" in buf.getvalue() and "histórico 4 de 11" in buf.getvalue(),
               f"línea de órdenes: pasada correcta ({buf.getvalue().strip()[:160]})")
            of.descargar = lambda url, sesion=None: "<html>Aviso de cookies</html>" + " " * 2000
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = of.main()
            ok(rc == 1 and "::error::ofertas" in buf.getvalue(), "línea de órdenes: si la CNMV cambia la página, sale con 1 y un error")
        finally:
            of.descargar = original
            sys.argv = argv
            of.AVISOS.clear()

    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")


if __name__ == "__main__":
    main()
