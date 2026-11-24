"""Comprobaciones sin red del lector de dividendos de la CNMV añadido el 24/11/2026 (cnmv/dividendos_cnmv.py):
el efectivo de los dividendos flexibles y los dividendos anunciados dentro de los resultados (lista cerrada de
empresas). Van aparte de cnmv/pruebas_cnmv.py para no mezclar estas reglas con las del clasificador.

Los textos de cnmv/pruebas_cnmv/dividendos/flex-*.txt y resultados-*.txt son recortes literales de los PDF de la CNMV
(pdftotext -raw), con «[…]» donde se ha cortado; cada valor esperado se ha comprobado a mano contra el PDF.

Uso: python cnmv/pruebas_dividendos.py
"""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dividendos_cnmv as dv  # noqa: E402

TEXTOS = AQUI / "pruebas_cnmv" / "dividendos"
FALLOS: list[str] = []
N = 0


def ok(cond: bool, texto: str) -> None:
    global N
    N += 1
    if not cond:
        FALLOS.append(texto)
        print("FALLA:", texto)


# --------------------------------------------------------------------------- 1. flexibles: efectivo y fecha de pago
# nreg: (fecha del comunicado, importe, fecha de pago, extracción), comprobados contra el PDF el 24/11/2026
FLEXIBLES = {
    "38415": ("2026-01-08", 0.253, None, "flexible: parcial"),            # Iberdrola, complemento (enero): solo el importe
    "41685": ("2026-07-02", 0.427, None, "flexible: parcial"),            # Iberdrola, complemento (julio): total con el ajuste
    "43244": ("2026-10-21", None, "2027-02-01", "flexible: parcial"),     # Iberdrola, términos: solo la fecha de pago
    "41519": ("2026-06-24", 1.866, "2026-07-15", "flexible: completa"),  # ACS: precio por derecho y calendario
    "43459": ("2026-11-03", 0.835, None, "flexible: parcial"),            # Ferrovial: importe en efectivo
    "43338": ("2026-10-27", None, "2026-12-10", "flexible: parcial"),     # Ferrovial: anuncio con calendario
    "38419": ("2026-01-08", 0.049, "2026-01-29", "flexible: completa"),  # Sacyr: precio fijo por derecho
}


def pruebas_flexibles() -> None:
    for nreg, (fecha, importe, pago, extraccion) in FLEXIBLES.items():
        texto = (TEXTOS / f"flex-OIR-{nreg}.txt").read_text(encoding="utf-8")
        r = dv.extraer(texto, date.fromisoformat(fecha), "Dividendo flexible")
        ok(r["importe_bruto"] == importe and (r["moneda"] == "EUR") == (importe is not None)
           and (r["fecha_pago"].isoformat() if r["fecha_pago"] else None) == pago and r["extraccion"] == extraccion
           and r["fecha_ex"] is None and r["fecha_registro"] is None,
           f"flexible OIR {nreg}: {importe} y {pago} ({r})")
    com = date(2026, 6, 16)
    # importes que no son el efectivo fijo: mínimo, objetivo, máximo
    for frase in ("El importe del Dividendo Complementario bruto por acción será, como mínimo, de 0,425 euros.",
                  "Dividendo Objetivo bruto por acción, que ascenderá a 0,427 euros.",
                  "no excede del máximo de 0,256 euros brutos por acción aprobado por el Consejo."):
        r = dv.extraer(frase, com, "Dividendo flexible")
        ok(r["importe_bruto"] is None and r["extraccion"] == "flexible: ver comunicado", f"no es el efectivo fijo: «{frase}»")
    dos = dv.extraer("El importe del Dividendo a Cuenta bruto por acción es de 0,253 euros. "
                     "El importe del Dividendo a Cuenta bruto por acción es de 0,260 euros.", com, "Dividendo flexible")
    ok(dos["importe_bruto"] is None, "dos importes distintos: sin importe")
    igual = dv.extraer("El importe del Dividendo a Cuenta bruto por acción es de 0,253 euros. Repetido: el importe del "
                       "Dividendo a Cuenta bruto por acción es de 0,253 euros.", com, "Dividendo flexible")
    ok(igual["importe_bruto"] == 0.253, "el mismo importe dos veces: vale")
    sin_derecho = dv.extraer("El precio del Compromiso de Compra de derechos asumido por ACS es de 1,866 euros brutos por derecho.",
                             com, "Dividendo flexible")
    ok(sin_derecho["importe_bruto"] is None, "precio por derecho sin «un derecho por cada acción»: sin importe")
    con_derecho = dv.extraer("Recibirán un derecho de asignación gratuita por cada acción. El precio del Compromiso de Compra de "
                             "derechos asumido por ACS es de 1,866 euros brutos por derecho.", com, "Dividendo flexible")
    ok(con_derecho["importe_bruto"] == 1.866, "precio por derecho con un derecho por acción: efectivo por acción")
    dos_fechas = dv.extraer("27 de julio de 2026 Pago del Dividendo Complementario a quienes hubieran optado por recibir efectivo. "
                            "28 de julio de 2026 Pago del Dividendo Complementario a quienes hubieran optado por recibir efectivo.",
                            com, "Dividendo flexible")
    ok(dos_fechas["fecha_pago"] is None, "dos fechas de pago distintas: sin fecha")
    vieja = dv.extraer("27 de julio de 2024 Pago del Dividendo Complementario a quienes hubieran optado por recibir efectivo.",
                       com, "Dividendo flexible")
    ok(vieja["fecha_pago"] is None, "fecha de pago anterior al comunicado: sin fecha")
    ok(dv.extraer("", com, "Dividendo flexible")["extraccion"] == "flexible: ver comunicado", "sin texto: ver el comunicado")
    ok(dv.extraer("Iberdrola Retribución Flexible", com, "Dividendo flexible")["extraccion"] == "flexible: ver comunicado",
       "título sin frases del efectivo: ver el comunicado")


def pruebas_titulos() -> None:
    si = ["Complemento al documento informativo de la primera edición del sistema de dividendo opcional “Iberdrola Retribución Flexible” de 2026",
          "Términos y condiciones de la segunda edición del sistema de dividendo opcional \"Iberdrola Retribución Flexible\" del ejercicio 2026",
          "Primera ejecución del dividendo flexible autorizado por la Junta de Accionistas de ACS del 8 de mayo de 2026",
          "Ejecución del acuerdo de ampliación de capital (scrip dividend) con cargo a beneficios (reservas de libre disposición) y el correspondiente documento informativo.",
          "Ferrovial anuncia el importe del dividendo en efectivo por acción correspondiente a su dividendo flexible",
          "Ferrovial anuncia un dividendo flexible (scrip dividend) pagadero en acciones o en efectivo"]
    no = ["Cierre de la primera edición del sistema de dividendo opcional \"Iberdrola Retribución Flexible\" del ejercicio 2026",
          "Modificación del número de derechos de voto y capital social por ampliación de capital del sistema Iberdrola Retribución Flexible de julio de 2026.",
          "Calendario estimado de la primera edición del sistema de dividendo opcional “Iberdrola Retribución Flexible” de 2026.",
          "Ferrovial informa de la ratio y el número de acciones a entregar en el dividendo flexible",
          "Iberdrola Retribución Flexible"]
    ok(all(dv.flexible_con_documento(t) for t in si), "títulos que se descargan: documento, términos, ejecución, importe, pagadero")
    ok(not any(dv.flexible_con_documento(t) for t in no), "títulos que no se descargan: cierre, capital, calendario estimado, ratio")


def pruebas_actualizar() -> None:
    """La pasada descarga y lee el complemento; el cierre, no; un flexible sin documento queda «sin documento»."""
    tmp = Path(tempfile.mkdtemp(prefix="pruebas_dividendos_"))
    try:
        datos = tmp / "cnmv" / "datos"
        datos.mkdir(parents=True)
        cab = "canal,nreg,fecha,emisor,categoria,texto,enlace,isin,empresa,ficha,caja,etiqueta,periodo,grupo\n"
        filas = [
            'OIR,41685,2026-07-02T08:00:00,IBERDROLA,Otros,"Complemento al documento informativo de la primera edición del sistema de dividendo opcional Iberdrola Retribución Flexible de 2026",https://x/41685,ES0144580Y14,Iberdrola,iberdrola,dividendos,Dividendo flexible,,g1',
            'OIR,42059,2026-07-24T08:00:00,IBERDROLA,Otros,"Cierre de la primera edición del sistema de dividendo opcional Iberdrola Retribución Flexible del ejercicio 2026",https://x/42059,ES0144580Y14,Iberdrola,iberdrola,dividendos,Dividendo flexible,,g1',
            'OIR,41519,2026-06-24T08:00:00,ACS,Otros,"Primera ejecución del dividendo flexible autorizado por la Junta de Accionistas de ACS del 8 de mayo de 2026",https://x/41519,ES0167050915,ACS,acs,dividendos,Dividendo flexible,,g2',
            'OIR,41935,2026-07-17T08:00:00,ACS,Otros,"AMPLIACION Y SIMULTÁNEA REDUCCIÓN DEL CAPITAL SOCIAL COMO PRIMERA EJECUCIÓN DEL DIVIDENDO FLEXIBLE",https://x/41935,ES0167050915,ACS,acs,dividendos,Dividendo flexible,,g2',
        ]
        (datos / "ibex35.csv").write_text(cab + "\n".join(filas) + "\n", encoding="utf-8")
        pedidos: list = []

        def texto_de(canal, nreg, enlace):
            pedidos.append(nreg)
            ruta = TEXTOS / f"flex-{canal}-{nreg}.txt"
            return ruta.read_text(encoding="utf-8") if ruta.exists() else None

        r = dv.actualizar(datos, limite=20, texto_de=texto_de)
        tabla = {row["nreg"]: row for row in csv.DictReader((datos / "dividendos.csv").open(encoding="utf-8"))}
        ok(r["leidos"] == 4 and sorted(pedidos) == ["41519", "41685", "41935"], f"se descargan complemento y ejecuciones, no el cierre ({pedidos})")
        ok(tabla["41685"]["importe_bruto"] == "0.427" and tabla["41685"]["extraccion"] == "flexible: parcial", "Iberdrola: 0,427 € (total con ajuste)")
        ok(tabla["41519"]["importe_bruto"] == "1.866" and tabla["41519"]["fecha_pago"] == "2026-07-15"
           and tabla["41519"]["extraccion"] == "flexible: completa", "ACS: 1,866 € y pago el 15/07/2026")
        ok(tabla["42059"]["extraccion"] == "flexible: ver comunicado" and tabla["42059"]["importe_bruto"] == "", "el cierre no se lee")
        ok(tabla["41935"]["extraccion"] == "sin documento" and tabla["41935"]["intentos"] == "1", "flexible sin documento: se reintenta")
        n = len(pedidos)
        dv.actualizar(datos, limite=20, texto_de=texto_de)
        ok(pedidos[n:] == ["41935"], f"en la pasada siguiente solo se vuelve a pedir el que no tenía documento ({pedidos[n:]})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    pruebas_flexibles()
    pruebas_titulos()
    pruebas_actualizar()
    if FALLOS:
        print(f"{len(FALLOS)} de {N} comprobaciones fallan.")
        sys.exit(1)
    print(f"Todas las comprobaciones pasan ({N}).")
