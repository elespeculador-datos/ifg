# Código del IFG / Oscilador Geopolítico en smpro-datos-1 · 25/11/2026

Archivo del **código** que corre en el servidor propio (`/home/smpro/ifg`, `main` en 08a44b2), sin `docs/` ni `datos/`:
- las series y los componentes no se publican en abierto mientras no se resuelvan las licencias de los precios de origen;
- el servidor guarda su historial completo y lo respalda cada sábado con `git bundle`.

- `servidor/ifg-diario.sh`: el script diario (L-V 03:15). Publica `/ifg/` (0.10.0) y, desde el 25/11/2026, `/oscilador-geo/` (0.10.1).
- `oscilador.py`, `pruebas_oscilador.py` y `CONGELADO-0.10.1.md`: Oscilador Geopolítico 0.10.1, el mismo cálculo que la 0.10.0 con nombre y tramos nuevos.

Es una rama de archivo: no se fusiona en `main`, porque `main` sirve GitHub Pages, del que siguen leyendo la CNMV y los colectores.
