# Métodos candidatos

`metrics.py` contiene cálculos puros para evaluación académica; no accede a archivos ni decide la unidad epidemiológica. `demo.py` lee exclusivamente la fixture sintética y utiliza esas fórmulas para la consulta de demostración. Cada resultado debe conservar `METHODS_VERSION` (`candidate-2`) y los metadatos de denominadores, estándar, escala y método.

## Funciones disponibles

- Frecuencia absoluta y relativa; la segunda requiere universo explícito.
- Tasa cruda/específica por escala configurable (100 000 por defecto).
- Ajuste directo con estratos coincidentes y pesos estándar explícitos.
- IC de tasas crudas/específicas mediante Byar para conteos positivos; si el conteo es cero usa límite superior exacto Poisson y límite inferior cero.
- IC Wald normal para ajuste directo, con varianza Poisson del ASR y límite inferior truncado en cero.

Los niveles de confianza aceptan cualquier valor entre 0 y 1. El valor predeterminado es 95 %. No se ha fijado redondeo. La variante para ASR es solo una candidata: el intervalo normal puede comportarse mal con conteos pequeños y no representa una política de publicación del RNC. La comparación metodológica y la pregunta `Q-009` están en la documentación de `rnc-research`.

## Compatibilidad de entradas

El llamador debe asegurar que numeradores y denominadores correspondan al mismo período, territorio, sexo, definición tumoral y grupo de edad. La población anual puede no ser equivalente a persona-años: confirmar el tipo de población ONEI usado antes de interpretar tasas. Los pesos estándar son distintos de los denominadores poblacionales; los pesos Segi–Doll de referencia suman 100 000 y no representan distribución cubana.

`fixtures/tasas_sinteticas.csv` conserva el ejercicio inicial de métodos. `fixtures/consulta_demo_sintetica.csv` amplía el escenario de consulta a provincias cubanas, localizaciones anatómicas habituales, cuatro períodos, dos sexos y 18 grupos de edad. Sus conteos son inventados; los denominadores son aproximaciones modeladas con cuadros demográficos ONEI como referencia. `analytics/demo.py` agrega conteos por tumores/personas y evita duplicar denominadores al combinar localizaciones.

La vista `/consulta-sintetica/` solo se sirve con `DEBUG=True`; la navegación local la identifica como «Consulta estadística» y la página advierte que se trata de cifras sintéticas. La exportación CSV conserva ese aviso. La tasa directa usa pesos Segi–Doll como referencia de diseño y no ha sido cotejada con resultados RNC. Ni el conjunto ni sus cálculos son estadísticas institucionales. La fuente y los supuestos de generación están descritos en `fixtures/README.md`.

## Referencias para evaluar los candidatos

- CI5 XII, IARC (2024), [capítulo metodológico y población estándar](https://ci5.iarc.who.int/ci5-xii/about/): ajuste directo y error estándar Poisson; no establece el IC del RNC.
- IARC, [Cancer Epidemiology: Principles and Methods](https://publications.iarc.who.int/421): intervalos aproximados/Poisson para tasas y conteos.
- Tiwari, Clegg y Zou (2006), [intervalos para tasas ajustadas por edad](https://wonder.cdc.gov/controller/pdf/TiwariMethodConfidenceIntervals.pdf): método gamma modificado, referencia para comparar más adelante.
- CDC, [intervalos de confianza en estadísticas de cáncer de Estados Unidos](https://www.cdc.gov/united-states-cancer-statistics/technical-notes/confidence-intervals.html): describe su política de intervalo gamma modificado; sirve como referencia comparativa extranjera, no como regla cubana.

Antes de usar cualquier intervalo en publicaciones se necesita escoger método con el RNC, cotejar resultados con un caso institucional autorizado y decidir el tratamiento de conteos pequeños, ceros, edades desconocidas y redondeo.
