# Revisión de versión: 0.9.0 -> 0.10.0

Republicado el 2026-10-18 21:10 CEST.

## Por qué se recalcula la serie entera

Un cambio de reglas obliga a recalcular toda la serie: mantener valores viejos calculados con reglas viejas junto a valores nuevos calculados con reglas nuevas produciría una serie que no es comparable consigo misma. Los cambios de esta versión están detallados en la cabecera de `config.py`.

## Qué cambia, medido

- Sesiones antes: **4293** · después: **4294**
- Sesiones cuyo valor cambia: **4273** de 4293 comunes
- Cambio absoluto medio: **2.69** puntos (mediana 1.33)
- Cambio máximo: **46.97** puntos, el 2011-10-03
- Sesiones que cambian de tramo: **828**
- Cobertura media de componentes: 0.838 -> **0.911**
- Primera sesión con cobertura plena: 2021-06-11 -> **2021-06-11**

### Cobertura de componentes, año a año

Es lo que responde de verdad a si el arreglo ha servido: la media de toda la serie puede subir por muchos sitios, pero lo que había que corregir era la era degradada del principio.

| Año | Antes | Después |
|---|---|---|
| 2010 | 0.15 | 0.82 (mejora) |
| 2011 | 0.25 | 0.81 (mejora) |
| 2012 | 0.81 | 0.81 |
| 2013 | 0.82 | 0.81 |
| 2014 | 0.85 | 0.84 |
| 2015 | 0.91 | 0.91 |
| 2016 | 0.91 | 0.91 |
| 2017 | 0.91 | 0.91 |
| 2018 | 0.91 | 0.91 |
| 2019 | 0.91 | 0.91 |
| 2020 | 0.91 | 0.91 |
| 2021 | 0.96 | 0.96 |
| 2022 | 1.00 | 1.00 |
| 2023 | 1.00 | 1.00 |
| 2024 | 1.00 | 1.00 |
| 2025 | 1.00 | 1.00 |
| 2026 | 1.00 | 1.00 |

## Dónde está la serie anterior

Archivada, no borrada. Quien haya citado un valor de la versión anterior lo sigue encontrando aquí:

- `docs/historico/ifg_serie_0.9.0.csv`
- `docs/historico/ifg_0.9.0.json`
- `docs/historico/ifg_serie_12m_0.9.0.json`

## Encuadre

Contenido informativo y educativo. No constituye asesoramiento financiero ni recomendación de inversión. El índice es una lectura del estado del mercado, nunca una señal de compra o de venta.
