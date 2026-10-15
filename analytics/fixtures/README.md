# Fixture sintético agregado

`tasas_sinteticas.csv` contiene solo cifras inventadas para explorar el contrato de cálculo. No procede del RNC, de ONEI ni de una persona; no es un formato de entrada productivo y no debe publicarse como estadística observada. No contiene filas individuales ni identificadores.

Cada fila representa una combinación ficticia de período, territorio, sexo, edad y localización. `tumor_count` cuenta tumores agregados; `person_count` representa personas distintas ficticias y nunca supera los tumores. `population` es un denominador inventado. La columna `standard_weight` reproduce los pesos públicos Segi–Doll usados por CI5/IARC para facilitar un ejercicio de ajuste directo; no es población cubana. La correspondencia de esos pesos con la salida institucional del RNC sigue pendiente de cotejo.

Todos los conteos y denominadores fueron creados únicamente para esta fixture. No usar para estimar incidencia, validar resultados institucionales, entrenar modelos ni presentar cifras sobre Cuba. Para ejemplos visibles, conservar siempre la etiqueta “datos sintéticos”.

`consulta_demo_sintetica.csv` es un escenario agregado para la vista local. Usa los nombres de las 15 provincias y el municipio especial Isla de la Juventud, además de categorías anatómicas habituales y años reales de referencia (2021–2024). Sus conteos de tumores y personas son enteramente sintéticos, calibrados para producir volúmenes y patrones de edad/sexo plausibles; no son casos observados, estimaciones RNC ni datos de cáncer de Cuba.

Los denominadores son aproximaciones sintéticas para la demostración. Los totales provinciales anuales toman como referencia la tabla 1.2 de ONEI 2024; la estructura de edad y sexo usa las tablas ONEI 1.7 y 1.10 de 2024, distribuida proporcionalmente por provincia. Por tanto, cada celda provincia × año × sexo × edad no equivale al valor publicado por ONEI y no debe usarse para producir tasas reales. El ajuste emplea los pesos estándar Segi–Doll del ejercicio original. La ficha local de la fuente es el [Anuario Demográfico de Cuba 2024](https://www.onei.gob.cu/sites/default/files/publicaciones/2025-07/00-anuario-demografico-2024.pdf); sus cuadros 1.2, 1.7 y 1.10 documentan las dimensiones y totales usados como referencia.

El archivo contiene agregados, sin filas individuales ni identificadores. Puede regenerarse con `python analytics/fixtures/generar_consulta_sintetica.py`. La vista está restringida a `DEBUG=True` y tanto ella como la descarga CSV identifican los casos como sintéticos.
