# Integración real y verificación del corte 2022

Fecha: 12-11-2026. Rama de trabajo: `codex/chart-filters-layout`.
Solicitud del responsable: corregir la desconexión entre la interfaz, BD_2022.csv
 y el diccionario de variables. Este documento registra trabajo técnico local.

## Fuente → regla → implementación → comprobación

| Fuente | Regla o interpretación | Implementación | Evidencia técnica |
|---|---|---|---|
| BD_2022.csv | Cada fila elegible se cuenta como tumor | rnc_input y rnc_aggregation | Conteo independiente contra el original |
| Variables para Danny_OK | FECHAD, EDAD, SEXO y PROV | Año, cohortes, quinquenios, sexo y residencia | Correspondencia con originales y Excel |
| Diccionario, COMP | Adultos 3; menores de 20 excepto 2 | Elegibilidad antes de agregar | Particiones adulta e infantil contrastadas |
| Tabla CIE-10 del DOCX | Grupos principales y localizaciones | Catálogo versionado rnc_site_groups.json | Transcripción íntegra y pertenencia de cada código |
| DOCX, CICN | Clasificador infantil independiente | Se conservan códigos CICN, sin inventar equivalencias CIE-10 | Contraste de códigos infantiles |
| DOCX, MORF y UNIDIDAD | VH: MORF distinto de 8000; SCD: UNIDIDAD 0000 | Numeradores y cobertura por celda | Comparación directa con el CSV |
| Excel suministrado | Población por residencia, sexo y edad | Cubo poblacional independiente de los casos | Estratos sin duplicados; denominador y tasas contrastados |
| Estándar Segi–Doll | Ajuste directo, pesos normalizados | Fórmula completa o truncada al intervalo explícito | Fórmula independiente por provincia y cohorte |

Se contrastó la publicación activa con las huellas de los tres archivos originales.
Pasaron 127 065 comprobaciones contra los originales y 9 240 de concordancia
online/offline. No se imprimieron datos de pacientes, identificadores ni valores
clínicos. Estas comprobaciones cubren las condiciones enumeradas en el script;
no certifican el producto cartesiano de todos los filtros ni la decisión
institucional sobre indicadores y serie poblacional.

La referencia del estándar y las fuentes institucionales siguen en rnc-research.
El Excel suministrado se identifica como fuente del denominador utilizado, sin
atribuirle una certificación oficial no demostrada en esta tarea.

## Distinciones que impiden resultados engañosos

Los niveles principal y detallado son particiones separadas: no se suman padres
con hijos. El selector adulto permite pedir explícitamente Total C00-97; las
categorías D del listado no se añaden a ese total. Las tasas por localización
requieren elegir población adulta o infantil para no mezclar clasificadores.
La población se obtiene del Excel incluso donde no hay casos de una localización.

NOCASO es la clave de persona confirmada por el responsable el 12-11-2026.
Se calcula su cardinalidad distinta en cada margen del cubo, conservando los
identificadores exclusivamente en memoria privada. No se publican identificadores,
conjuntos ni huellas individuales. El corte actual tiene NOCASO único por registro;
por eso sus márgenes son disjuntos y admiten selecciones múltiples sin duplicar
personas. En un futuro corte con personas repetidas, se conservan los conteos
exactos de cada margen y se restringen las uniones que no se pueden deduplicar
con el agregado disponible; nunca se suman personas potencialmente solapadas.

Etapa se muestra mediante los códigos recibidos. Se aplican las exclusiones
conocidas para leucemias y linfomas. La excepción escrita como «****» no se ha
localizado completa en los cuatro nomencladores ni en el texto consultado del
Manual VII; no se supone. Los porcentajes usan únicamente casos elegibles para
esa distribución. Las equivalencias I–IV y «sin estudiar» no se inventan.

Los rótulos del DOCX se usan tal como se suministraron, por instrucción explícita
del responsable de 12-11-2026. Las diferencias C09/D46/D45,D47 con CIE-10 se
conservan en label_notes como antecedentes; ya no bloquean ni sustituyen los
rótulos del producto. No se corrige el código clínico original.

El archivo CLASIFICACION DE LOS NIÑOS.xlsx contiene 12 grupos y 47 subgrupos.
Se transcribe íntegro, conservando código romano y descripción; la representación
numérica de CICN se vincula a esa jerarquía sin recalcular el diagnóstico a partir
de morfología. Los códigos no presentes en el catálogo conservan su código visible.

Los tres XLS de nomenclatura se conservan como un catálogo de referencia
versionado. Las denominaciones morfológicas mantienen sus sinónimos y su sufijo de
comportamiento; se utilizan como descripción de MORF, sin multiplicar registros.
Los cuatro códigos morfológicos que no cumplen el formato de cuatro dígitos/barra/
comportamiento quedan registrados como entradas originales no normalizadas y no
se reparan automáticamente. Las correspondencias CIE-O/CIE-10 condicionadas por
morfología no se aplican como conversiones directas. Los rótulos de agrupación del
DOCX tienen prioridad sobre los nombres de catálogo.

El Anuario suministrado tiene 19 cuadros y prescribe tasas generales/adultas por
100 000 y tasas infantiles por 1 000 000; estas unidades se aplican a cálculo,
gráficos, tablas y exportaciones online. La consulta offline actual mantiene su
contrato de todas las edades por 100 000; no anuncia filtros de cohorte ausentes.
Los totales C00-96 del Anuario y C00-97 del DOCX tienen selecciones separadas.
La comprobación provincial inicial frente al Anuario coincide en conteos, tasas
brutas y ajustadas para 30 de 32 combinaciones provincia/sexo. Las dos diferencias
son mujeres de Artemisa y Matanzas; no se altera el CSV para igualar una tabla.
Esta comparación parcial no certifica todos los cuadros del Anuario ni determina
la causa de esas diferencias de fuente.

## Operación y aislamiento

La instancia de esta tarea utiliza sus propios `private/`, `db.sqlite3` y
`public_releases/`. Se conserva la interfaz y la configuración de traducciones.
Los worktrees originales no se modificaron. La activación está registrada como
operación local mediante una cuenta técnica inactiva, sin privilegios ni contraseña.
Los artefactos publicados son agregados, no copias del CSV ni de NOCASO.

Se retiró el comando de generación de demostraciones del flujo activo. El lector
requiere esquema 3 real y manifiesto íntegro. Se conserva un respaldo comprimido
verificado del artefacto propio anterior en esta tarea, con nota de recuperación
privada. La compresión reduce el uso de disco y no cambia el contenido estadístico.

## Pendientes tras las aclaraciones y lectura de los archivos

1. Texto que reemplaza «****» y equivalencias de los códigos de etapa.
2. Explicar las dos diferencias provinciales CSV/Anuario antes de afirmar
   concordancia completa con ese documento.
3. Revisión visual interactiva, aún no realizada.

La clave de persona, los rótulos del DOCX y los nombres/grupos infantiles ya no
son pendientes. La serie poblacional suministrada y las unidades del Anuario son
las elegidas por el responsable para esta implementación; esto no se presenta
como una aprobación institucional independiente.

Validación actualizada tras las aclaraciones: `python manage.py test analytics public_site --noinput`: 56 pruebas, OK (57,515 s). El verificador independiente aprobó 127 065 comprobaciones y 9 240 online/offline, incluidas personas con selección múltiple, los 59 rótulos infantiles y los dos totales documentales.

La suite de aplicación se adaptó al flujo real: se conservaron cuentas, permisos y
traducciones, se retiraron los positivos basados en el importador de demostración y
se añadieron pruebas de ingestión, publicación/revocación real, privacidad y
disponibilidad de visualizaciones. Pasaron 56 pruebas sin fallos. Las verificaciones
numéricas contra archivos reales se mantienen separadas de los ejemplos unitarios
de aritmética. CSV, XLSX, PNG, SVG y PDF devolvieron HTTP 200 y firmas de formato
válidas. Las vistas de tabla, grupos principales, histología, códigos de etapa y
mapa respondieron HTTP 200, mostrando únicamente 2022. No se realizó QA visual
interactivo ni se certificó el producto cartesiano de todos los filtros.

## Corrección posterior de legibilidad

La revisión de densidad se documenta en VISUALIZATIONS.md. Se revisó visualmente
el gráfico de barras en Chromium y exportaciones; esta evidencia posterior
supera la ausencia de QA visual indicada en la verificación inicial, únicamente
para los escenarios de esta corrección. No certifica todas las combinaciones de
filtros. El significado de los datos y los pendientes de etapa/Anuario no cambian.

## Consulta unificada posterior

La integración offline/PWA se describe en OFFLINE_CONSULTATION.md. Su comprobación
de 184 consultas y 106 992 resultados contra el motor Python amplía la cobertura
del contrato local inicial. Los resultados históricos anteriores se conservan
como evidencia de sus respectivos escenarios.
