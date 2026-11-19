# Legibilidad de columnas y nombres de gráficos

Corrección del 13 de noviembre de 2026. El ancho mínimo compartido incluye las columnas y reserva espacio por categoría. Las etiquetas del eje categórico se conservan y la región del gráfico permite desplazamiento horizontal sin ensanchar la página. Las vistas con pocas categorías ocupan el ancho disponible. Se mantiene el desplazamiento vertical de barras horizontales.

La barra de tipos de gráfico dispone de un nivel de superposición superior al panel de filtros para que los nombres al pasar el puntero o enfocar los iconos permanezcan visibles. Se actualizaron las versiones de recursos y la caché pública para propagar el cambio a la consulta sin conexión.

Validación dirigida en Chrome con publicación agregada existente de solo lectura: 16 comprobaciones aprobadas. Escritorio 1440 × 1050 y móvil emulado 390 × 844; 105 categorías en columnas y dos en selección por sexo; acceso a las últimas columnas, etiquetas completas, ausencia de desbordamiento de página, orden visual del nombre emergente, barras horizontales y cálculo local sin red. No se modificaron datos originales ni cuentas. No se ejecutó una nueva suite Django porque el cambio se limita a presentación y caché de recursos.
