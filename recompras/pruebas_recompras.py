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

print(f"{TOTAL - len(FALLOS)}/{TOTAL} comprobaciones superadas")
sys.exit(1 if FALLOS else 0)
