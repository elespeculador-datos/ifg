# Oscilador Geopolítico 0.10.1 · reglas congeladas

Congeladas el 25/11/2026 por el chat del servidor, antes de la primera publicación, por decisión de Federico del 25/11/2026: opción 1 de `claude/oscilador-0110-resultados-2026-11-20.md`, solo el cambio de nombre con el cálculo de la 0.10.0. Cualquier cambio de estas reglas exige numerar otra versión.

1. **Cálculo.** Es el de la 0.10.0, sin ningún cambio: el código de `main` que publica `/ifg/` (`config.VERSION = "0.10.0"`). El Oscilador no recalcula nada. Toma la serie que `publicar_diario.py` ha escrito y `verificar_estabilidad.py` ha dado por buena, así que sus valores son los del IFG 0.10.0, sesión a sesión.
2. **Nombre.** «Oscilador Geopolítico». Nota pública: «Hasta la versión 0.10.0 este índice se publicó como Índice de Fricción Global».
3. **Tramos (R7, decidido el 20/11).** Alivio fuerte [0, 20) · Alivio [20, 40) · Estable [40, 60) · Presión [60, 80) · Presión fuerte [80, 100].
4. **Histéresis.** Una sesión conserva el tramo de la anterior mientras su valor no quede más de 2 puntos por fuera de los límites de ese tramo: por debajo del límite inferior menos 2, o por encima del superior más 2. Sin sesión anterior con dato, el tramo es el que corresponde al valor. El valor publicado no se toca.
5. **Lo cerrado no se toca.** El tramo de una sesión publicada como definitiva se calcula una vez y se conserva en las pasadas siguientes (`docs/oscilador-geo/oscilador-geo_serie.csv`). Si el valor de una sesión cerrada cambiara, el Oscilador no se publica ese día.
6. **Direcciones.**
   - Datos: `datos.elespeculador.com/oscilador-geo/oscilador-geo.json` y `oscilador-geo_serie_12m.json`.
   - Ficha: `/indices/oscilador-geopolitico/`.
   - Shortcodes: `[esp_oscilador_geo]`, `[esp_oscilador_geo_panel]` y `[esp_oscilador_geo_valor]`.
7. **Transición.** `/ifg/` sigue publicando la 0.10.0 sin ningún cambio mientras alguien lo lea. Después se congela con un aviso de traslado (fase F5), sin borrarse.
8. **Lo que la 0.10.1 no arregla** (auditoría del 20/11/2026):
   - saturación en los extremos por la multiplicación por el coseno;
   - memoria de unas 60 sesiones en los componentes de precios;
   - GDELT muestreado un día por semana.

   La 0.10.0 tampoco pasa la prueba P4 de escaladas: Crimea 74,2 y Mar Rojo 67,5, por debajo de 80. La metodología lo declara.
9. **La 0.11.0** sigue calculándose en privado. Solo puede sustituir a esta versión con un prerregistro nuevo y validación prospectiva.
