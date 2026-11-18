# -*- coding: utf-8 -*-
"""
Publicación diaria del Índice de Fricción Global.

Lo ejecuta GitHub Actions cada día hábil de madrugada. Recalcula la serie
completa y escribe en docs/, que GitHub Pages sirve como URL pública:

    ifg.json            el valor del día y sus dos motores. Lo lee Make.
    ifg_serie.csv       la serie histórica entera. Dato abierto.
    ifg_serie_12m.json  los últimos doce meses en formato compacto, para el
                        gráfico del panel de la web.
    revisiones.csv      cuánto se separa el recálculo de lo ya publicado.

POR QUÉ DE MADRUGADA Y NO A LAS 8:30. La especificación original fijaba las
8:30 CET, pero el pipeline editorial que genera "Antes de la apertura" corre
sobre las 5:00. Publicando después, el texto de cada mañana citaría siempre
el valor de la víspera. Publicar a las 3:30 además es MÁS fiel al criterio
de la propia especificación —hora de corte coherente con el cierre de Wall
Street del día anterior—, porque el índice queda fijado antes de que abra
ningún mercado europeo y no mezcla sesiones.

POR QUÉ RECALCULA TODO CADA DÍA en vez de añadir solo la fila nueva: los
z-scores necesitan la ventana de 750 sesiones y la escala necesita la sigma
expansiva.

LA SERIE PUBLICADA ES INMUTABLE. Esta es la regla que gobierna el archivo y
hay que entender por qué existe. El recálculo diario NO reproduce
exactamente lo publicado ayer, y no por un fallo: backfill_gdelt.py recorre
todo el rango y recupera los ficheros que en su día no estaban disponibles,
de modo que una ejecución puede insertar una muestra de GDELT con fecha
pasada. Como la serie semanal se arrastra hacia delante, esa muestra mueve
los valores diarios desde esa fecha. El 12 de octubre de 2026 se observó en
vivo: el valor del viernes 9 pasó de 63,41 a 63,69 entre dos ejecuciones del
mismo día.

Un índice que aspira a ser citable no puede permitirse eso. Así que el
recálculo se usa SOLO para las fechas que todavía no se han publicado; las
filas que ya están en docs/ifg_serie.csv se conservan intactas. La deriva
entre lo que saldría hoy y lo que se publicó en su día no se esconde: se
mide en cada ejecución y se escribe en docs/revisiones.csv, que es público.
Esa es la política de revisiones del índice y debe figurar en la
metodología.

Y DESDE AHORA SE AVISA, no solo se anota. Medir la deriva y dejarla en un CSV
no es vigilarla: nadie entra a mirar el CSV de un flujo que lleva meses
saliendo bien. Cuando la deriva contradice un tramo ya publicado, o cuando es
mayor que cualquiera registrada bajo esta versión, avisar_deriva() lo escribe
en un marcador que el flujo convierte en una incidencia. No detiene la
publicación: un dato cerrado sigue siendo inmutable. Solo deja de moverse el
pasado a oscuras.

LÍMITE CONOCIDO DE ESTA REGLA. El valor, la variación y el tramo quedan
congelados. El desglose por componentes que acompaña al día (los "motores"
de ifg.json y el desglose_nivel del panel) se recalcula, porque la serie de
contribuciones no se guarda. Es información descriptiva, la deriva observada
está muy por debajo de la décima, y congelarla exigiría guardar las once
contribuciones de cada sesión. Queda anotado como deuda, no como fallo
oculto.

GUARDIA HORARIA. GitHub Actions solo entiende UTC y España cambia de hora dos
veces al año, así que el flujo se dispara dos veces y este script se planta
salvo que en Madrid sea la madrugada. Se acepta una VENTANA de dos horas en
vez de una hora exacta, porque las tareas programadas de GitHub se retrasan
con frecuencia y un retraso de media hora no puede impedir la publicación
del día. Que la ventana admita las dos ejecuciones en verano no duplica
nada: la segunda encuentra la fila de hoy en el registro y se planta. Y aun
forzándola, la regla de inmutabilidad hace que no cambie ningún valor ya
publicado.

Uso:
    python publicar_diario.py            # con guardia horaria
    python publicar_diario.py --ahora    # sin guardia, para probar
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config, fuentes, indice                     # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("publicar")

DIR_PUBLICO = "docs"
RUTA_SERIE = f"{DIR_PUBLICO}/ifg_serie.csv"
REGISTRO = f"{DIR_PUBLICO}/registro_publicaciones.csv"
REVISIONES = f"{DIR_PUBLICO}/revisiones.csv"
DIR_HISTORICO = f"{DIR_PUBLICO}/historico"    # fotos archivadas al republicar
VENTANA_PUBLICACION = (3, 5)      # horas locales de Madrid: vale las 3 y las 4
ZONA = ZoneInfo("Europe/Madrid")

# Sesiones que se publican en el archivo compacto del panel. Doce meses de
# bolsa son unas 256 sesiones; se dejan 260 por margen.
SESIONES_PANEL = 260

# Columnas de la serie pública, en orden.
COLUMNAS = ["ifg", "ifg_suavizado", "variacion", "tramo", "cobertura", "parcial"]

# El archivo de componentes NO va en DIR_PUBLICO. GitHub Pages sirve ese
# directorio entero, y este archivo es la versión estandarizada, sesión a
# sesión, de los precios de origen: un derivado directo de datos de terceros
# cuyas licencias están sin resolver (cambio P3 de la revisión de cumplimiento
# del 27-10-2026). Se sigue archivando, porque es la única prueba de con qué
# se calculó cada día, pero deja de ofrecerse como descarga.
#
# Queda pendiente, y no se decide aquí: llevarlo a un sitio privado de verdad
# —el repositorio es público—, añadir la desviación típica de escala de cada
# día y archivar la fila definitiva en vez de la provisional cuando un
# provisional se cierra. Eso es de Federico y Tecnología.
RUTA_COMPONENTES = "datos/componentes.csv"
CORRECCIONES = f"{DIR_PUBLICO}/correcciones.csv"

# Marcador que lee el flujo para decidir si abre una incidencia por deriva.
#
# VA EN LA RAÍZ Y NO EN docs/ A PROPÓSITO. No es un dato publicado, es una
# señal interna de una ejecución para el paso siguiente del mismo flujo. El
# paso que guarda el resultado solo añade docs/ y datos/, así que este
# archivo nunca llega al repositorio, que es exactamente lo que se quiere:
# el aviso vive en la incidencia, no en el histórico.
RUTA_AVISO_DERIVA = "aviso_deriva.json"

# Sesiones que un valor incompleto sigue abierto a corrección.
#
# POR QUÉ CINCO. Cubre los dos plazos reales de las fuentes: una caída de
# precios se resuelve en uno o dos días hábiles, y GDELT publica su muestra
# semanal dentro de los siete naturales siguientes. Más ventana no recupera
# casi nada y retrasa el cierre; menos deja fuera la mitad de los casos.
VENTANA_PROVISIONAL = 5

# Estados posibles de una fila publicada.
#   definitivo             cobertura completa; no se vuelve a tocar jamás
#   provisional            le falta algún componente y aún está dentro de la
#                          ventana: se recalcula cada madrugada por si la
#                          fuente vuelve
#   definitivo_incompleto  salió de la ventana sin completarse. Se cierra con
#                          la marca puesta: el dato nunca llegó y se dice.
DEFINITIVO = "definitivo"
PROVISIONAL = "provisional"
INCOMPLETO = "definitivo_incompleto"


def ya_publicado_hoy() -> bool:
    """¿Hay ya una fila de hoy en el registro de publicaciones?"""
    if not os.path.exists(REGISTRO):
        return False
    hoy = datetime.now(ZONA).date().isoformat()
    try:
        with open(REGISTRO, encoding="utf-8") as fh:
            return any(linea.startswith(hoy) for linea in fh)
    except OSError:
        return False


def toca_publicar() -> bool:
    ahora = datetime.now(ZONA)
    if ahora.weekday() >= 5:
        log.info("Fin de semana en Madrid (%s). No se publica.", ahora.date())
        return False
    if not VENTANA_PUBLICACION[0] <= ahora.hour < VENTANA_PUBLICACION[1]:
        log.info("En Madrid son las %02d:%02d, fuera de la ventana de "
                 "publicación (%02d:00-%02d:00). Esta ejecución no toca.",
                 ahora.hour, ahora.minute, *VENTANA_PUBLICACION)
        return False
    if ya_publicado_hoy():
        log.info("Ya hay una publicación registrada hoy. No se repite.")
        return False
    return True


def leer_serie_publicada() -> pd.DataFrame | None:
    """La serie tal y como quedó publicada en la ejecución anterior."""
    if not os.path.exists(RUTA_SERIE):
        return None
    try:
        previo = pd.read_csv(RUTA_SERIE, index_col=0, parse_dates=True)
    except Exception as e:                       # archivo corrupto o vacío
        log.warning("No se puede leer la serie publicada (%s). Se trata esta "
                    "ejecución como la primera.", e)
        return None
    if previo.empty:
        return None
    return previo


def sellar_foto(ultimo: dict, generado: str,
                revisiones: str | None = None) -> dict:
    """
    Pone en la foto del día las claves que no vienen del cálculo: licencia,
    aviso legal, estado del índice, política de revisiones y sello temporal.

    POR QUÉ ES UNA FUNCIÓN Y NO CUATRO LÍNEAS SUELTAS. Estaban escritas a mano
    aquí, y cuando republicar_version.py pasó a escribir también ifg.json se
    quedó sin ellas: la republicación de la 0.10.0 publicó un JSON sin
    'licencia', sin 'aviso' y sin 'estado'. El plugin de la web lee
    'licencia', y 'aviso' es el encuadre legal, que no es opcional. Un dato
    duplicado a mano en dos sitios se desincroniza siempre; en cuanto hay dos
    caminos de escritura, esto tiene que vivir en uno solo.

    'revisiones' se puede sobrescribir, porque la republicación por cambio de
    versión tiene que contar otra cosa que la publicación diaria.
    """
    # P2 de la revisión de cumplimiento del 27-10-2026. La CC BY 4.0 nunca
    # pudo cubrir los precios de terceros de los que salen ocho de los once
    # componentes (cl. 1: solo se licencia lo que el licenciante puede
    # licenciar). Se deja de ofrecer para lo que se publique desde ahora; es
    # irrevocable para quien ya recibió la serie con ella, así que no se
    # «suspende», y la fe de erratas de la metodología lo explica.
    ultimo["licencia"] = ("Consulta y cita. Sin licencia de reutilización "
                          "comercial ni de redistribución. Ver "
                          "https://elespeculador.com/indices/friccion-global/"
                          "#ifg-licencia")
    ultimo["aviso"] = ("Contenido informativo y educativo. No constituye "
                       "asesoramiento financiero ni recomendación de inversión.")
    # Fila 13 de la revisión: «índice de referencia» es un término definido
    # por el Reglamento (UE) 2016/1011 y el JSON contradecía a la ficha, que
    # dice que sí puede citarse. Lo que está en validación son las reglas.
    ultimo["estado"] = ("preliminar: reglas congeladas, índice en validación "
                        "prospectiva")
    ultimo["revisiones"] = revisiones or (
        "Un valor definitivo no se revisa nunca. Un valor provisional —al que "
        f"le falta algún componente— queda abierto {VENTANA_PROVISIONAL} "
        "sesiones por si la fuente vuelve, y toda corrección aplicada se "
        "publica en correcciones.csv. La deriva observada entre el recálculo "
        "y lo ya cerrado se publica en revisiones.csv.")
    ultimo["generado"] = generado
    return ultimo


def comprobar_version() -> bool:
    """
    La versión del código tiene que coincidir con la de la serie publicada.

    POR QUÉ ESTA GUARDIA EXISTE. Si se sube VERSION y se cambian reglas sin
    republicar la serie, el flujo diario NO falla, y eso es lo peligroso:
    fusionar() conserva intactas las filas ya cerradas y añade la nueva
    calculada con las reglas nuevas. El resultado es una serie mezclada —el
    pasado con una fórmula y el presente con otra— publicada en silencio,
    mientras ifg.json anuncia la versión nueva como si toda la serie fuera de
    esa versión. Es peor que una caída: una caída se ve.

    verificar_estabilidad.py no lo caza, y es correcto que no lo cace: su
    trabajo es comprobar que lo publicado no cambia, y aquí no cambia. El que
    tiene que negarse a publicar es este script.

    La deriva medida sí daría un salto enorme y quedaría en revisiones.csv,
    pero eso es un rastro para la autopsia, no una barrera.

    Cuando los números no coinciden, la salida NO es saltarse la guardia: es
    ejecutar el flujo de republicación, que archiva la serie anterior,
    recalcula la completa y declara la discontinuidad.
    """
    ruta = f"{DIR_PUBLICO}/ifg.json"
    if not os.path.exists(ruta):
        return True                      # primera publicación: nada que comparar
    try:
        with open(ruta, encoding="utf-8") as fh:
            publicada = str(json.load(fh).get("version", "")).strip()
    except Exception as e:               # noqa: BLE001
        log.warning("No se puede leer la versión de %s (%s). Se continúa.",
                    ruta, e)
        return True
    if not publicada or publicada == config.VERSION:
        return True

    log.error("DESAJUSTE DE VERSIÓN. El código es %s y la serie publicada es "
              "%s.", config.VERSION, publicada)
    log.error("No se publica. Publicar ahora dejaría una serie mezclada: el "
              "pasado con las reglas de %s y las sesiones nuevas con las de "
              "%s.", publicada, config.VERSION)
    log.error("Para resolverlo, ejecuta el flujo 'Republicar version' con "
              "--version-anterior %s. Archivará la serie actual, recalculará "
              "la completa y declarará la discontinuidad.", publicada)
    return False


def estado_de(cobertura: float, dentro_ventana: bool) -> str:
    """El estado que le toca a una fila según su cobertura y su antigüedad."""
    if cobertura >= 0.9999:
        return DEFINITIVO
    return PROVISIONAL if dentro_ventana else INCOMPLETO


def fusionar(recalculada: pd.DataFrame,
             publicada: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.Series, list]:
    """
    Funde el recálculo con lo ya publicado respetando el estado de cada fila.

    LA REGLA, Y POR QUÉ ES ASÍ. Hasta ahora había una sola norma —lo publicado
    no se toca— y eso resultó ser demasiado rígido en un caso concreto: los
    días 9 y 12 de octubre de 2026 una fuente se cayó, el índice se calculó
    sin un componente y esos dos valores degradados quedaron congelados para
    siempre. La inmutabilidad protegía un dato que no merecía protección.

    La norma pasa a ser la de las estadísticas oficiales: un dato nace
    provisional y se vuelve definitivo cuando está completo.

      - Cobertura completa  -> definitivo, intocable para siempre.
      - Cobertura incompleta y dentro de la ventana -> provisional: se
        recalcula cada madrugada por si la fuente volvió.
      - Cobertura incompleta y fuera de la ventana -> se cierra como
        definitivo incompleto, con la marca puesta.

    Lo que NO cambia es lo esencial: un valor definitivo no se mueve nunca.
    La inmutabilidad sigue entera donde importa, que es donde el lector cita.

    Devuelve la serie final, la deriva medida SOLO sobre filas definitivas
    —que es la que de verdad informa de si el pasado se mueve— y la lista de
    correcciones aplicadas a provisionales.
    """
    # Las últimas sesiones del recálculo son la ventana abierta.
    ventana = set(recalculada.index[-VENTANA_PROVISIONAL:])

    def estados(df: pd.DataFrame) -> pd.Series:
        return pd.Series(
            [estado_de(float(c), f in ventana) for f, c in df["cobertura"].items()],
            index=df.index, name="estado")

    if publicada is None:
        log.info("No hay serie previa: se publica el recálculo entero (%d "
                 "sesiones).", len(recalculada))
        nueva = recalculada.copy()
        nueva["estado"] = estados(nueva)
        return nueva, pd.Series(dtype=float), []

    # Compatibilidad con la serie anterior, que no tenía columna de estado:
    # todo lo que había se considera cerrado, que es como se publicó.
    if "estado" not in publicada.columns:
        publicada = publicada.copy()
        publicada["estado"] = [
            DEFINITIVO if float(c) >= 0.9999 else INCOMPLETO
            for c in publicada["cobertura"]]
        log.info("La serie publicada no traía columna de estado. Se marcan sus "
                 "%d filas como cerradas, que es como se publicaron.",
                 len(publicada))

    firmes = publicada[publicada["estado"] != PROVISIONAL]
    abiertas = publicada.index[publicada["estado"] == PROVISIONAL]

    # Deriva: solo sobre lo cerrado. Es la cifra que responde a "¿se mueve el
    # pasado?". Incluir los provisionales la ensuciaría con lo que sí tiene
    # permiso para moverse.
    # Desde la 0.10.0 se mide sobre "ifg", que es el valor oficial. Antes se
    # medía sobre el suavizado porque el suavizado era el titular.
    comunes = firmes.index.intersection(recalculada.index)
    deriva = (recalculada.loc[comunes, "ifg"]
              - firmes.loc[comunes, "ifg"]).dropna()

    # Correcciones: provisionales que el recálculo mejora.
    correcciones = []
    rehechas = []
    for f in abiertas:
        if f not in recalculada.index:
            continue
        antes, ahora = publicada.loc[f], recalculada.loc[f]
        fila = ahora.copy()
        fila["estado"] = estado_de(float(ahora["cobertura"]), f in ventana)
        rehechas.append(fila)
        if abs(float(ahora["ifg"]) - float(antes["ifg"])) > 0.005:
            correcciones.append({
                "fecha": str(f.date()),
                "valor_anterior": round(float(antes["ifg"]), 2),
                "valor_nuevo": round(float(ahora["ifg"]), 2),
                "cobertura_anterior": round(float(antes["cobertura"]), 3),
                "cobertura_nueva": round(float(ahora["cobertura"]), 3),
                "estado_nuevo": fila["estado"],
            })

    partes = [firmes]
    if rehechas:
        partes.append(pd.DataFrame(rehechas))
    nuevas = recalculada.index.difference(publicada.index)
    if len(nuevas):
        bloque = recalculada.loc[nuevas].copy()
        bloque["estado"] = estados(bloque)
        partes.append(bloque)

    final = pd.concat(partes).sort_index()
    final = final[~final.index.duplicated(keep="last")]

    log.info("Fusión: %d cerradas intactas, %d provisionales revisadas, "
             "%d nuevas.", len(firmes), len(rehechas), len(nuevas))
    for c in correcciones:
        log.warning("CORREGIDO %s: %.2f -> %.2f (cobertura %.3f -> %.3f, ahora %s)",
                    c["fecha"], c["valor_anterior"], c["valor_nuevo"],
                    c["cobertura_anterior"], c["cobertura_nueva"], c["estado_nuevo"])
    abiertas_fin = int((final["estado"] == PROVISIONAL).sum())
    if abiertas_fin:
        log.info("Quedan %d sesiones provisionales abiertas a corrección.",
                 abiertas_fin)
    if len(deriva) and deriva.abs().max() > 0.005:
        peor = deriva.abs().idxmax()
        log.warning("El recálculo se separa de lo CERRADO hasta %.3f puntos "
                    "(%s). No se corrige: un valor cerrado es inmutable.",
                    deriva.abs().max(), peor.date())
    return final, deriva, correcciones


def anotar_correcciones(correcciones: list, generado: str) -> None:
    """
    Registro público de cada corrección aplicada a un provisional.

    Va en archivo propio y no en revisiones.csv porque son dos cosas
    distintas: revisiones mide cuánto se separaría el recálculo de lo
    publicado si lo aplicáramos, y esto anota lo que de verdad se cambió.
    Mezclarlas haría ilegibles las dos.
    """
    if not correcciones:
        return
    nuevo = not os.path.exists(CORRECCIONES)
    with open(CORRECCIONES, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write("ejecutado,fecha,valor_anterior,valor_nuevo,"
                     "cobertura_anterior,cobertura_nueva,estado_nuevo\n")
        for c in correcciones:
            fh.write(f"{generado},{c['fecha']},{c['valor_anterior']},"
                     f"{c['valor_nuevo']},{c['cobertura_anterior']},"
                     f"{c['cobertura_nueva']},{c['estado_nuevo']}\n")


def archivar_componentes(final: pd.DataFrame, res: dict) -> int:
    """
    Guarda los z-scores con los que se calculó cada día publicado.

    POR QUÉ HACE FALTA. Hoy nadie puede reproducir la serie partiendo de las
    fuentes, y no por un fallo: los datos de origen no son inmutables. Yahoo
    devuelve precios ajustados y reescribe su histórico en cada dividendo, y
    GDELT rellena huecos hacia atrás. Quien recalcule mañana obtendrá otros
    números, y sin este archivo no habrá forma de demostrar que los nuestros
    estaban bien.

    HASTA DÓNDE LLEGA, dicho con exactitud desde la fe de erratas del
    27-10-2026: con esta tabla NO se reconstruye la serie completa. La escala
    divide por una desviación típica expansiva que usa historia anterior a
    2010 y que no se publica, así que la reconstrucción solo funciona desde el
    3 de diciembre de 2012, con 3,5 puntos de diferencia media y 13,6 de
    máxima. Y cuando un provisional se cierra, la fila archivada conserva los
    componentes provisionales: la del 23-10-2026 da 50,49 y el definitivo es
    51,22. Sirve como prueba de con qué se calculó cada día, no como receta
    para reproducirlo.

    Se escribe con la misma regla que la serie: las filas ya cerradas no se
    tocan, las provisionales se refrescan y las nuevas se añaden.
    """
    comp = res["componentes"]
    if comp is None or comp.empty:
        return 0

    cerradas = final.index[final["estado"] != PROVISIONAL]
    previo = None
    if os.path.exists(RUTA_COMPONENTES):
        try:
            previo = pd.read_csv(RUTA_COMPONENTES, index_col=0, parse_dates=True)
        except Exception as e:
            log.warning("No se puede leer %s (%s). Se reescribe.",
                        RUTA_COMPONENTES, e)

    nuevo = comp.reindex(final.index)
    if previo is not None and not previo.empty:
        intocables = previo.index.intersection(cerradas)
        resto = nuevo.index.difference(intocables)
        nuevo = pd.concat([previo.loc[intocables], nuevo.loc[resto]]).sort_index()
        nuevo = nuevo[~nuevo.index.duplicated(keep="first")]

    nuevo.to_csv(RUTA_COMPONENTES, float_format="%.4f")
    return len(nuevo)


CABECERA_REVISIONES = ("ejecutado,sesiones_comparadas,deriva_maxima,"
                       "fecha_peor,sesiones_movidas,version")


def version_de_cada_ejecucion(marcas: list[str],
                               dir_historico: str = None) -> list[str]:
    """
    Con qué versión se hizo cada ejecución, deducido de lo que el propio
    sistema dejó escrito, no de una suposición.

    LA FUENTE. Cada republicación archiva en docs/historico/ la foto que
    estaba publicada justo antes de cambiar de reglas (ifg_<versión>.json).
    Esa foto lleva su versión y la marca «generado» de la última ejecución
    hecha con esas reglas, que es la misma marca que esa ejecución escribió
    como «ejecutado» en revisiones.csv. Así que la frontera entre versiones
    está registrada al segundo:

      - una ejecución cuya marca es igual o anterior a la de la foto
        archivada de la versión V, y posterior a la de la versión archivada
        previa, se hizo con V;
      - una ejecución posterior a la última foto archivada se hizo con la
        versión en curso (config.VERSION): la guardia de versión impide
        publicar si config.py y ifg.json no coinciden, y toda republicación
        archiva antes de tocar nada, así que no puede haber una versión
        intermedia sin rastro.

    Las marcas se comparan como instantes con su zona horaria, no como
    texto: el registro cruza el cambio de hora (+02:00 / +01:00).

    LÍMITE CONOCIDO. Una ejecución anterior a la foto archivada más antigua
    se atribuye a esa versión. Es exacto en este repositorio —la primera
    fila de revisiones.csv es del 13 de octubre de 2026, con la 0.9.0, y la
    0.9.0 es la versión archivada más antigua—, pero si alguna vez apareciera
    un registro de antes de que existiera el archivado, esa atribución no
    estaría demostrada. Una marca ilegible se deja sin versión.
    """
    dir_historico = dir_historico or DIR_HISTORICO
    fronteras = []
    if os.path.isdir(dir_historico):
        for nombre in os.listdir(dir_historico):
            if not (nombre.startswith("ifg_") and nombre.endswith(".json")):
                continue
            try:
                with open(os.path.join(dir_historico, nombre),
                          encoding="utf-8") as fh:
                    foto = json.load(fh)
                fronteras.append((pd.Timestamp(foto["generado"]),
                                  str(foto["version"])))
            except Exception as e:                              # noqa: BLE001
                log.warning("Foto archivada ilegible, se ignora: %s (%s)",
                            nombre, e)
    fronteras.sort()

    versiones = []
    for marca in marcas:
        try:
            t = pd.Timestamp(marca)
        except Exception:                                       # noqa: BLE001
            versiones.append("")
            continue
        if t.tzinfo is None:
            versiones.append("")
            continue
        v = next((ver for limite, ver in fronteras if t <= limite),
                 config.VERSION)
        versiones.append(v)
    return versiones


def migrar_revisiones() -> None:
    """
    Añade la columna de versión al registro de deriva si aún no la tiene.

    POR QUÉ HACÍA FALTA. Una deriva sin versión al lado no se puede
    interpretar: el 8,87 de la semana del 12 de octubre de 2026 se midió con
    las reglas de la 0.9.0 y no es comparable con el 10,14 de la 0.10.0, pero
    el archivo no lo decía. Comparar los dos como si fueran la misma magnitud
    es justo el error que este índice no se puede permitir.

    POR QUÉ SE HACE AQUÍ Y NO A MANO EN EL REPOSITORIO. La primera versión de
    este cambio llevaba revisiones.csv ya migrado. Como la publicación diaria
    añade una fila a ese mismo archivo cada madrugada, la rama quedaba en
    conflicto todos los días y había que rehacerla a mano. Ahora el archivo
    no se toca en el cambio: la primera ejecución tras fusionarlo lo migra
    sola, una vez, y la versión de cada fila sale de
    version_de_cada_ejecucion(), que la deduce de las fotos archivadas en
    cada republicación. Da exactamente el mismo etiquetado que se hizo a
    mano contra el historial de git (lo comprueba pruebas_aviso_deriva.py).

    La migración es puramente de forma: no toca ninguna cifra ya escrita.
    Las cinco columnas de cada fila quedan byte a byte como estaban; solo se
    añade la sexta. Si el archivo ya tiene la cabecera nueva, no hace nada.
    """
    if not os.path.exists(REVISIONES):
        return
    with open(REVISIONES, encoding="utf-8") as fh:
        lineas = fh.read().splitlines()
    if not lineas or lineas[0].strip() == CABECERA_REVISIONES:
        return
    filas = [l for l in lineas[1:] if l.strip()]
    versiones = version_de_cada_ejecucion([l.split(",")[0] for l in filas])
    cuerpo = [f"{l},{v}" for l, v in zip(filas, versiones)]
    with open(REVISIONES, "w", encoding="utf-8") as fh:
        fh.write("\n".join([CABECERA_REVISIONES] + cuerpo) + "\n")
    sin = sum(1 for v in versiones if not v)
    log.info("Registro de deriva migrado: %d filas etiquetadas con su "
             "versión, %d sin versión demostrable.", len(cuerpo) - sin, sin)


def deriva_maxima_registrada(version: str = None) -> float:
    """
    La mayor deriva anotada hasta ahora BAJO LA VERSIÓN EN CURSO.

    Se usa como referencia para avisar solo cuando la deriva es peor que
    nunca. Se mira antes de anotar la de hoy, así que no se compara consigo
    misma. Las filas sin versión —las de antes de la migración— se dejan
    fuera: no se sabe con qué reglas se midieron.
    """
    version = version or config.VERSION
    if not os.path.exists(REVISIONES):
        return float("nan")
    try:
        reg = pd.read_csv(REVISIONES)
    except Exception as e:                                      # noqa: BLE001
        log.warning("No se puede leer %s (%s). No hay referencia de deriva.",
                    REVISIONES, e)
        return float("nan")
    if "version" not in reg.columns or reg.empty:
        return float("nan")
    propias = reg[reg["version"].astype(str) == str(version)]
    if propias.empty:
        return float("nan")
    return float(pd.to_numeric(propias["deriva_maxima"],
                               errors="coerce").max())


def anotar_revision(deriva: pd.Series, generado: str) -> None:
    """Una fila por ejecución con el tamaño de la deriva observada."""
    if deriva.empty:
        return
    migrar_revisiones()
    peor = deriva.abs().idxmax()
    linea = (f"{generado},{len(deriva)},{deriva.abs().max():.4f},"
             f"{peor.date()},{int((deriva.abs() > 0.005).sum())},"
             f"{config.VERSION}\n")
    nuevo = not os.path.exists(REVISIONES)
    with open(REVISIONES, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write(CABECERA_REVISIONES + "\n")
        fh.write(linea)


def cruces_de_tramo(final: pd.DataFrame,
                    recalculada: pd.DataFrame) -> pd.DataFrame:
    """
    Filas cerradas cuyo tramo publicado ya no es el que daría el recálculo.

    QUÉ PREGUNTA RESPONDE. La deriva en puntos dice cuánto se mueve el
    pasado, pero no dice si eso importa. Un índice se lee por su tramo: una
    sesión publicada como Tensión que hoy saldría Normal es una etiqueta
    publicada que la propia fuente contradice, y eso sí importa. Una deriva de
    diez puntos en el centro de un tramo ancho, no.

    SIN UMBRALES INVENTADOS, igual que en verificar_estabilidad.py. Aquí no
    hay ninguna cifra elegida a ojo: la frontera la ponen los tramos
    publicados de config.TRAMOS, que son parte de las reglas congeladas. Si
    algún día se cambian los tramos, este aviso se recalibra solo.

    No corrige nada ni puede: una fila cerrada es inmutable. Solo la señala.
    """
    vacio = pd.DataFrame(columns=["valor_publicado", "valor_recalculado",
                                  "tramo_publicado", "tramo_recalculado"])
    if "estado" not in final.columns or "tramo" not in recalculada.columns:
        return vacio

    cerradas = final.index[final["estado"].astype(str) != PROVISIONAL]
    comunes = cerradas.intersection(recalculada.index)
    if not len(comunes):
        return vacio

    pub, rec = final.loc[comunes], recalculada.loc[comunes]
    distinto = (pub["tramo"].astype(str).fillna("")
                != rec["tramo"].astype(str).fillna(""))
    cruzadas = comunes[distinto.fillna(False).values]
    if not len(cruzadas):
        return vacio

    return pd.DataFrame({
        "valor_publicado": pub.loc[cruzadas, "ifg"].round(2),
        "valor_recalculado": rec.loc[cruzadas, "ifg"].round(2),
        "tramo_publicado": pub.loc[cruzadas, "tramo"],
        "tramo_recalculado": rec.loc[cruzadas, "tramo"],
    })


def avisar_deriva(deriva: pd.Series, cruces: pd.DataFrame,
                  record_previo: float, generado: str) -> dict:
    """
    Decide si la deriva de esta ejecución merece una incidencia, y la escribe.

    POR QUÉ EXISTE ESTE PASO. El 20 de octubre de 2026 el recálculo se separó
    10,14 puntos del valor cerrado del día 14 —la mayor deriva medida hasta
    entonces, sobre 39 sesiones— y el sistema no tenía forma de decirlo: la
    cifra se anotó en revisiones.csv y ahí se quedó. El flujo solo avisa
    cuando la publicación FALLA, y aquella no falló: publicó puntualmente un
    valor correcto. Lo que se movió fue el pasado, en silencio. Un índice que
    aspira a ser citable no puede enterarse de eso porque alguien entre a
    mirar un CSV.

    DOS DISPARADORES, NINGUNO ARBITRARIO:

      1. Un tramo publicado que el recálculo contradice. Es el aviso que
         importa editorialmente: lo que se citó ya no es lo que saldría.

      2. Una deriva mayor que cualquiera registrada bajo esta versión. No es
         un umbral a ojo, es un récord: avisa cuando pasa algo sin
         precedentes y se calla sola en cuanto ese nivel deja de ser
         excepcional. Sin esto, una deriva que no cruza ningún tramo —la del
         20 de octubre, por ejemplo— seguiría siendo invisible.

    EL RÉCORD EXIGE TENER CON QUÉ COMPARAR, y por eso no se declara cuando no
    hay ninguna deriva anotada de esta versión. Solo cuentan las filas de la
    versión en curso: las de la 0.9.0 se midieron con otras reglas, y las que
    no tengan versión demostrable se quedan fuera. Si en su lugar se usara el
    máximo de todo el archivo, el aviso compararía magnitudes distintas, que
    es justo lo que la columna de versión viene a evitar; y si se diera por
    récord la primera deriva sin base, saltaría una alerta falsa. Como el
    registro se migra antes de leer el récord, la base existe ya en la
    primera ejecución tras introducir este cambio; el caso sin base queda
    para el primer día de una versión nueva, y entonces el disparador 2
    arranca en la segunda ejecución. El 1 funciona siempre desde la primera,
    que es el que tiene consecuencia.

    No interrumpe la publicación ni toca un solo valor. Un dato cerrado es
    inmutable y lo sigue siendo: esto solo enciende una luz.
    """
    maxima = float(deriva.abs().max()) if not deriva.empty else 0.0
    peor = (str(deriva.abs().idxmax().date()) if not deriva.empty else None)
    movidas = int((deriva.abs() > 0.005).sum()) if not deriva.empty else 0

    sin_base = pd.isna(record_previo)
    hay_record = bool(maxima > 0.005 and not sin_base
                      and maxima > record_previo)

    aviso = {
        "generado": generado,
        "version": config.VERSION,
        "deriva_maxima": round(maxima, 4),
        "fecha_peor": peor,
        "sesiones_movidas": movidas,
        "record_previo": (None if pd.isna(record_previo)
                          else round(float(record_previo), 4)),
        "es_record": hay_record,
        "sin_base_comparable": bool(sin_base),
        "cruces_de_tramo": [
            {"fecha": str(f.date()),
             "valor_publicado": float(r["valor_publicado"]),
             "valor_recalculado": float(r["valor_recalculado"]),
             "tramo_publicado": str(r["tramo_publicado"]),
             "tramo_recalculado": str(r["tramo_recalculado"])}
            for f, r in cruces.iterrows()],
    }
    aviso["avisar"] = bool(hay_record or len(cruces))

    with open(RUTA_AVISO_DERIVA, "w", encoding="utf-8") as fh:
        json.dump(aviso, fh, ensure_ascii=False, indent=2)

    if len(cruces):
        log.warning("DERIVA CON CONSECUENCIA: %d sesiones cerradas tendrían "
                    "hoy otro tramo. La primera, %s: %s -> %s.",
                    len(cruces), cruces.index[0].date(),
                    cruces.iloc[0]["tramo_publicado"],
                    cruces.iloc[0]["tramo_recalculado"])
    if hay_record:
        log.warning("DERIVA SIN PRECEDENTES en la %s: %.3f puntos (%s), por "
                    "encima del máximo anterior (%.3f).", config.VERSION,
                    maxima, peor, record_previo)
    elif sin_base and maxima > 0.005:
        log.info("Deriva de %.3f puntos (%s). Es la primera anotada de la %s: "
                 "queda como referencia, no se declara récord sin base con la "
                 "que comparar.", maxima, peor, config.VERSION)
    return aviso


def escribir_serie_panel(final: pd.DataFrame, res: dict, generado: str,
                         fecha_dia: pd.Timestamp) -> dict:
    """
    Archivo compacto para el panel de la web: últimos doce meses.

    POR QUÉ EXISTE. La serie histórica completa (docs/ifg_serie.csv) tiene
    unas 4.000 filas y ronda los 250 KB. Eso vale como dato abierto para
    quien quiera descargarlo, pero no se puede pedir al navegador de cada
    lector para pintar un gráfico: penalizaría la carga de la página y
    obligaría a parsear CSV en el frontal.

    FORMATO. Arrays paralelos (fechas y valores) en vez de una lista de
    objetos. Ahorra la mitad del tamaño y es lo que una gráfica necesita.
    Se incluyen además las cifras agregadas que muestra el panel —máximo,
    mínimo y sesiones por tramo— para que el plugin no tenga que
    recalcularlas en PHP ni en JavaScript.

    Se construye sobre la serie YA FUSIONADA, no sobre el recálculo: el
    gráfico tiene que enseñar exactamente los valores publicados.

    NO SE TOCA docs/ifg.json en su forma. Los pipelines de Make ya leen ese
    archivo y cualquier cambio de estructura podría romperlos.
    """
    # El gráfico pinta el valor OFICIAL desde la 0.10.0, para que su último
    # punto coincida con el titular. Si pintara el suavizado mientras el
    # titular es el crudo, el lector vería dos cifras distintas para el mismo
    # día. La línea de tendencia viaja aparte, en "valores_tendencia", lista
    # para cuando el plugin la dibuje; añadir una clave no rompe nada, y
    # quitarla sí.
    serie = final["ifg"].dropna().tail(SESIONES_PANEL)
    tendencia = final["ifg_suavizado"].reindex(serie.index)
    tramos = final["tramo"].reindex(serie.index)

    # Desglose del último día. Se recalcula; ver el límite conocido anotado
    # en la cabecera del archivo.
    nivel = res["contribuciones"].loc[fecha_dia].dropna()

    panel = {
        "version": config.VERSION,
        "generado": generado,
        "desde": str(serie.index[0].date()),
        "hasta": str(serie.index[-1].date()),
        "sesiones": int(len(serie)),
        "fechas": [str(f.date()) for f in serie.index],
        "valores": [round(float(v), 2) for v in serie.values],
        "valores_tendencia": [None if pd.isna(v) else round(float(v), 2)
                              for v in tendencia.values],
        "maximo": {"fecha": str(serie.idxmax().date()),
                   "valor": round(float(serie.max()), 2)},
        "minimo": {"fecha": str(serie.idxmin().date()),
                   "valor": round(float(serie.min()), 2)},
        "sesiones_por_tramo": {t: int((tramos == t).sum())
                               for _, _, t in config.TRAMOS},
        "desglose_nivel": {c: round(float(nivel[c]), 4) for c in nivel.index},
        # P2: misma licencia que la foto del día. Ver sellar_foto().
        "licencia": ("Consulta y cita. Sin licencia de reutilización "
                     "comercial ni de redistribución. Ver "
                     "https://elespeculador.com/indices/friccion-global/"
                     "#ifg-licencia"),
    }

    with open(f"{DIR_PUBLICO}/ifg_serie_12m.json", "w", encoding="utf-8") as fh:
        json.dump(panel, fh, ensure_ascii=False, separators=(",", ":"))
    return panel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ahora", action="store_true",
                   help="salta la guardia horaria")
    args = p.parse_args()

    if not args.ahora and not toca_publicar():
        return 0

    if not comprobar_version():
        return 1

    os.makedirs(DIR_PUBLICO, exist_ok=True)
    generado = datetime.now(ZONA).isoformat(timespec="seconds")

    # --- Datos --------------------------------------------------------------
    tickers = {**config.TICKERS, **config.CESTA_DEFENSA, **config.CESTA_FLETES}
    precios = fuentes.descargar_precios(tickers,
                                        inicio=config.FECHA_INICIO_MUESTRA,
                                        usar_cache=False)
    gpr = fuentes.descargar_gpr(usar_cache=False)
    prima = fuentes.descargar_prima_riesgo(usar_cache=False)
    gdelt = fuentes.cargar_gdelt()

    # --- Cálculo ------------------------------------------------------------
    res = indice.calcular(precios, gpr=gpr, prima=prima, gdelt=gdelt)
    tabla = res["tabla"]
    if not tabla["ifg"].notna().any():
        log.error("El cálculo no ha producido ningún valor. No se publica.")
        return 1

    # --- Solo sesiones cerradas ---------------------------------------------
    # Con la serie congelada, publicar la fecha de hoy sería congelar un
    # valor intradía como si fuera un cierre, y ya no habría forma de
    # corregirlo. En la ejecución normal de las 03:15 esto no quita nada: la
    # última sesión disponible es siempre la de un día anterior. Lo que evita
    # es que un --ahora lanzado por la tarde ensucie la serie para siempre.
    hoy = datetime.now(ZONA).date()
    recalculada = tabla[COLUMNAS].copy()
    abiertas = recalculada.index[recalculada.index.date >= hoy]
    if len(abiertas):
        log.warning("Se descartan %d sesiones sin cerrar (desde %s): no se "
                    "congela un valor intradía.", len(abiertas),
                    abiertas[0].date())
        recalculada = recalculada[recalculada.index.date < hoy]
    if recalculada.empty:
        log.error("No queda ninguna sesión cerrada que publicar.")
        return 1

    # --- Serie definitiva: lo cerrado manda ---------------------------------
    final, deriva, correcciones = fusionar(recalculada, leer_serie_publicada())
    final.to_csv(RUTA_SERIE, float_format="%.2f")

    # El récord se mira ANTES de anotar la deriva de hoy, o se compararía
    # consigo misma y nunca habría récord. Y DESPUÉS de migrar el registro:
    # si se leyera sin la columna de versión, el primer día tras introducirla
    # no habría base y el disparador del récord se perdería esa sesión.
    migrar_revisiones()
    record_previo = deriva_maxima_registrada()
    anotar_revision(deriva, generado)
    anotar_correcciones(correcciones, generado)

    # La deriva, por sí sola, no para nada: una fila cerrada es inmutable.
    # Pero deja de ser invisible.
    avisar_deriva(deriva, cruces_de_tramo(final, recalculada),
                  record_previo, generado)

    n_comp = archivar_componentes(final, res)
    log.info("Componentes archivados: %d sesiones en %s.", n_comp, RUTA_COMPONENTES)

    # --- Valor del día, tomado de la serie definitiva ------------------------
    # La fecha la manda la serie definitiva, no el recálculo: si se han
    # descartado sesiones sin cerrar, el día publicado es el último cerrado.
    fecha_dia = final.index[-1]
    ultimo = indice.descomponer_dia(res, fecha=fecha_dia)
    fila = final.loc[fecha_dia]

    # Si esta fecha ya estaba publicada, estos tres campos vienen de la
    # publicación original, no del recálculo de hoy. Es justo el punto de
    # toda la regla.
    # El índice oficial es el crudo desde la 0.10.0; el suavizado viaja como
    # "valor_tendencia". Ninguna clave desaparece: ver indice.descomponer_dia.
    ultimo["valor"] = None if pd.isna(fila["ifg"]) else float(fila["ifg"])
    ultimo["valor_tendencia"] = (None if pd.isna(fila["ifg_suavizado"])
                                 else float(fila["ifg_suavizado"]))
    ultimo["valor_crudo"] = None if pd.isna(fila["ifg"]) else float(fila["ifg"])
    ultimo["variacion"] = None if pd.isna(fila["variacion"]) else float(fila["variacion"])
    ultimo["tramo"] = fila["tramo"]
    ultimo["estado_dato"] = str(fila["estado"])

    sellar_foto(ultimo, generado)

    with open(f"{DIR_PUBLICO}/ifg.json", "w", encoding="utf-8") as fh:
        json.dump(ultimo, fh, ensure_ascii=False, indent=2)

    panel = escribir_serie_panel(final, res, generado, fecha_dia)
    log.info("Serie del panel: %d sesiones de %s a %s, máximo %.1f el %s.",
             panel["sesiones"], panel["desde"], panel["hasta"],
             panel["maximo"]["valor"], panel["maximo"]["fecha"])

    # Registro de ejecuciones: la prueba de que se publica sin fallos, que es
    # el requisito 5 de la sección 4, y la base de la validación prospectiva.
    # También es lo que evita publicar dos veces el mismo día.
    linea = (f"{generado},{ultimo['fecha']},{ultimo['valor']},"
             f"{ultimo['tramo']},{ultimo['cobertura']},"
             f"{ultimo['estado_dato']}\n")
    nuevo = not os.path.exists(REGISTRO)
    with open(REGISTRO, "a", encoding="utf-8") as fh:
        if nuevo:
            fh.write("ejecutado,fecha_dato,valor,tramo,cobertura,estado\n")
        fh.write(linea)

    log.info("Publicado: %s = %.1f (%s, %s), motores %s",
             ultimo["fecha"], ultimo["valor"], ultimo["tramo"],
             ultimo["estado_dato"], [m["componente"] for m in ultimo["motores"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
