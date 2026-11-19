# Una consulta estadística con conexión y sin conexión

Dirección del responsable del 12-11-2026: integrar el modo offline/PWA en la
consulta habitual y mostrar el estado al pie del sidebar. Sustituye el acceso
separado de consulta local; /consulta-offline/ redirige a /consulta/ para conservar
marcadores antiguos. La PWA inicia en /consulta/.

## Comportamiento

El mismo formulario, selector de gráficos, pestañas, tabla y paginación sirven
con y sin conexión. Con servidor disponible se mantiene el recorrido Django.
Al fallar la conexión se calcula en un worker sobre la publicación pública
agregada guardada. Los filtros también se restauran desde la URL al arrancar sin
red; el estado y las exportaciones locales no requieren una sección distinta.

El indicador Online/Offline comprueba el servidor mediante una respuesta pequeña
sin caché. Los eventos del navegador ayudan a detectar cambios, pero no se
considera navigator.onLine una prueba suficiente de acceso al servidor.
Otra línea informa si los datos están preparados, disponibles o no se pudieron
guardar. Visitar Consulta con conexión prepara automáticamente la copia; abrir
por primera vez sin red y sin copia previa no puede ofrecer datos que el
navegador nunca descargó. Los fallos de cuota/almacenamiento se muestran y no
rompen la consulta online.

## Publicación local y cálculo

Se reutiliza IndexedDB rnc-public-offline, almacén package, clave active. Se
aceptan únicamente esquema 3 real, publicación aprobada y contrato unified. Los
paquetes antiguos no se presentan como completos. Una huella de publicación
permite evitar descargas completas repetidas; la sustitución de la copia se hace
solo tras recibir y guardar un paquete válido. Una revocación observada al
reconectar retira la copia activa. Sin red no es posible conocer una revocación.

Se incluyen cohortes adulta/infantil, C10/CICN, grupos principales, morfología,
etapa, VH/SCD, tasas, totales documentales y geometría provincial. En el corte
actual los identificadores de persona son disjuntos; se envían los márgenes más
detallados y el worker reconstruye los demás. Si no son disjuntos se conservan
los márgenes precomputados, evitando sumar personas solapadas. No se añaden
identificadores individuales al paquete. El paquete actual ocupa unos 14,64 MiB.

El service worker conserva el shell canónico y los recursos públicos, reconoce
las versiones de recursos y excluye administración, acceso/cuentas, respuestas de
consulta con filtros, comprobaciones de conexión y descargas de paquetes. La
publicación se guarda explícitamente en IndexedDB, no como una respuesta privada
ni como una captura de una sesión. El proceso público sigue usando BD dummy.

## Exportaciones

Sin red se generan CSV y XLSX con todos los resultados y metadatos, PNG local y
un informe mediante la impresión/PDF del navegador, con tabla completa y bloques
de gráfico cuando es denso. El SVG local de gráficos de canvas contiene una
imagen, señalado en su botón; el mapa conserva vectores. Con conexión permanecen
los renderizadores del servidor, incluido SVG vectorial y PDF. Esta diferencia
no altera los conteos ni los cálculos.

## Verificación observada

- 184 consultas del paquete compacto contra el motor Python: 106 992
  comprobaciones aprobadas, incluyendo cohortes, dimensiones, dos unidades,
  tasas, VH/SCD y los dos totales documentales.
- Chromium en perfil temporal: 15 comprobaciones de preparación automática,
  control del service worker, manifiesto, apertura directa sin red, cambios de
  filtro/gráfico, mapa, tabla, exportaciones CSV/XLSX/PNG, preparación de impresión/PDF, vista móvil, recarga sin
  red, exclusión de rutas privadas de caché y reconexión.
- XLSX generado sin servidor leído con openpyxl: nueve columnas y celdas
  numéricas válidas. Sin registros ni resultados clínicos en los logs.

Se comprobó el manifiesto y el arranque sin red; no se afirma una instalación
manual en un dispositivo físico. Los datos y artefactos de QA permanecen en los
recursos temporales/ignorados propios de la tarea. Los pendientes de etapa y las
diferencias de fuente CSV/Anuario no cambian por esta integración.

La suite de aplicación terminó con 56 pruebas aprobadas (52,734 s), usando
base y almacenamiento temporales. Se actualizó la expectativa del manifiesto
para su nuevo inicio en /consulta/.


## Corrección del 13-11-2026: páginas públicas independientes

Inicio, Acerca de y Nomencladores mantienen su ruta y contenido sin red o con el servidor caído. Las páginas se preparan en español e inglés; solo los alias de consulta reutilizan el explorador. El HTML de respaldo ya indica offline antes de pintarse. El acceso administrativo nace oculto y requiere confirmación real de conexión; también se protege la restauración del historial y se descartan comprobaciones tardías.

Las páginas informativas no dependen de IndexedDB ni del paquete estadístico. La consulta local sí requiere sus agregados preparados. Las rutas privadas siguen fuera de caché. La instalación rechaza una nueva caché si falta una página obligatoria. Versión: `rnc-public-shell-navigation-20261113-v5`.

Validación: 8 regresiones de worker, 62 pruebas Django y 81 comprobaciones Chrome aprobadas. Se detuvo realmente el proceso público de prueba manteniendo la red del navegador activa, y después se verificó la recuperación. La simulación de modo independiente no equivale a instalar en todos los sistemas operativos. Los scripts reproducibles son `scripts/test_public_navigation.cjs` y `scripts/review_public_navigation.cjs`; este último recibe una ruta existente de publicaciones públicas y usa servidor y perfil temporal propios.

Trazabilidad: SRC-PRJ-057 → EVD-776..778 → DEC-013; registro en `rnc-research-offline-navigation/docs/04-ux-ui/2026-11-13-navegacion-publica-offline.md`. El servidor público actualizado se ejecuta desde este worktree en `127.0.0.1:8010`, con lectura de la publicación existente, sin iniciar administración ni migrar datos compartidos.
