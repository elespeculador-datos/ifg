# Especulador Índices — instalación

Plugin de WordPress que pinta el Índice de Fricción Global en elespeculador.com.
No calcula nada: lee los JSON que publica GitHub Actions cada madrugada.

---

## 1. Antes de instalar

**En el entorno de pruebas primero, nunca en producción.** El plugin no toca
ninguna tabla de WordPress ni modifica contenido, pero JNews es un tema con
muchos estilos propios y conviene ver cómo encaja el bloque antes de ponerlo
en la portada.

## 2. Instalación

1. En el escritorio de WordPress, **Plugins → Añadir nuevo → Subir plugin**.
2. Elige el archivo `especulador-indices.zip`.
3. **Instalar ahora** y después **Activar**.

Al activarse hace tres cosas: deja los ajustes de fábrica, programa una tarea
horaria de refresco y trae los datos una primera vez. Si todo ha ido bien, en
**Ajustes → Índices** verás ya el valor del día.

## 3. Comprobación

Entra en **Ajustes → Índices**. La tabla de estado debe decir:

- **Valor del día**: una cifra, una fecha y la versión del índice.
- **Serie de doce meses**: el número de sesiones. Si dice «Pendiente», es
  normal hasta la primera publicación con el código nuevo del repositorio.
- **Próximo refresco**: un tiempo. Si dice que la tarea no está programada,
  desactiva y vuelve a activar el plugin.

Si el valor del día no se puede leer, usa el botón **Refrescar ahora** y mira
si cambia. Lo más probable entonces es que el servidor no tenga salida a
internet hacia GitHub.

## 4. Dónde se coloca cada cosa

| Código | Dónde va |
|---|---|
| `[esp_friccion]` | Portada, en el sitio del actual bloque «Radar de fricción global» |
| `[esp_friccion_panel]` | La página del índice: `/indices/friccion-global/` |
| `[esp_friccion_valor]` | Dentro del texto de un artículo, para citar la cifra |

El tercero admite dos parámetros: `[esp_friccion_valor enlace="no" tramo="no"]`.

### En la portada con JNews

El bloque de portada funciona en un **widget de texto** o en un bloque
**Shortcode** de Gutenberg. Si la fila donde va obliga a que las dos columnas
tengan la misma altura, el bloque se estirará o se recortará: en ese caso usa
el parámetro `focos` para ajustar cuántas noticias lista.

    [esp_friccion focos="2"]

También se puede cambiar el título y la entradilla:

    [esp_friccion titulo="Radar de fricción global" entrada="Los focos que pueden alterar la sesión."]

## 5. Ajustes

En **Ajustes → Índices** se configuran solo direcciones: dónde están los datos
y a dónde llevan los enlaces. Los valores de fábrica ya apuntan a
`elespeculador-datos.github.io/ifg/` y a `/indices/friccion-global/`.

**Lo que no se puede cambiar desde ahí, a propósito**: los umbrales de los
tramos, los componentes y sus pesos. Son la definición del índice y están
publicados en la metodología. Si se pudieran tocar desde un formulario, un día
alguien movería el corte de «Alta» y la serie dejaría de significar lo mismo a
lo largo del tiempo, en silencio. Cambiarlos exige numerar una versión nueva y
recalcular la serie entera desde el script de Python.

La casilla **«Mostrar la versión y la etiqueta preliminar»** debe quedarse
marcada mientras el índice esté en validación prospectiva. Quitarla equivale a
presentarlo como referencia terminada.

## 6. Caché

El plugin guarda los datos en la base de datos y los lee de ahí: una visita a
la portada **nunca** llama a GitHub. Por eso no hay nada que excluir del caché
de página, y si GitHub se cae, el bloque sigue enseñando el último valor bueno
con su fecha.

Si usas un caché de página agresivo, la única consecuencia es que el valor
nuevo tardará en verse lo que tarde en caducar esa página. Con un caché de
seis horas y una publicación de madrugada, ningún lector verá un dato de hace
más de un día.

## 7. Qué hace con la base de datos

Dos opciones, ambas con `autoload` desactivado:

- `esp_indices_ifg_dia` — la foto del día, menos de 2 KB.
- `esp_indices_ifg_serie` — doce meses para el gráfico, unos 6 KB.

No crea tablas ni guarda la serie histórica completa: esa vive en GitHub como
dato abierto y pesa 250 KB. Al desinstalar, las opciones se quedan; si quieres
limpiarlas del todo, se borran a mano desde la base de datos.

## 8. Aviso legal

Todo lo que pinta el plugin es contenido informativo y educativo. No es
asesoramiento financiero ni recomendación de inversión. El aviso viaja dentro
del propio marcado del bloque, no en una nota al pie, para que no se pierda si
alguien reutiliza el HTML.
