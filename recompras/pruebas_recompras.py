"""Comprobaciones sin red del lector de filas de recompras (fase 0). Los textos simulados reproducen la
maquetación real (pdftotext -layout) de los informes semanales leídos el 18/11/2026 en la CNMV, con las
cifras recortadas a unas pocas filas; los totales de control son los que declaran los propios documentos."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filas  # noqa: E402

FALLOS = []
TOTAL = 0


def ok(cond, texto):
    global TOTAL
    TOTAL += 1
    if not cond:
        FALLOS.append(texto)
        print("FALLA:", texto)


# Estilo español, fecha y ticker pegados con un solo espacio, anexo detrás (maqueta Repsol).
REPSOL = """
                                           Centro de      Número de          Precio
          Fecha       Valor   Operación
                                          negociación      acciones        (€/acción)
       11/11/2026 REP.MC       Compra       XMAD           763.405          29,3857
       11/11/2026 REP.MC       Compra        CEUX           151.098         29,3306
       12/11/2026 REP.MC       Compra       XMAD            766.917         29,7240
Se acompaña como anexo información detallada sobre cada una de las operaciones
realizadas durante el período indicado.
                                                                   ANEXO
  Detalle de las operaciones de compra de acciones propias realizadas durante el período
11/11/2026                 REP.MC                     Compra                      CEUX                       1.500                  29,3900
11/11/2026                 REP.MC                     Compra                      XMAD                       1.500                  29,4000
"""

# Estilo inglés: fecha 09-Nov-26, miles con coma, símbolo de moneda delante del precio (maqueta IAG).
IAG = """
                                         Número total de        Precio medio diario
     Fecha            Mercado
                                       acciones adquiridas          (£/€ acción)
   09-Nov-26            LON                  391,656                  £ 4.448
   09-Nov-26            MAD                  458,514                  € 5.340
   10-Nov-26            MAD                  54,513                   € 5.434
Se acompaña a este anuncio un desglose completo de las operaciones individuales
                                   Anexo
     International Consolidated Airlines Group, S.A.   09/11/2026                08:01:00           ES0177542018        XLON    1,200   4.45
"""

# Instrumento delante de la fecha, importe en euros como tercera cifra, centro al final; TOTAL (maqueta CaixaBank).
CAIXABANK = """
    Instrumento                                    Número de    Precio medio      Importe       Centro de
                            Fecha      Operación
     Financiero                                     acciones    ponderado (€)   Compras (€)    negociación
        CABK              30/10/2026    Compra        102.099         11,2048      1.143.996     XMAD
        CABK              30/10/2026    Compra         55.190         11,2040        618.349     CEUX
        CABK              03/11/2026    Compra          9.964         11,1971        111.568     TQEX
                                        TOTAL         167.253         11,2041      1.873.913
Se acompaña como Anexo información detallada sobre cada una de las operaciones realizadas
                          ANEXO
            30/10/2026    09:00:21      CABK        Compra        CEUX          391       11,0000
"""

# Centro de negociación en texto largo, precio con dos decimales, total sin fecha (maqueta Ferrovial).
FERROVIAL = """
                                                                     Número de acciones        Precio medio
     Fecha         Valor           Centro de negociación
                                                                        adquiridas             ponderado (€)
   06/11/2026      FER      Centros de negociación estadounidenses         55.000                  52,64
   09/11/2026      FER      Centros de negociación estadounidenses         55.000                  54,33
     Total                                                                110,000                  53.49
"""

# Precio con tres decimales e intermediario con espacios al final de la fila (maqueta ACS).
ACS = """
    Fecha          Valor    Centro de negociación Número de acciones                    Intermediario
  10/11/2026      ACS.MA           AQEU                 4.218             89,648      SOCIETE GENERALE
  10/11/2026      ACS.MA           CEUX                22.979             89,656      SOCIETE GENERALE
Se acompaña como anexo información detallada sobre cada una de las operaciones realizadas durante el
   10/11/2026              CEUX                 27                   90,000        10/11/2026          XMAD                 11                  89,900
"""

# Sin tabla resumen antes del anexo: se lee todo y se descartan las filas con hora.
SOLO_ANEXO = """
Se acompaña como anexo información detallada.
                                               ANEXO
       09/11/2026           09:00:12            XMAD                682             26,8900
       09/11/2026                               XMAD             59.368             26,8442
       09/11/2026                               CEUX             40.196             26,8747
"""

VENTA = "   12/11/2026      XYZ      Venta        XMAD            1.000          10,50\n"

# --- Lectura de filas -------------------------------------------------------------------------------------
f = filas.leer_filas(REPSOL)
ok(len(f) == 3, "Repsol: tres filas del resumen diario, ninguna del anexo")
ok(f[0]["fecha"] == "2026-11-11" and f[0]["centro"] == "XMAD" and f[0]["acciones"] == 763405, "Repsol: fecha, centro y acciones")
ok(abs(f[0]["precio"] - 29.3857) < 1e-9 and f[0]["moneda"] == "EUR" and f[0]["operacion"] == "compra", "Repsol: precio, moneda y operación")
ok(not any(x["detalle"] for x in f), "Repsol: el resumen diario no lleva hora")
todas = filas.leer_filas(REPSOL, solo_primera_tabla=False)
ok(len(todas) == 5 and todas[-1]["acciones"] == 1500, "Repsol: con solo_primera_tabla=False entran también las filas del anexo")

f = filas.leer_filas(IAG)
ok(len(f) == 3, "IAG: tres filas, el anexo queda fuera")
ok(f[0]["fecha"] == "2026-11-09" and f[0]["centro"] == "XLON" and f[0]["acciones"] == 391656, "IAG: fecha inglesa, LON -> XLON, miles con coma")
ok(abs(f[0]["precio"] - 4.448) < 1e-9 and f[0]["moneda"] == "GBP", "IAG: precio 4.448 en libras (punto decimal, no miles)")
ok(f[1]["centro"] == "XMAD" and f[1]["moneda"] == "EUR" and abs(f[1]["precio"] - 5.34) < 1e-9, "IAG: fila en euros de Madrid")

f = filas.leer_filas(CAIXABANK)
ok(len(f) == 3, "CaixaBank: tres filas; la línea TOTAL (sin fecha) no cuenta")
ok(f[0]["acciones"] == 102099 and abs(f[0]["precio"] - 11.2048) < 1e-9 and f[0]["centro"] == "XMAD", "CaixaBank: acciones y precio son la primera y la segunda cifra, el importe se ignora")
ok(f[2]["centro"] == "TQEX" and f[2]["fecha"] == "2026-11-03", "CaixaBank: centro al final de la fila")

f = filas.leer_filas(FERROVIAL)
ok(len(f) == 2 and all(x["centro"] == "EEUU" for x in f), "Ferrovial: centro en texto largo -> EEUU")
ok(f[0]["acciones"] == 55000 and abs(f[0]["precio"] - 52.64) < 1e-9, "Ferrovial: cifras con el centro en texto por medio")

f = filas.leer_filas(ACS)
ok(len(f) == 2 and f[0]["acciones"] == 4218 and abs(f[0]["precio"] - 89.648) < 1e-9, "ACS: precio con tres decimales (89,648 es precio, no miles)")

f = filas.leer_filas(SOLO_ANEXO)
ok(len(f) == 2 and all(not x["detalle"] for x in f), "Sin tabla resumen: se lee todo y se descartan las filas con hora")
ok(filas.leer_filas(SOLO_ANEXO, solo_primera_tabla=False)[0]["detalle"], "La fila con hora se marca como detalle")

f = filas.leer_filas(VENTA)
ok(len(f) == 1 and f[0]["operacion"] == "venta", "Operación de venta reconocida")
ok(filas.leer_filas("Texto sin filas 12/11/2026 y sin centro 1.000 10,50\n") == [], "Fecha sin centro de negociación no es fila")
ok(filas.leer_filas("   12/11/2026   XMAD   solo una cifra 1.000\n") == [], "Fila con una sola cifra se descarta")
ok(filas.leer_filas("   31/13/2026   XMAD   1.000   10,50\n") == [], "Fecha imposible se descarta")

# --- Números -----------------------------------------------------------------------------------------------
ok(filas._numero("763.405") == 763405 and abs(filas._numero("29,3857") - 29.3857) < 1e-9, "Números en español")
ok(filas._numero("391,656", "en") == 391656 and abs(filas._numero("4.448", "en") - 4.448) < 1e-9, "Números en inglés")
ok(abs(filas._numero("1.143.996,50") - 1143996.5) < 1e-9, "Miles y decimales en español")

# --- Resumen y totales de control --------------------------------------------------------------------------
r = filas.resumen(filas.leer_filas(CAIXABANK))
ok(r["acciones"] == 167253 == filas.totales_declarados(CAIXABANK)[0], "CaixaBank: la suma coincide con el TOTAL declarado")
ok(abs(r["precio_medio"]["EUR"] - 11.2041) < 5e-4, "CaixaBank: precio medio ponderado coincide con el declarado (11,2041)")
ok(r["desde"] == "2026-10-30" and r["hasta"] == "2026-11-03" and r["dias"] == 2 and r["centros"] == ["CEUX", "TQEX", "XMAD"], "CaixaBank: fechas, días y centros")

r = filas.resumen(filas.leer_filas(FERROVIAL))
ok(r["acciones"] == 110000 == filas.totales_declarados(FERROVIAL)[0], "Ferrovial: suma = Total declarado (110,000 en estilo inglés)")
ok(abs(r["precio_medio"]["EUR"] - 53.485) < 1e-6, "Ferrovial: precio medio ponderado 53,485 (el documento redondea a 53.49)")

r = filas.resumen(filas.leer_filas(IAG))
ok(r["acciones"] == 904683 and set(r["precio_medio"]) == {"EUR", "GBP"}, "IAG: un precio medio por moneda")
ok(abs(r["precio_medio"]["GBP"] - 4.448) < 1e-9, "IAG: medio en libras con una sola fila")
esperado_eur = (458514 * 5.340 + 54513 * 5.434) / (458514 + 54513)
ok(abs(r["precio_medio"]["EUR"] - round(esperado_eur, 4)) < 1e-9, "IAG: medio ponderado en euros")

r = filas.resumen(filas.leer_filas(VENTA))
ok(r["filas"] == 0 and r["acciones"] == 0 and r["desde"] is None, "El resumen solo cuenta compras; sin compras, vacío")

# Caso de control frente a una librería de referencia: media ponderada con numpy.
try:
    import numpy as np
    fr = filas.leer_filas(REPSOL)
    ref = float(np.average([x["precio"] for x in fr], weights=[x["acciones"] for x in fr]))
    ok(abs(filas.resumen(fr)["precio_medio"]["EUR"] - round(ref, 4)) < 1e-9, "Control: media ponderada igual que numpy.average")
except ImportError:
    print("aviso: numpy no disponible, control de referencia omitido")

ok(filas.totales_declarados("Total…        3.305.308\n") == [3305308], "Total con puntos suspensivos (Sabadell)")
ok(filas.totales_declarados("TOTAL:   492.309 acciones Precio Medio 26,70\n") == [492309], "TOTAL: con dos puntos (Cellnex)")
ok(filas.totales_declarados("sin totales\n") == [], "Sin línea Total")

# =========================================================================== Colector (fase 1): recompras.py
import json
import tempfile
from datetime import date
from pathlib import Path

import recompras  # noqa: E402

HOY = date(2026, 11, 19)

# --- Acumulado del programa según el texto ----------------------------------------------------------------
SABADELL_TXT = """El importe monetario total de las acciones compradas bajo el Programa de Recompra asciende a 313.703.878,75 euros, lo que representa
aproximadamente, el 94,77% del importe monetario máximo del Programa de Recompra, quedando por tanto pendiente de ejecución aproximadamente el 5,23%.
El número total de acciones compradas bajo el actual Programa de Recompra asciende
a 87.683.998 acciones (que representan el 1,84% del capital social actual)."""
pr = recompras.resumen_programa(SABADELL_TXT)
ok(pr["pct_programa"] == 94.77 and pr["importe_programa_eur"] == 313703878.75, "Programa: porcentaje e importe (Sabadell)")
ok(pr["acciones_programa"] == 87683998 and pr["pct_capital"] == 1.84 and pr["finalizado"] is False, "Programa: acciones acumuladas y % del capital (Sabadell)")

BBVA_TXT = "El importe monetario de las acciones compradas hasta la fecha como consecuencia de la\nejecución del Segundo Tramo asciende a 336.983.018,88 euros, que representa,\naproximadamente, el 33,70% del importe monetario máximo del Segundo Tramo."
pr = recompras.resumen_programa(BBVA_TXT)
ok(pr["pct_programa"] == 33.7 and pr["importe_programa_eur"] == 336983018.88 and pr["acciones_programa"] is None, "Programa: BBVA (sin acciones acumuladas)")

CAIXA_TXT = "el número total de acciones adquiridas en el marco del programa de recompras asciende a 29.476.674 que representan un importe de 358.741.361 euros equivalente\n al 71,75 % del importe monetario máximo."
pr = recompras.resumen_programa(CAIXA_TXT)
ok(pr["pct_programa"] == 71.75 and pr["importe_programa_eur"] == 358741361.0 and pr["acciones_programa"] == 29476674, "Programa: CaixaBank (asciende a N que representan un importe de X euros)")

CELLNEX_TXT = "el Programa de Recompra\nha finalizado al haberse alcanzado el importe máximo de 200 millones de euros.\nEn el marco de la ejecución del Programa de Recompra se han adquirido un total de 7.861.372\nacciones propias, que representan el 1,18% del capital social de Cellnex."
pr = recompras.resumen_programa(CELLNEX_TXT)
ok(pr["finalizado"] is True and pr["pct_programa"] == 100.0 and pr["acciones_programa"] == 7861372 and pr["pct_capital"] == 1.18, "Programa: Cellnex terminado al alcanzar el importe máximo")
ok(pr["importe_programa_eur"] is None, "Programa: «200 millones de euros» no se toma como importe (va en millones, no en cifra)")
pr = recompras.resumen_programa("Texto sin cifras del programa.")
ok(all(v is None for k, v in pr.items() if k != "finalizado") and pr["finalizado"] is False, "Programa: sin datos -> None")

# --- Documentos de la página del comunicado -----------------------------------------------------------------
PAGINA = """<a href="/portal/home.aspx">Inicio</a> <a href="https://www.cnmv.es/webservices/verdocumento/ver?t=%7baaa%7d">Informe</a>
<a href="/webservices/verdocumento/ver?t=%7bbbb%7d&amp;x=1">Anexo</a> <a href="/DocPortal/Aviso.pdf">Aviso legal</a>
<a href="https://www.cnmv.es/webservices/verdocumento/ver?t=%7baaa%7d">Informe otra vez</a>"""
docs = recompras.enlaces_documentos(PAGINA)
ok(docs == ["https://www.cnmv.es/webservices/verdocumento/ver?t=%7baaa%7d", "https://www.cnmv.es/webservices/verdocumento/ver?t=%7bbbb%7d&x=1"],
   "Documentos: solo verdocumento, absolutos, sin repetir, entidades HTML deshechas")
ok(recompras.texto_pdf(b"no es un pdf") == "", "texto_pdf: lo que no es PDF devuelve cadena vacía")

# --- Análisis de un informe y registro ----------------------------------------------------------------------
a = recompras.analizar(CAIXABANK)
ok(a["coincide"] is True and a["resumen"]["acciones"] == 167253 and a["programa"]["pct_programa"] is None, "analizar: filas, coincidencia y programa")
a = recompras.analizar(CAIXABANK.replace("TOTAL         167.253", "TOTAL         167.999"))
ok(a["coincide"] is False, "analizar: la suma no coincide con un total declarado distinto")
ok(recompras.analizar(REPSOL)["coincide"] is None, "analizar: sin total declarado, coincide es None")

listado_fila = {"nreg": "43525", "fecha": "2026-11-06T08:59:25", "isin": "ES0140609019", "empresa": "CaixaBank", "texto": "La Sociedad remite información",
                "enlace": "https://www.cnmv.es/portal/otra-informacion-relevante/Resultado-OIR.aspx?nreg=43525", "caja": "recompras"}
recompras.AVISOS.clear()
inf, ops = recompras.informe_desde_textos(listado_fila, [("u1", "sin nada"), ("u2", CAIXABANK + SABADELL_TXT)], HOY)
ok(inf["estado"] == "leido" and inf["documento"] == "u2" and inf["filas"] == 3 and inf["acciones"] == 167253, "Informe: se elige el documento con filas")
ok(abs(float(inf["importe_estimado_eur"]) - (102099 * 11.2048 + 55190 * 11.2040 + 9964 * 11.1971)) < 0.01, "Informe: importe estimado = suma de acciones × precio")
ok(inf["coincide"] == 1 and inf["total_declarado"] == 167253 and inf["pct_programa"] == 94.77 and inf["leido"] == "2026-11-19", "Informe: total declarado, coincidencia, programa y fecha de lectura")
ok(len(ops) == 3 and ops[0]["nreg"] == "43525" and ops[0]["centro"] == "XMAD" and ops[0]["acciones"] == 102099, "Informe: operaciones diarias con nreg y centro")
inf, ops = recompras.informe_desde_textos(listado_fila, [("u1", BBVA_TXT)], HOY)
ok(inf["estado"] == "sin_filas" and inf["pct_programa"] == 33.7 and ops == [], "Informe sin tabla legible: estado sin_filas con el acumulado del texto (BBVA)")
inf, ops = recompras.informe_desde_textos(listado_fila, [], HOY)
ok(inf["estado"] == "sin_texto" and ops == [], "Informe sin documentos: sin_texto")
inf, _ = recompras.informe_desde_textos(listado_fila, [("u", CAIXABANK.replace("TOTAL         167.253", "TOTAL         167.999"))], HOY)
ok(inf["coincide"] == 0 and any("no coincide" in x for x in recompras.AVISOS), "Informe que no coincide: marcado y aviso")

# --- Pendientes y reintentos --------------------------------------------------------------------------------
listado = [{"nreg": "3", "fecha": "2026-11-18"}, {"nreg": "2", "fecha": "2026-11-17"}, {"nreg": "1", "fecha": "2026-11-16"}]
informes = [{"nreg": "1", "estado": "leido", "intentos": "1"}, {"nreg": "2", "estado": "error", "intentos": "1"}]
ok([r["nreg"] for r in recompras.pendientes(listado, informes)] == ["3", "2"], "Pendientes: los nuevos y los errores con intentos por debajo del máximo")
informes[1]["intentos"] = str(recompras.INTENTOS_MAX)
ok([r["nreg"] for r in recompras.pendientes(listado, informes)] == ["3"], "Pendientes: un error agotado no se reintenta")

# --- Serie semanal y cálculo --------------------------------------------------------------------------------
ops = [{"isin": "A", "empresa": "A", "fecha": "2026-11-09", "centro": "XMAD", "operacion": "compra", "acciones": "100", "precio": "10", "moneda": "EUR"},
       {"isin": "A", "empresa": "A", "fecha": "2026-11-13", "centro": "CEUX", "operacion": "compra", "acciones": "50", "precio": "12", "moneda": "EUR"},
       {"isin": "B", "empresa": "B", "fecha": "2026-11-10", "centro": "XLON", "operacion": "compra", "acciones": "70", "precio": "4", "moneda": "GBP"},
       {"isin": "B", "empresa": "B", "fecha": "2026-11-17", "centro": "XMAD", "operacion": "compra", "acciones": "10", "precio": "5", "moneda": "EUR"},
       {"isin": "C", "empresa": "C", "fecha": "2026-11-12", "centro": "XMAD", "operacion": "venta", "acciones": "999", "precio": "5", "moneda": "EUR"}]
serie = recompras.serie_semanal(ops)
ok([s["semana"] for s in serie] == ["2026-11-09", "2026-11-16"], "Serie: semanas ISO por su lunes")
ok(serie[0] == {"semana": "2026-11-09", "empresas": 2, "acciones": 220, "importe_estimado_eur": 1600.0}, "Serie: acciones de todas las monedas, importe solo de las filas en euros, ventas fuera")
ok(recompras.percentil(5, [1, 2, 3]) is None, "Percentil: None con menos de 52 semanas")
ok(recompras.percentil(3, list(range(1, 53))) == round(100 * 3 / 52, 1), "Percentil débil con 52 observaciones")

base = {"nreg": "1", "isin": "A", "empresa": "Alfa", "fecha_comunicado": "2026-11-17", "titulo": "t", "enlace": "e", "documento": "d", "estado": "leido", "intentos": "1",
        "filas": "2", "acciones": "150", "precio_medio": "10.6667", "moneda": "EUR", "importe_estimado_eur": "1600.0", "desde": "2026-11-09", "hasta": "2026-11-13", "dias": "2",
        "centros": "CEUX+XMAD", "total_declarado": "150", "coincide": "1", "acciones_programa": "", "importe_programa_eur": "", "pct_programa": "40.5", "pct_capital": "", "finalizado": "0", "leido": "2026-11-18"}
viejo = dict(base, nreg="0", fecha_comunicado="2026-11-01", pct_programa="20")
otro = dict(base, nreg="2", isin="B", empresa="Beta", fecha_comunicado="2026-11-10", acciones="80", importe_estimado_eur="280.0", finalizado="1", pct_programa="100")
antiguo = dict(base, nreg="9", isin="C", empresa="Gamma", fecha_comunicado="2026-09-01")
roto = dict(base, nreg="7", isin="D", empresa="Delta", fecha_comunicado="2026-11-18", estado="error", acciones="0", importe_estimado_eur="")
d = recompras.calcular([base, viejo, otro, antiguo, roto], ops, HOY)
ok([x["empresa"] for x in d["semana"]["informes"]] == ["Alfa"] and d["semana"]["acciones"] == 150 and d["semana"]["importe_estimado_eur"] == 1600.0, "Calcular: la semana toma el último informe de cada empresa en siete días; los errores no cuentan")
ok([x["empresa"] for x in d["en_curso"]["programas"]] == ["Alfa"] and [x["empresa"] for x in d["en_curso"]["terminados"]] == ["Beta"], "Calcular: en curso a 45 días, con los terminados aparte y los de hace meses fuera")
ok(d["en_curso"]["programas"][0]["pct_programa"] == 40.5 and d["en_curso"]["programas"][0]["coincide"] is True and d["en_curso"]["programas"][0]["centros"] == ["CEUX", "XMAD"], "Calcular: tipos convertidos en la ficha de cada informe")
ok(d["serie"]["n_semanas"] == 1 and d["serie"]["ultima_completa"]["semana"] == "2026-11-09" and d["serie"]["percentil_ultima"] is None, "Calcular: solo las semanas completas cuentan; sin percentil todavía")
ok(d["cobertura"] == {"informes_leidos": 4, "informes_sin_filas": 0, "informes_error": 1, "coinciden": 4, "no_coinciden": 0, "primer_comunicado": "2026-09-01"}, "Calcular: cobertura")
h1 = recompras.huella(d)
d2 = recompras.calcular([base, viejo, otro, antiguo, roto], ops, date(2026, 11, 20))
ok(recompras.huella(d2) == h1, "Huella: no cambia con la fecha de la pasada si las ventanas no cambian")
d3 = recompras.calcular([base, viejo, otro, antiguo, roto], ops + [dict(ops[0], fecha="2026-11-18")], HOY)
ok(recompras.huella(d3) != h1, "Huella: cambia con una operación nueva")

# --- Fragmento ---------------------------------------------------------------------------------------------
frag = recompras.fragmento(dict(d, huella=h1))
ok(frag.startswith(f"<!-- recompras:inicio {h1} -->") and frag.rstrip().endswith("<!-- recompras:fin -->"), "Fragmento: marcas con la huella")
ok("Alfa" in frag and "40,50 %" in frag and "1.600 €" in frag and "Programas terminados en el periodo: Beta" in frag, "Fragmento: tabla de la semana, programas y terminados")
ok("$" not in frag and "application/ld+json" in frag and "recomendación" in frag and "Históricamente" in frag, "Fragmento: sin dólar, con JSON-LD y marco educativo")
ok("percentil histórico se publicará cuando haya 52 semanas" in frag, "Fragmento: aviso de serie corta")
ok(recompras.frase_semana(recompras.calcular([antiguo], [], HOY)).startswith("Ninguna empresa"), "Frase: sin comunicados en la semana")
tres = recompras.calcular([base, dict(base, nreg="5", isin="E", empresa="Eps", fecha_comunicado="2026-11-16"), dict(base, nreg="6", isin="F", empresa="Fi", fecha_comunicado="2026-11-15"), dict(base, nreg="8", isin="G", empresa="Ge", fecha_comunicado="2026-11-14")], ops, HOY)
ok("y otras 1)" in recompras.frase_semana(tres), "Frase: con más de tres empresas, «y otras N»")
mixto = dict(base, moneda="EUR+GBP")
ok("(solo euros)" in recompras.fragmento(recompras.calcular([mixto], ops, HOY)), "Fragmento: importe parcial marcado cuando hay varias monedas")

# --- Pasada completa sin red (--local) y escritura ------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    local = Path(tmp) / "local"
    local.mkdir()
    cab = "canal,nreg,fecha,emisor,categoria,texto,enlace,isin,empresa,ficha,caja,etiqueta,periodo,grupo\n"
    filas_l = [
        "OIR,43525,2026-11-06T08:59:25,CAIXABANK,Programas de recompra,Informe,https://cnmv/oir/43525,ES0140609019,CaixaBank,caixabank,recompras,Programa de recompra,,",
        "OIR,43664,2026-11-16T10:55:16,BBVA,Programas de recompra,Informe,https://cnmv/oir/43664,ES0113211835,BBVA,bbva,recompras,Programa de recompra,,",
        "OIR,43719,2026-11-18T15:59:48,REPSOL,Programas de recompra,Informe,https://cnmv/oir/43719,ES0173516115,Repsol,repsol,recompras,Programa de recompra,,",
        "OIR,43700,2026-11-18T09:00:00,REPSOL,Programas de recompra,Sin documento,https://cnmv/oir/43700,ES0173516115,Repsol,repsol,recompras,Programa de recompra,,",
        "OIR,43600,2026-11-02T08:00:00,SANTANDER,Dividendos,Dividendo,https://cnmv/oir/43600,ES0113900J37,Santander,santander,dividendos,Dividendo,,",
    ]
    (local / "ibex35.csv").write_text(cab + "\n".join(filas_l) + "\n", encoding="utf-8")
    (local / "43525.txt").write_text(CAIXABANK + "\n" + CAIXA_TXT, encoding="utf-8")
    (local / "43664.txt").write_text(BBVA_TXT, encoding="utf-8")
    (local / "43719.txt").write_text(REPSOL, encoding="utf-8")
    listado = recompras.leer_listado(str(local / "ibex35.csv"))
    ok([r["nreg"] for r in listado] == ["43719", "43700", "43664", "43525"], "Listado: solo caja recompras, del más reciente al más antiguo")
    recompras.AVISOS.clear()
    informes, operaciones, hechos = recompras.recoger(listado, [], [], HOY, local=local)
    est = {i["nreg"]: i["estado"] for i in informes}
    ok(hechos == 4 and est == {"43719": "leido", "43700": "sin_texto", "43664": "sin_filas", "43525": "leido"}, "Recoger: estados por comunicado (leído, sin texto, sin filas)")
    ok(len(operaciones) == 6 and operaciones[0]["fecha"] >= operaciones[-1]["fecha"], "Recoger: operaciones de los informes leídos, de la más reciente a la más antigua")
    informes2, operaciones2, hechos2 = recompras.recoger(listado, informes, operaciones, HOY, local=local)
    ok(hechos2 == 0 and informes2 == informes and operaciones2 == operaciones, "Recoger: segunda pasada sin pendientes no cambia nada")
    d = recompras.calcular(informes, operaciones, HOY)
    ok([x["empresa"] for x in d["semana"]["informes"]] == ["Repsol", "BBVA"] and d["semana"]["informes"][1]["estado"] == "sin_filas", "Pasada local: semana con Repsol y BBVA (sin tabla legible)")
    ok([x["empresa"] for x in d["en_curso"]["programas"]] == ["Repsol", "CaixaBank", "BBVA"], "Pasada local: programas en curso ordenados por importe estimado")
    salida = Path(tmp) / "salida"
    ok(recompras.escribir(salida, d, informes, operaciones) is True, "Escribir: primera pasada escribe")
    ok(all((salida / x).exists() for x in ("fragmento-wp.html", "index.html", "datos/ultima.json", "datos/informes.csv", "datos/operaciones.csv", "datos/semanal.csv")), "Escribir: seis ficheros")
    j = json.loads((salida / "datos/ultima.json").read_text(encoding="utf-8"))
    ok(j["huella"] == (salida / "fragmento-wp.html").read_text(encoding="utf-8").split()[2] and j["version"] == recompras.VERSION, "Escribir: la huella del JSON es la del fragmento")
    ok(recompras.escribir(salida, d, informes, operaciones) is False, "Escribir: sin cambios no reescribe")
    ok(recompras.escribir(salida, d, informes, operaciones, forzar=True) is True, "Escribir: --forzar reescribe")
    inf2, ops2 = recompras.cargar_estado(salida / "datos")
    ok(len(inf2) == 4 and len(ops2) == 6 and inf2[0]["nreg"] == "43719" and ops2[0]["fecha"] == "2026-11-12" and ops2[0]["acciones"] == "766917", "Estado: se recarga del CSV")
    try:
        recompras.leer_listado(str(local / "no_existe.csv"))
        ok(False, "Listado inexistente debe parar")
    except recompras.DatosRaros:
        ok(True, "Listado inexistente: DatosRaros")
    (local / "vacio.csv").write_text(cab + filas_l[-1] + "\n", encoding="utf-8")
    try:
        recompras.leer_listado(str(local / "vacio.csv"))
        ok(False, "Listado sin recompras debe parar")
    except recompras.DatosRaros:
        ok(True, "Listado sin comunicados de recompra: DatosRaros")

# --- Maquetas vistas en la pasada real del 19/11/2026 (ejecución 44466038203) -------------------------------
# IAG del 02/11: fecha inglesa pero cifras en español (miles con punto, decimales con coma).
IAG_ES = """
    26-Oct-26            LON                 807.864                   £ 4,091
    26-Oct-26           MAD                  540.592                   € 4,868
    27-Oct-26            LON                 806.172                   £ 4,102
Se acompaña a este anuncio un desglose completo de las operaciones individuales
"""
f = filas.leer_filas(IAG_ES)
ok(len(f) == 3 and f[0]["acciones"] == 807864 and abs(f[0]["precio"] - 4.091) < 1e-9 and f[0]["moneda"] == "GBP", "IAG (02/11): fecha inglesa con cifras españolas: las cifras mandan")
ok(f[1]["acciones"] == 540592 and abs(f[1]["precio"] - 4.868) < 1e-9 and f[1]["moneda"] == "EUR", "IAG (02/11): fila en euros")

# Endesa: mes abreviado en español con punto (28-oct.-26) y total de la semana en una frase.
ENDESA = """
                  28-oct.-26            ELE.MC              Compra               AQEU                2.080              42,9351
                  28-oct.-26            ELE.MC              Compra               CEUX                6.158              42,9456
                  28-oct.-26            ELE.MC              Compra               TQEX                1.095              42,9516
                  28-oct.-26            ELE.MC              Compra               XMAD                10.510             42,9379
 El número total de acciones compradas asciende a 19.843 acciones a un precio medio de
 42,94€/acción.
 Se acompaña como anexo información detallada sobre cada una de las operaciones realizadas durante
                                                                     ANEXO
                  28-oct.-26            ELE.MC              Compra               XMAD                500             42,9000
"""
f = filas.leer_filas(ENDESA)
ok(len(f) == 4 and f[0]["fecha"] == "2026-10-28" and f[0]["acciones"] == 2080 and abs(f[0]["precio"] - 42.9351) < 1e-9, "Endesa: fecha 28-oct.-26 y cifras españolas")
ok(filas.resumen(f)["acciones"] == 19843 == filas.totales_declarados(ENDESA)[0], "Endesa: la frase «el número total de acciones compradas asciende a 19.843 acciones» vale como total declarado")
pr = recompras.resumen_programa(ENDESA)
ok(pr["acciones_programa"] is None, "Endesa: el total de la semana no se confunde con el acumulado del programa")

# ArcelorMittal: inglés, sin centro de negociación, miles con espacio, detalle con hora.
ARCELOR = """
Purchases of own shares on 26th October 2026
Aggregate presentation by day and market
                                 ARCELORMITTAL   2EULGUTUI56JI9SAL165        26/10/2026              LU1598757687                      17 271                  53.1968
Rounded to two digits after the decimal point                                                            TOTAL                         17 271                    53.20
Detail transaction by transaction
                                 ARCELORMITTAL   2EULGUTUI56JI9SAL165          Natixis         KX1WK48MPD4Y2NCUIZ63             26/10/2026 09:00:39         LU1598757687        XPAR     300     53.10
Purchases of own shares on 27th October 2026
                                 ARCELORMITTAL   2EULGUTUI56JI9SAL165        27/10/2026              LU1598757687                      16 500                  52.9000
"""
f = filas.leer_filas(ARCELOR)
ok(len(f) == 2 and f[0]["centro"] == "n/d" and f[0]["acciones"] == 17271 and abs(f[0]["precio"] - 53.1968) < 1e-9, "ArcelorMittal: fila con ISIN y sin centro; miles con espacio; precio con punto")
ok(f[1]["acciones"] == 16500 and f[1]["fecha"] == "2026-10-27", "ArcelorMittal: segundo día")
ok(filas.totales_declarados(ARCELOR) == [17271], "ArcelorMittal: TOTAL con miles por espacio")
ok(all(not x["detalle"] for x in f) and len(filas.leer_filas(ARCELOR, solo_primera_tabla=False)) == 3, "ArcelorMittal: la fila con hora es detalle y queda fuera del resumen")

# Fluidra: comunicado de extensión, sin tabla; acumulado del programa en el texto.
FLUIDRA = ("Conforme al Plan Global, el número máximo de acciones a adquirir al amparo del Programa de Recompra continúa fijado en 500.000 acciones de Fluidra, "
           "representativas de aproximadamente el 0,26% del capital social de la Sociedad, de las que ya se han adquirido 222.878 acciones hasta el día 15 de octubre de 2026 (incluido), "
           "y el importe monetario máximo asignado al Programa de Recompra continúa siendo de 12,5 millones de euros, habiéndose alcanzado un importe de 4.812.981 euros hasta el día 15 de octubre de 2026 (incluido).")
pr = recompras.resumen_programa(FLUIDRA)
ok(pr["importe_programa_eur"] == 4812981.0 and pr["acciones_programa"] == 222878 and pr["pct_programa"] is None, "Fluidra: acumulado del programa en un comunicado de extensión")
ok(filas.leer_filas(FLUIDRA) == [], "Fluidra: sin filas")
ok(abs(filas._numero("54.61", "es") - 54.61) < 1e-9 and abs(filas._numero("42,9351", "en") - 42.9351) < 1e-9 and filas._numero("17 271") == 17271 and filas._numero("1,143,996.50", "es") == 1143996.5, "Números: decimal evidente, miles con espacio, dos separadores")

# Caso de control de la serie semanal frente a pandas.
try:
    import pandas as pd
    df = pd.DataFrame(ops)
    df = df[df["operacion"] == "compra"].copy()
    df["acciones"] = df["acciones"].astype(int)
    df["lunes"] = pd.to_datetime(df["fecha"]).dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    ref = df.groupby("lunes")["acciones"].sum().to_dict()
    ok({s["semana"]: s["acciones"] for s in recompras.serie_semanal(ops)} == ref, "Control: acciones por semana igual que pandas (periodos W-SUN)")
except ImportError:
    print("aviso: pandas no disponible, control de referencia omitido")

print(f"{TOTAL - len(FALLOS)}/{TOTAL} comprobaciones superadas")
sys.exit(1 if FALLOS else 0)
