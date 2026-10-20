"""Descarga el fichero de posiciones cortas de la CNMV y describe su estructura.
Solo para el desarrollo del rastreador: imprime hojas, columnas y primeras filas."""
import io, sys
import requests
import pandas as pd

URL = "https://www.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls"
r = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 (El Especulador datos abiertos)"})
print("HTTP", r.status_code, "bytes", len(r.content), "tipo", r.headers.get("Content-Type"))
print("cabecera", r.content[:16])
open("cortos/NetShortPositions.xls", "wb").write(r.content)
for motor in ("xlrd", "openpyxl", None):
    try:
        hojas = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None, engine=motor)
        print("motor", motor, "OK")
        break
    except Exception as e:
        print("motor", motor, "falla:", e)
else:
    try:
        tablas = pd.read_html(io.BytesIO(r.content))
        hojas = {f"tabla{i}": t for i, t in enumerate(tablas)}
        print("leido como HTML")
    except Exception as e:
        print("tampoco HTML:", e); sys.exit(1)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
for nombre, df in hojas.items():
    print("\n=== HOJA", repr(nombre), df.shape)
    print(df.head(15).to_string())
    print("...")
    print(df.tail(3).to_string())
