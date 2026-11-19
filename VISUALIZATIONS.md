# Vistas de Consulta estadística

Cambio solicitado por el responsable del proyecto el 12-11-2026, como propuesta
de producto: ampliar el selector de gráficos y administrar la disponibilidad
del mapa y la tendencia temporal. Referencia de interacción: Cancer Today/GCO.

- `table`: tabla de agregados, diez filas por página. Los cálculos y las
  exportaciones utilizan el resultado completo, independientemente de la página.
- `trend`: serie anual de los valores observados. Requiere dos años disponibles;
  activar la función no crea años ni extrapola valores.
- `curve`: perfil por grupos de edad, con interpolación monótona entre valores
  observados. Es una interpretación provisional de la petición de una curva
  parecida a una exponencial, pendiente de confirmar con el responsable.
  No estima una función exponencial ni predice valores futuros.
- `map`: mapa coroplético provincial. Usa el indicador seleccionado, muestra
  explícitamente áreas sin datos y conserva el cero como valor observado.
  Geometría y procedencia: [static/geo/README.md](static/geo/README.md).

## Disponibilidad

`/administracion/visualizaciones/` permite activar/desactivar `trend` y `map`.
Requiere la capacidad existente `publish_deliveries`, también disponible para
superadministradores, y registra el cambio en la auditoría.

El administrador escribe `visualizations.json` de forma atómica dentro de
`RNC_PUBLIC_RELEASE_ROOT`. El servicio público solo lo lee y filtra tanto el
selector como las opciones admitidas por el formulario. En una instalación con
procesos separados, ambos usan el mismo directorio de publicaciones: el público
requiere acceso de lectura. No se introduce acceso del servicio público a la BD.
Sin archivo se ofrecen ambas funciones; un archivo ilegible o inválido las oculta.

La disponibilidad administrativa y la suficiencia de datos son independientes:
la tendencia temporal no puede dibujarse a partir de un único año publicado.
Los cambios no alteran el archivo de entrada ni crean datos de ejemplo.

## Densidad de categorías y exportación

Corrección solicitada a partir de una imagen con etiquetas superpuestas.
La consulta no elimina categorías para hacerlas caber en un tamaño fijo:

- Barras, ranking y puntos por categoría: altura por fila, nombres partidos en
  líneas y contenedor con desplazamiento accesible por teclado.
- Barras agrupadas/apiladas/porcentuales: orientación horizontal cuando hay más
  de diez categorías; se conservan las series y la escala porcentual 0–100.
- Series y curvas: ancho por categoría, desplazamiento horizontal y menos
  anotaciones cuando podrían superponerse. El valor completo sigue en tooltip
  y tabla. El corte 2022 no permite verificar una serie temporal de varios años.
- Dispersión: tamaño de punto adaptado a la densidad; se mantiene el tratamiento
  de puntos coincidentes. El mapa conserva sus límites geográficos.
- Circular/anillo: hasta ocho sectores. Con más categorías, se muestran las siete
  mayores y la suma de las restantes como Otras categorías, con una nota visible.
  La tabla, CSV, XLSX y las páginas de detalle PDF mantienen todas las categorías.
  Los nombres largos de leyenda se abrevian en pantalla; los nombres completos
  siguen en el tooltip/tabla y en la leyenda exportada, partida en líneas.
- PNG/SVG: dimensiones adaptadas a filas y longitud de etiquetas; título y pie
  usan márgenes físicos para no entrar en el gráfico. PNG limita las dimensiones
  de rasterización; SVG conserva texto vectorial escalable.
- PDF: gráficos categóricos densos en bloques de veinte, conservando escala
  común, posición global e intervalo de categorías. Las páginas de detalle se
  distribuyen según las líneas que necesita cada fila.

`chart-layout.js` comparte las reglas de tamaño y composición con la consulta
local. Se actualiza la caché del shell offline para incluirlo. Esta corrección
cambia la presentación; no modifica el CSV ni los denominadores.

Comprobación con el agregado real: recorridos Chromium de escritorio (1366 px)
y móvil (390 px), incluyendo 105 localizaciones y 333 códigos morfológicos;
22 recorridos aprobados: 18 consultas online y cuatro variantes offline. Revisión geométrica de 31 figuras y páginas de imágenes y
páginas PDF: nombres dentro de los márgenes, etiquetas consecutivas sin solaparse,
títulos y pies fuera de los ejes. Inspección visual de barras en navegador y de
exportaciones. Las capturas/agregados de QA quedan solo en almacenamiento local
ignorado, sin incluirse en documentación ni Git.
