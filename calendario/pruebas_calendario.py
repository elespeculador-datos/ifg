"""Comprobaciones sin red del calendario de dividendos del IBEX 35 (indicador 11).

  python calendario/pruebas_calendario.py

Salidas simuladas del colector cnmv (`cnmv/datos/ibex35.csv` y `dividendos.csv`) con su formato real y casos
conocidos: un dividendo anunciado dos veces (aprobado y ajustado por la autocartera) y un recordatorio sin importe,
fecha ex pasada con el pago pendiente, pago sin fecha ex, pagado hace más y menos de 90 días, flexibles, un
comunicado que ya no es de dividendos, dólares, importe sin leer, dos dividendos distintos con la misma fecha,
títulos con caracteres especiales; huella, escritura, paradas y un caso de control con pandas.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import calendario as cal

FALLOS: list[str] = []
N = 0
HOY = date(2026, 11, 22)
CNMV = "https://www.cnmv.es/Portal/Otra-Informacion-Relevante/Resultado-OIR.aspx?nreg="

# canal, nreg, fecha, isin, empresa, ficha, caja, etiqueta, título
COMUNICADOS = [
    ("OIR", "43348", "2026-10-28T18:00:00", "ES0124244E34", "Mapfre", "mapfre", "dividendos", "Dividendo", "Dividendo a cuenta del ejercicio 2026"),
    ("OIR", "43701", "2026-11-17T09:00:00", "ES0124244E34", "Mapfre", "mapfre", "dividendos", "Dividendo", "Importe definitivo del dividendo a cuenta"),
    ("OIR", "43760", "2026-11-20T09:00:00", "ES0124244E34", "Mapfre", "mapfre", "dividendos", "Dividendo", "Recordatorio del dividendo a cuenta"),
    ("OIR", "43636", "2026-11-12T09:00:00", "ES0105025003", "Merlin Properties", "merlin-properties", "dividendos", "Dividendo", "MERLIN - Dividendo a cuenta 2026"),
    ("OIR", "43452", "2026-11-02T09:00:00", "ES0171996087", "Grifols", "grifols", "dividendos", "Dividendo", "Dividendo a cuenta <2026> & más"),
    ("OIR", "43416", "2026-10-30T09:00:00", "ES0140609019", "CaixaBank", "caixabank", "dividendos", "Dividendo", "Dividendo a cuenta"),
    ("OIR", "41000", "2026-05-20T09:00:00", "ES0113211835", "BBVA", "bbva", "dividendos", "Dividendo", "Dividendo complementario"),
    ("OIR", "43244", "2026-10-21T08:29:27", "ES0144580Y14", "Iberdrola", "iberdrola", "dividendos", "Dividendo flexible", "Iberdrola Retribución Flexible: segunda edición"),
    ("OIR", "41700", "2026-07-01T08:00:00", "ES0144580Y14", "Iberdrola", "iberdrola", "dividendos", "Dividendo flexible", "Iberdrola Retribución Flexible: primera edición"),
    ("OIR", "41900", "2026-09-29T08:00:00", "ES0167050915", "ACS", "acs", "dividendos", "Dividendo flexible", "Modificación del Programa de Recompra por el Scrip Dividend"),
    ("OIR", "43000", "2026-10-01T08:00:00", "ES0173516115", "Repsol", "repsol", "resultados", "Resultados", "Resultados del tercer trimestre y dividendos de la 407ETR"),
    ("OIR", "43100", "2026-11-05T08:00:00", "LU1598757687", "ArcelorMittal", "arcelormittal", "dividendos", "Dividendo", "Interim dividend payment"),
    ("OIR", "43200", "2026-11-10T08:00:00", "ES0130670112", "Endesa", "endesa", "dividendos", "Dividendo", "Dividendo a cuenta"),
    ("OIR", "43300", "2026-11-11T08:00:00", "ES0116870314", "Naturgy", "naturgy", "dividendos", "Dividendo", "Dividendo a cuenta"),
    ("OIR", "43301", "2026-11-11T08:05:00", "ES0116870314", "Naturgy", "naturgy", "dividendos", "Dividendo", "Dividendo extraordinario"),
    ("OIR", "43400", "2026-11-14T08:00:00", "ES0178430E18", "Telefónica", "telefonica", "dividendos", "Dividendo", "Política de retribución"),
]
# canal, nreg, fecha_comunicado, importe, moneda, ex, registro, pago, extracción
LECTURAS = [
    ("OIR", "43348", "2026-10-28", "0.08", "EUR", "2026-11-24", "2026-11-25", "2026-11-26", "completa"),
    ("OIR", "43701", "2026-11-17", "0.080248", "EUR", "2026-11-24", "2026-11-25", "2026-11-26", "completa"),
    ("OIR", "43760", "2026-11-20", "", "", "2026-11-24", "", "2026-11-26", "parcial"),
    ("OIR", "43636", "2026-11-12", "0.2", "EUR", "2026-11-20", "2026-11-23", "2026-12-10", "completa"),
    ("OIR", "43452", "2026-11-02", "0.15", "EUR", "", "", "2026-12-04", "parcial"),
    ("OIR", "43416", "2026-10-30", "0.1844", "EUR", "2026-11-04", "", "2026-11-06", "completa"),
    ("OIR", "41000", "2026-05-20", "0.6", "EUR", "2026-06-01", "", "2026-06-03", "completa"),
    ("OIR", "43244", "2026-10-21", "", "", "", "", "", "flexible: ver comunicado"),
    ("OIR", "41700", "2026-07-01", "", "", "", "", "", "flexible: ver comunicado"),
    ("OIR", "41900", "2026-09-29", "", "", "", "", "", "flexible: ver comunicado"),
    ("OIR", "43000", "2026-10-01", "0.5", "EUR", "2026-12-20", "", "2026-12-22", "completa"),
    ("OIR", "43100", "2026-11-05", "0.15", "USD", "2026-11-30", "2026-12-01", "2026-12-10", "completa"),
    ("OIR", "43200", "2026-11-10", "", "", "2026-12-15", "", "2026-12-17", "parcial"),
    ("OIR", "43300", "2026-11-11", "0.3", "EUR", "2026-12-01", "", "2026-12-03", "completa"),
    ("OIR", "43301", "2026-11-11", "0.5", "EUR", "2026-12-01", "", "2026-12-03", "completa"),
    ("OIR", "43400", "2026-11-14", "", "", "", "", "", "sin datos"),
]


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print(f"FALLO  {texto}")


def preparar(raiz: Path, comunicados=COMUNICADOS, lecturas=LECTURAS) -> Path:
    base = raiz / "cnmv" / "datos"
    base.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"canal": c, "nreg": n, "fecha": f, "emisor": e.upper(), "categoria": "Otra información relevante", "texto": t,
                   "enlace": CNMV + n, "isin": i, "empresa": e, "ficha": fi, "caja": cj, "etiqueta": et, "periodo": "", "grupo": f"g{n}"}
                  for c, n, f, i, e, fi, cj, et, t in comunicados]).to_csv(base / "ibex35.csv", index=False)
    emp = {n: (i, e, et) for c, n, f, i, e, fi, cj, et, t in comunicados}
    pd.DataFrame([{"canal": c, "nreg": n, "fecha_comunicado": f, "isin": emp[n][0], "empresa": emp[n][1], "tipo": emp[n][2],
                   "importe_bruto": imp, "moneda": mon, "fecha_ex": ex, "fecha_registro": reg, "fecha_pago": pago, "extraccion": extr,
                   "intentos": "1", "enlace": CNMV + n, "lector": "2026-11-22d"}
                  for c, n, f, imp, mon, ex, reg, pago, extr in lecturas]).to_csv(base / "dividendos.csv", index=False)
    return raiz


def main() -> None:
    with tempfile.TemporaryDirectory() as t:
        raiz = preparar(Path(t) / "datos")
        divs, hasta = cal.leer(raiz)
        ok(hasta == "2026-11-20", f"fecha del último comunicado de dividendo ({hasta})")
        ok(not any(d["nreg"] == "43000" for d in divs), "un comunicado que el colector ya no clasifica como dividendo no entra")
        ok(cal.concepto("Dividendo a cuenta 2026") == "a cuenta" and cal.concepto("Dividendo Complementario de 2025 de IAG") == "complementario"
           and cal.concepto("Pago del dividendo extraordinario") == "extraordinario" and cal.concepto("dividendo final de 0,05 €") == "complementario"
           and cal.concepto("Información sobre la retribución al accionista") == "", "concepto leído del título")
        res = cal.calcular(divs, HOY, hasta)
        res["huella"] = cal.huella(res)
        prox = [(d["empresa"], d["importe"], d["fecha_ex"], d["fecha_pago"]) for d in res["proximos"]]
        ok(prox == [("Merlin Properties", 0.2, "2026-11-20", "2026-12-10"), ("Mapfre", 0.080248, "2026-11-24", "2026-11-26"),
                    ("ArcelorMittal", 0.15, "2026-11-30", "2026-12-10"), ("Naturgy", 0.3, "2026-12-01", "2026-12-03"),
                    ("Naturgy", 0.5, "2026-12-01", "2026-12-03"), ("Grifols", 0.15, None, "2026-12-04"), ("Endesa", None, "2026-12-15", "2026-12-17")],
           f"próximos: fecha ex pasada con pago pendiente, pago sin fecha ex, dos dividendos distintos el mismo día, orden por fecha ({prox})")
        mapfre = [d for d in res["proximos"] if d["empresa"] == "Mapfre"]
        ok(len(mapfre) == 1 and mapfre[0]["nreg"] == "43701",
           "el mismo dividendo anunciado tres veces sale una vez: el importe ajustado, y el recordatorio sin importe no lo borra")
        ok(res["con_fecha_ex"] == 5 and res["empresas_con_fecha_ex"] == 4, f"recuento con fecha ex de hoy en adelante ({res['con_fecha_ex']}, {res['empresas_con_fecha_ex']})")
        ok([(d["empresa"], d["fecha_pago"]) for d in res["pagados_90d"]] == [("CaixaBank", "2026-11-06")],
           "pagados en 90 días: el de CaixaBank sí, el de BBVA de junio no")
        ok([(d["empresa"], d["nreg"]) for d in res["flexibles"]] == [("Iberdrola", "43244")],
           "flexibles: el último comunicado de cada empresa, y no el de una modificación de la recompra")
        ok(all(d["nreg"] != "43400" for d in res["todos"]), "un comunicado sin fechas no entra en el calendario")
        # caso de control con pandas: los próximos son, de los dividendos fundidos, los de fecha ex o de pago de hoy en adelante
        todos = pd.DataFrame(res["todos"])
        h = HOY.isoformat()
        control = todos[(todos["fecha_ex"].fillna("") >= h) | (todos["fecha_pago"].fillna("") >= h)].copy()
        control["clave"] = control["fecha_ex"].fillna(control["fecha_pago"])
        control = control.sort_values(["clave", "empresa"], kind="stable")
        ok(list(zip(control["empresa"], control["fecha_pago"])) == [(d["empresa"], d["fecha_pago"]) for d in res["proximos"]],
           "control con pandas: mismo conjunto y mismo orden de próximos")
        frag = cal.fragmento(res, h)
        ok(frag.startswith(f"<!-- dividendos:inicio {res['huella']} -->") and frag.rstrip().endswith("<!-- dividendos:fin -->"),
           "marcas de la página 8578 con la huella")
        ok("La próxima fecha ex es el <strong>24/11/2026</strong>: <a href=\"https://elespeculador.com/ibex35/mapfre/\">Mapfre</a> descuenta 0,080248 € brutos por acción, que paga el 26/11/2026." in frag
           and "Hay <strong>5 dividendos</strong> de 4 empresas del IBEX 35" in frag, "frase del día")
        sin_importe = {**res, "proximos": [d for d in res["proximos"] if d["empresa"] == "Endesa"], "con_fecha_ex": 1, "empresas_con_fecha_ex": 1}
        ok(cal.frase(sin_importe) == ("Hay <strong>1 dividendo</strong> de 1 empresa del IBEX 35 con fecha ex de hoy en adelante. La próxima fecha ex es el "
                                      "<strong>15/12/2026</strong>: <a href=\"https://elespeculador.com/ibex35/endesa/\">Endesa</a> descuenta un dividendo cuyo "
                                      "importe está en el comunicado; lo paga el 17/12/2026."), "frase del día sin importe leído, en singular")
        solo_pago = {**res, "proximos": [d for d in res["proximos"] if d["empresa"] in ("Merlin Properties", "Grifols")], "con_fecha_ex": 0, "empresas_con_fecha_ex": 0}
        ok(cal.frase(solo_pago) == ("Ahora mismo ninguna empresa del IBEX 35 tiene comunicado un dividendo con fecha ex de hoy en adelante. "
                                    "Quedan 2 dividendos pendientes de pago."), "frase del día sin fechas ex por delante")
        ok("20/11/2026 (pasada)" in frag and "<tr><td>—</td>" in frag, "fecha ex pasada marcada; sin fecha ex, raya")
        ok("0,15 USD" in frag and "<td>0,20 €</td>" in frag and "<td>0,50 €</td>" in frag and "<td>0,080248 €</td>" in frag
           and f'<a href="{CNMV}43200">en el comunicado</a>' in frag, "moneda, dos decimales como mínimo y los que haga falta, y enlace si no hay importe")
        ok('href="https://elespeculador.com/ibex35/mapfre/"' in frag and f'href="{CNMV}43701"' in frag, "enlaces a la ficha y al comunicado")
        ok("&lt;2026&gt; &amp; más" in frag and "<2026>" not in frag, "títulos escapados")
        bajo = frag.lower()
        ok("%" not in frag and not any(p in bajo for p in ("precio de cierre", "cotización", "bme", "yahoo", "recomendamos", "le conviene", "conviene comprar")),
           "sin precios de cierre, rentabilidades (ningún porcentaje), BME, Yahoo ni recomendaciones")
        ok("no es asesoramiento financiero ni recomendación de inversión" in frag and "gratuitos en cnmv.es" in frag, "aviso y condición de la CNMV")
        # huella y escritura
        res2 = cal.calcular(cal.leer(raiz)[0], HOY, hasta)
        ok(cal.huella(res2) == res["huella"], "huella estable con los mismos datos")
        res3 = cal.calcular(divs, date(2026, 11, 25), hasta)
        ok(cal.huella(res3) != res["huella"] and not any(d["empresa"] == "Mapfre" for d in res3["proximos"] if (d["fecha_ex"] or "") >= "2026-11-25"),
           "cuando pasa una fecha ex, cambia la huella")
        salida = Path(t) / "datos" / "calendario"
        ok(cal.escribir(res, HOY, salida) is True, "primera escritura")
        ok(cal.escribir(res, HOY, salida) is False, "sin cambios no se reescribe")
        antes = (salida / "fragmento-wp.html").stat().st_mtime_ns
        (salida / "index.html").unlink()
        ok(cal.escribir(res, HOY, salida) is False and (salida / "index.html").exists(), "si falta un fichero, se rehace aunque no haya datos nuevos")
        import time
        time.sleep(0.01)
        cal.escribir(res, HOY, salida, forzar=True)
        ok((salida / "fragmento-wp.html").stat().st_mtime_ns != antes, "--forzar reescribe")
        u = json.loads((salida / "datos" / "ultima.json").read_text(encoding="utf-8"))
        ok(u["huella"] == res["huella"] and u["version"] == cal.VERSION and len(u["proximos"]) == 7 and "todos" not in u, "ultima.json")
        filas = pd.read_csv(salida / "datos" / "calendario.csv", dtype=str)
        ok(len(filas) == len(res["todos"]) and list(filas.columns[:3]) == ["empresa", "isin", "concepto"], f"calendario.csv ({len(filas)} filas)")
        f = (salida / "fragmento-wp.html").read_text(encoding="utf-8")
        ok(f.count("<!-- dividendos:fin -->") == 1 and '"@type": "Dataset"' in f and len(f) > 3000, "fragmento con JSON-LD y más de 3.000 caracteres (filtro del escenario)")
        ok((salida / "index.html").exists(), "index.html")
        # paradas
        vacio = Path(t) / "vacio"
        try:
            cal.leer(vacio)
            ok(False, "sin la salida de cnmv debe parar")
        except cal.DatosRaros:
            ok(True, "sin la salida de cnmv, DatosRaros")
        malo = preparar(Path(t) / "malo")
        (malo / "cnmv" / "datos" / "dividendos.csv").write_text("canal,nreg\nOIR,1\n", encoding="utf-8")
        try:
            cal.leer(malo)
            ok(False, "dividendos.csv sin columnas debe parar")
        except cal.DatosRaros:
            ok(True, "dividendos.csv sin sus columnas, DatosRaros")
        r = subprocess.run([sys.executable, str(AQUI / "calendario.py"), "--salida", str(vacio / "calendario")], capture_output=True, text=True, check=False)
        ok(r.returncode == 1 and "::error::calendario" in r.stdout, "sin datos, el script sale con 1 y un error (incidencia en el servidor)")
        r = subprocess.run([sys.executable, str(AQUI / "calendario.py"), "--salida", str(Path(t) / "datos" / "cal2"), "--fecha", "2026-11-22"],
                           capture_output=True, text=True, check=False)
        ok(r.returncode == 0 and "5 dividendos con fecha ex" in r.stdout and (Path(t) / "datos" / "cal2" / "fragmento-wp.html").exists(),
           "por línea de órdenes, con --datos por defecto en la carpeta madre de --salida")
        # 24/11/2026: dividendos anunciados en los resultados (Inditex) y efectivo de los flexibles
        itx = [("OIR", "39667", "2026-03-11T07:29:00", "ES0148396007", "Inditex", "inditex", "resultados", "Resultados",
                "La sociedad remite información sobre resultados anuales correspondientes al ejercicio 2025"),
               ("OIR", "39999", "2026-03-12T07:29:00", "ES0148396007", "Inditex", "inditex", "recompras", "Programa de recompra", "Recompra")]
        lect = [x if x[1] != "43244" else ("OIR", "43244", "2026-10-21", "", "", "", "", "2027-02-01", "flexible: parcial") for x in LECTURAS]
        raiz2 = preparar(Path(t) / "res", COMUNICADOS + itx, lect)
        cab = "canal,nreg,pago,fecha_comunicado,isin,empresa,concepto,importe_bruto,moneda,fecha_ex,fecha_registro,fecha_pago,extraccion,dividendo_anunciado,enlace,lector\n"
        (raiz2 / "cnmv" / "datos" / "dividendos_resultados.csv").write_text(
            cab + f"OIR,39667,1,2026-03-11,ES0148396007,Inditex,ordinario,0.875,EUR,2026-04-29,2026-04-30,2026-05-04,completa,1.75,{CNMV}39667,x\n"
            f"OIR,39667,2,2026-03-11,ES0148396007,Inditex,ordinario y extraordinario,0.875,EUR,2026-10-29,2026-10-30,2026-11-02,completa,1.75,{CNMV}39667,x\n"
            f"OIR,39999,1,2026-03-12,ES0148396007,Inditex,ordinario,9.99,EUR,2026-12-01,2026-12-02,2026-12-03,completa,9.99,{CNMV}39999,x\n",
            encoding="utf-8")
        d2, h2 = cal.leer(raiz2)
        r2 = cal.calcular(d2, HOY, h2)
        r2["huella"] = cal.huella(r2)
        itx_pag = [(d["fecha_pago"], d["importe"], d["concepto"], d["fecha_ex"], d["nreg"]) for d in r2["pagados_90d"] if d["empresa"] == "Inditex"]
        ok(itx_pag == [("2026-11-02", 0.875, "ordinario y extraordinario", "2026-10-29", "39667")],
           f"Inditex: el pago del 02/11, anunciado en los resultados, entre los pagados en 90 días ({itx_pag})")
        ok([d["fecha_pago"] for d in r2["todos"] if d["empresa"] == "Inditex"] == ["2026-05-04", "2026-11-02"]
           and not any(d["nreg"] == "39999" for d in r2["todos"]), "Inditex: los dos pagos; una fila cuya nota ya no es de resultados no entra")
        ok(h2 == hasta, "la fecha del último comunicado de dividendo no cambia por las notas de resultados")
        fl = [d for d in r2["flexibles"] if d["empresa"] == "Iberdrola"][0]
        ok(fl["fecha_pago"] == "2027-02-01" and fl["importe"] is None and {"importe", "moneda", "fecha_pago"} <= set(fl),
           "flexible: la fecha de pago del efectivo llega a la lista")
        frag2 = cal.fragmento(r2, h)
        ok("Iberdrola Retribución Flexible: segunda edición</a> · pago del efectivo: 01/02/2027</li>" in frag2
           and "hoy, Inditex" in frag2 and "<td>ordinario y extraordinario</td>" in frag2,
           "fragmento: pago del efectivo del flexible, Inditex en el método y el tipo de su dividendo")
        ok(cal._efectivo({"importe": 0.253, "moneda": "EUR", "fecha_pago": "2027-02-01"})
           == " · efectivo para quien lo elige: 0,253 € por acción; pago del efectivo: 01/02/2027" and cal._efectivo({}) == "",
           "texto del efectivo de un flexible")
        ok(r2["huella"] != res["huella"], "los datos nuevos cambian la huella")
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")


if __name__ == "__main__":
    main()
