# Vigilancia de los comunicados de la CNMV

Que ninguna empresa del IBEX 35 se quede sin comunicados sin que nadie lo vea.

**Por qué**: el 24/11/2026 se vio que Logista y Colonial llevaban trece meses sin un solo comunicado en el colector `cnmv`. Firman en la CNMV como «Logista Integral» y «Colonial SFL», y sus alias de `cnmv/empresas.csv` eran los antiguos. El colector terminaba siempre en «correcto», así que sus fichas salían vacías y no se abría ninguna incidencia. Arreglado en la PR #124; esta pasada evita que vuelva a pasar en silencio.

**Qué hace** (`vigilancia.py`, todos los días a las 09:25, después de `cnmv`):
- Lee `cnmv/datos/ibex35.csv`, el listado de trece meses que deja `cnmv`, con el ISIN de cada empresa.
- Para con error, que abre la incidencia `vigilancia-fallido`, si alguna empresa del IBEX 35:
  - no tiene ningún comunicado en el listado: su alias no reconoce el nombre con el que firma hoy;
  - lleva más de 150 días sin ninguno. En los trece meses hasta el 25/11/2026, el hueco más largo entre dos comunicados de una misma empresa fue de 110 días (Puig); el siguiente, 98 (Acerinox).
- El error nombra la empresa y su alias.
- No descarga nada ni toca las salidas de otros colectores. Deja `vigilancia/datos/ultima.json` con el recuento y el último comunicado de cada empresa.

**Comprobado con los datos reales**: con el listado del servidor del 25/11 a las 17:25 (todavía con los alias antiguos), avisa justo de Logista y Colonial.

**Pruebas**: `python3 vigilancia/pruebas_vigilancia.py` (sin red, 8 comprobaciones). Cubren:
- empresa sin comunicados;
- empresa callada 151 días;
- listado vacío;
- filas sin ISIN;
- dos pasadas completas con la composición real del IBEX 35 (código 0 y código 1).

**Composición**: usa `cnmv.comunicados.empresas_ibex`, así que vence con ella (`IBEX35_VALIDA_HASTA`). Si vence, también para con error, y eso también es algo que hay que ver.
