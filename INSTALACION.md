# Fase 2 — publicación diaria automática

Pasos para poner el IFG a publicarse solo cada día hábil. No hace falta
terminal: todo se hace desde la web de GitHub.

Tiempo estimado: media hora la primera vez.

---

## Antes de empezar

Necesitas una cuenta de GitHub. Es gratis y basta con un correo. Si no la
tienes, créala en `github.com` antes de nada.

---

## 1. Crear el repositorio

1. En `github.com`, botón **New** (o el `+` de arriba a la derecha → *New
   repository*).
2. Nombre: `ifg` o el que prefieras.
3. Déjalo **Public**. Hace falta para que GitHub Pages sirva el JSON gratis,
   y además encaja con el requisito de datos abiertos.
4. No marques nada más. Botón **Create repository**.

## 2. Subir los ficheros

1. En el repositorio vacío, enlace **uploading an existing file**.
2. Arrastra **la carpeta entera** descomprimida, no los ficheros sueltos: la
   estructura importa.
3. Abajo, botón **Commit changes**.

Debe quedar así:

```
config.py  indice.py  firma.py  fuentes.py  ...   el código del índice
publicar_diario.py                                lo que corre cada mañana
requirements.txt
.github/workflows/ifg-diario.yml                  la tarea programada
docs/                                             lo que se publica (se llena solo)
```

Si `.github` no aparece tras subirlo, es que el navegador se saltó las
carpetas que empiezan por punto. En ese caso: **Add file → Create new file**,
y en el nombre escribe `.github/workflows/ifg-diario.yml` (las barras crean
las carpetas solas), pega dentro el contenido de ese fichero y confirma.

## 3. Encender GitHub Pages

1. Pestaña **Settings** del repositorio.
2. Menú lateral, **Pages**.
3. En *Source*, elige **Deploy from a branch**.
4. Branch: `main`, carpeta: `/docs`. Botón **Save**.

A los pocos minutos el JSON estará en:

```
https://TUUSUARIO.github.io/ifg/ifg.json
```

Esa es la URL que leerá Make.

## 4. Primera carga de GDELT

El histórico de GDELT hay que bajarlo una vez. En el repositorio:

1. Pestaña **Actions**.
2. En la lista de la izquierda, **IFG diario**.
3. Botón **Run workflow**, deja *forzar* marcado, y confirma.

Tarda unos veinticinco minutos. Las ejecuciones siguientes solo añaden los
días que falten y tardan tres o cuatro.

## 5. Comprobar

Cuando el flujo termine en verde, abre la URL de Pages. Debe salir algo así:

```json
{
  "fecha": "2026-10-09",
  "version": "0.9.0",
  "valor": 71.4,
  "variacion": 2.3,
  "tramo": "Tensión",
  "motores": [
    {"componente": "fletes", "aporte_cambio": 0.08},
    {"componente": "prima", "aporte_cambio": 0.05}
  ],
  "estado": "preliminar: ..."
}
```

A partir de ahí se publica solo, de lunes a viernes.

---

## Qué vigilar las primeras semanas

- **Que no falle ningún día.** El fichero `docs/registro_publicaciones.csv`
  deja constancia de cada ejecución. Es la prueba del requisito de
  puntualidad y, sobre todo, la base de la validación prospectiva: cada día
  que pasa es muestra nueva que la serie histórica ya no nos puede dar.
- **La cobertura.** Si baja del 70 %, el día sale marcado como parcial y
  conviene mirar qué fuente se ha caído.
- **GDELT.** Es la pieza más frágil. Si falla, el paso está marcado para no
  tumbar la publicación: el índice se calcula sin él y reparte el peso.

## Lo que NO hay que hacer

Tocar los pesos, los componentes o los umbrales. Las reglas están congeladas
desde el 10 de octubre de 2026 y el sentido de congelarlas es precisamente
que los próximos meses sean validación de verdad. Cualquier cambio obliga a
numerar versión nueva, anunciarlo y recalcular la serie entera.

---

Contenido informativo y educativo. No constituye asesoramiento financiero ni
recomendación de inversión.
