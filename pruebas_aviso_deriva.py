# -*- coding: utf-8 -*-
"""
Pruebas del aviso de deriva, con datos sintéticos y sin red.

QUÉ SE COMPRUEBA Y POR QUÉ CADA COSA:

  1. Un tramo publicado que el recálculo contradice se detecta. Es el aviso
     que importa editorialmente.
  2. Una deriva grande que NO cambia el tramo no se señala como cruce. Si no,
     el aviso se dispararía con cualquier vaivén dentro de un tramo ancho y
     dejaría de leerse.
  3. Las filas provisionales no cuentan como cruce: cambiar es su razón de
     existir.
  4. El récord de deriva se mide solo sobre la versión en curso. Comparar el
     8,87 de la 0.9.0 con el 10,14 de la 0.10.0 es comparar dos reglas
     distintas.
  5. La migración del registro añade la columna sin tocar ninguna cifra, y
     etiqueta cada fila con la versión que deducen las fotos archivadas.
  6. avisar_deriva se calla cuando no hay cruce y la deriva no es récord, y
     habla cuando lo es.
  7. Sobre el revisiones.csv REAL del repositorio, la migración reproduce el
     etiquetado que se hizo a mano contra el historial de git, deja las cinco
     columnas publicadas byte a byte, es idempotente y deja el récord de la
     versión en curso disponible desde la primera ejecución.

Ejecución:
    python pruebas_aviso_deriva.py
"""
import json
import os
import shutil
import tempfile

import pandas as pd

import config
import publicar_diario as pub

fallos = []


def comprobar(condicion: bool, titulo: str, detalle: str = "") -> None:
    if condicion:
        print(f"  OK   {titulo}")
    else:
        print(f"  FALLA {titulo}  {detalle}")
        fallos.append(titulo)


def serie(filas: list[tuple]) -> pd.DataFrame:
    """filas: (fecha, ifg, tramo, estado)."""
    idx = pd.to_datetime([f[0] for f in filas])
    return pd.DataFrame({"ifg": [f[1] for f in filas],
                         "tramo": [f[2] for f in filas],
                         "estado": [f[3] for f in filas]}, index=idx)


# --- 1, 2 y 3: cruces de tramo ---------------------------------------------
print("\n1-3. Cruces de tramo")

final = serie([
    ("2026-10-13", 72.23, "Tensión", pub.DEFINITIVO),   # se queda en Tensión
    ("2026-10-14", 63.13, "Tensión", pub.DEFINITIVO),   # deriva grande, mismo tramo
    ("2026-10-16", 50.20, "Tensión", pub.DEFINITIVO),   # cruza a Normal
    ("2026-10-19", 44.25, "Normal",  pub.PROVISIONAL),  # abierta: no cuenta
])
recalculada = serie([
    ("2026-10-13", 70.00, "Tensión", pub.DEFINITIVO),
    ("2026-10-14", 53.00, "Tensión", pub.DEFINITIVO),   # -10,13 puntos
    ("2026-10-16", 49.10, "Normal",  pub.DEFINITIVO),   # -1,10 y cambia tramo
    ("2026-10-19", 38.00, "Normal",  pub.DEFINITIVO),
])

cruces = pub.cruces_de_tramo(final, recalculada)
comprobar(len(cruces) == 1, "detecta un solo cruce", f"detecta {len(cruces)}")
comprobar(list(cruces.index.strftime("%Y-%m-%d")) == ["2026-10-16"],
          "el cruce es el 2026-10-16", str(list(cruces.index)))
if len(cruces):
    f = cruces.iloc[0]
    comprobar(f["tramo_publicado"] == "Tensión"
              and f["tramo_recalculado"] == "Normal",
              "registra los dos tramos",
              f"{f['tramo_publicado']} -> {f['tramo_recalculado']}")
comprobar(pd.Timestamp("2026-10-14") not in cruces.index,
          "una deriva de 10 puntos dentro del mismo tramo no es cruce")
comprobar(pd.Timestamp("2026-10-19") not in cruces.index,
          "una fila provisional no es cruce")

# La frontera la ponen los tramos publicados, no una cifra escrita aquí.
comprobar([t[2] for t in config.TRAMOS].count("Tensión") == 1,
          "los tramos salen de config.TRAMOS")

# --- 4, 5 y 6: récord y registro -------------------------------------------
print("\n4-6. Récord de deriva, migración y aviso")

tmp = tempfile.mkdtemp()
rev_real, aviso_real = pub.REVISIONES, pub.RUTA_AVISO_DERIVA
hist_real = pub.DIR_HISTORICO
try:
    pub.REVISIONES = os.path.join(tmp, "revisiones.csv")
    pub.RUTA_AVISO_DERIVA = os.path.join(tmp, "aviso_deriva.json")

    # Caso «primer día de una versión nueva»: todas las filas heredadas son
    # de la versión anterior, porque la foto archivada de esa versión es
    # posterior a ellas. No hay base de la versión en curso.
    pub.DIR_HISTORICO = os.path.join(tmp, "historico")
    os.makedirs(pub.DIR_HISTORICO)
    with open(os.path.join(pub.DIR_HISTORICO, "ifg_0.9.0.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"version": "0.9.0",
                   "generado": "2026-10-19T03:45:30+02:00"}, fh)

    # Registro heredado: cabecera vieja, sin columna de versión.
    with open(pub.REVISIONES, "w", encoding="utf-8") as fh:
        fh.write("ejecutado,sesiones_comparadas,deriva_maxima,fecha_peor,"
                 "sesiones_movidas\n")
        fh.write("2026-10-14T03:41:55+02:00,4290,8.8700,2026-10-12,199\n")
        fh.write("2026-10-19T03:45:30+02:00,4294,0.1200,2026-10-16,5\n")

    comprobar(pd.isna(pub.deriva_maxima_registrada()),
              "sin columna de versión no hay referencia de récord")

    pub.migrar_revisiones()
    reg = pd.read_csv(pub.REVISIONES)
    comprobar("version" in reg.columns, "la migración añade la columna")
    comprobar(len(reg) == 2 and float(reg["deriva_maxima"].max()) == 8.87,
              "la migración no toca ninguna cifra",
              str(reg["deriva_maxima"].tolist()))
    comprobar(reg["version"].astype(str).tolist() == ["0.9.0", "0.9.0"],
              "las filas heredadas llevan la versión con que se midieron",
              str(reg["version"].tolist()))
    comprobar(pd.isna(pub.deriva_maxima_registrada()),
              "las filas de otra versión no cuentan para el récord")

    # Primera deriva de esta versión: 10,14, pero SIN base con la que
    # comparar. No se declara récord: si se declarara, el primer día de una
    # versión nueva saltaría una alerta falsa. Avisa por el cruce de tramo,
    # que es el disparador que sí funciona desde la primera ejecución.
    deriva = pd.Series({pd.Timestamp("2026-10-14"): -10.14,
                        pd.Timestamp("2026-10-13"): 2.0})
    previo = pub.deriva_maxima_registrada()
    pub.anotar_revision(deriva, "2026-10-20T03:46:49+02:00")
    aviso = pub.avisar_deriva(deriva, pub.cruces_de_tramo(final, recalculada),
                              previo, "2026-10-20T03:46:49+02:00")
    comprobar(aviso["es_record"] is False,
              "sin base comparable no se declara récord")
    comprobar(aviso["sin_base_comparable"] is True,
              "y se deja dicho que no había base")
    comprobar(aviso["avisar"] is True, "avisa igual, por el cruce de tramo")
    comprobar(aviso["version"] == config.VERSION,
              "la fila nueva lleva la versión en curso")
    comprobar(os.path.exists(pub.RUTA_AVISO_DERIVA), "escribe el marcador")
    with open(pub.RUTA_AVISO_DERIVA, encoding="utf-8") as fh:
        comprobar(json.load(fh)["deriva_maxima"] == 10.14,
                  "el marcador lleva la deriva medida")

    comprobar(pub.deriva_maxima_registrada() == 10.14,
              "ahora el récord de la versión es 10,14",
              str(pub.deriva_maxima_registrada()))

    # Deriva menor y sin cruces: ni récord ni aviso.
    floja = pd.Series({pd.Timestamp("2026-10-13"): 1.5})
    sin_cruces = pub.cruces_de_tramo(final, final.assign(ifg=final["ifg"]))
    aviso2 = pub.avisar_deriva(floja, sin_cruces,
                               pub.deriva_maxima_registrada(),
                               "2026-10-21T03:46:00+02:00")
    comprobar(aviso2["es_record"] is False, "1,5 no es récord frente a 10,14")
    comprobar(aviso2["avisar"] is False,
              "sin cruce y sin récord no se avisa: el aviso no se gasta")

    # Con base ya anotada (10,14), una deriva mayor sí es récord, y avisa
    # aunque no cruce ningún tramo: es el caso del 20 de octubre de 2026.
    mayor = pd.Series({pd.Timestamp("2026-10-14"): -12.5})
    aviso_rec = pub.avisar_deriva(mayor, sin_cruces,
                                  pub.deriva_maxima_registrada(),
                                  "2026-10-23T03:46:00+02:00")
    comprobar(aviso_rec["es_record"] is True,
              "12,5 es récord frente a 10,14")
    comprobar(aviso_rec["avisar"] is True and not aviso_rec["cruces_de_tramo"],
              "una deriva sin precedentes avisa sin cruzar tramo")

    # Una deriva que cruza tramo avisa aunque no sea récord.
    aviso3 = pub.avisar_deriva(floja, cruces, 10.14,
                               "2026-10-22T03:46:00+02:00")
    comprobar(aviso3["avisar"] is True and aviso3["es_record"] is False,
              "un cruce de tramo avisa por sí solo")
    comprobar(len(aviso3["cruces_de_tramo"]) == 1
              and aviso3["cruces_de_tramo"][0]["fecha"] == "2026-10-16",
              "el marcador detalla el cruce")

    # --- 7: el registro real del repositorio ---------------------------------
    print("\n7. Migración del revisiones.csv real")
    pub.DIR_HISTORICO = hist_real
    with open(rev_real, encoding="utf-8") as fh:
        lineas = fh.read().splitlines()
    # Si el archivo real ya está migrado (después de fusionar esto), se le
    # quita la sexta columna para probar la migración desde el original.
    if lineas[0].strip() == pub.CABECERA_REVISIONES:
        lineas = [",".join(l.split(",")[:5]) for l in lineas]
    original = "\n".join(lineas) + "\n"
    with open(pub.REVISIONES, "w", encoding="utf-8") as fh:
        fh.write(original)

    pub.migrar_revisiones()
    with open(pub.REVISIONES, encoding="utf-8") as fh:
        migrado = fh.read()
    filas_m = migrado.splitlines()

    comprobar(filas_m[0] == pub.CABECERA_REVISIONES, "cabecera nueva")
    comprobar("\n".join(",".join(l.split(",")[:5]) for l in filas_m) + "\n"
              == original,
              "las cinco columnas publicadas quedan byte a byte")

    # Etiquetado hecho a mano el 20 de octubre de 2026 contra el historial
    # de git (la republicación a la 0.10.0 es del 18 de octubre). Lo que
    # deduce el código tiene que coincidir fila a fila.
    a_mano = {
        "2026-10-13T03:35:21+02:00": "0.9.0",
        "2026-10-14T03:41:55+02:00": "0.9.0",
        "2026-10-15T03:44:07+02:00": "0.9.0",
        "2026-10-16T03:43:24+02:00": "0.9.0",
        "2026-10-19T03:45:30+02:00": "0.10.0",
        "2026-10-20T03:46:49+02:00": "0.10.0",
        "2026-10-21T03:47:33+02:00": "0.10.0",
        "2026-10-22T03:47:05+02:00": "0.10.0",
        "2026-10-23T03:49:55+02:00": "0.10.0",
    }
    deducido = {l.split(",")[0]: l.split(",")[5] for l in filas_m[1:]}
    discrepan = [k for k, v in a_mano.items() if deducido.get(k) != v]
    comprobar(not discrepan, "reproduce el etiquetado hecho a mano",
              str(discrepan))
    posteriores = [v for k, v in deducido.items() if k not in a_mano
                   and pd.Timestamp(k) > pd.Timestamp("2026-10-23T03:49:55+02:00")]
    comprobar(all(v == config.VERSION for v in posteriores),
              "las ejecuciones posteriores llevan la versión en curso",
              str(posteriores))
    comprobar(all(deducido.values()), "ninguna fila real queda sin versión")

    pub.migrar_revisiones()
    with open(pub.REVISIONES, encoding="utf-8") as fh:
        comprobar(fh.read() == migrado, "migrar dos veces no cambia nada")

    comprobar(pub.deriva_maxima_registrada() == 10.14,
              "el récord de la versión en curso existe desde el primer día",
              str(pub.deriva_maxima_registrada()))

    # Una marca ilegible o sin zona horaria no se atribuye a ninguna versión.
    comprobar(pub.version_de_cada_ejecucion(["basura", "2026-10-20T03:00:00"])
              == ["", ""], "una marca ilegible o sin zona queda sin versión")
finally:
    pub.REVISIONES, pub.RUTA_AVISO_DERIVA = rev_real, aviso_real
    pub.DIR_HISTORICO = hist_real
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("TODO OK" if not fallos
               else f"{len(fallos)} FALLOS: {fallos}"))
raise SystemExit(1 if fallos else 0)
