# RNC Web

Portal de consulta de incidencia de cáncer en Cuba. MVP local funcional con datos exclusivamente sintéticos; no es un despliegue institucional ni está autorizado para recibir microdatos reales.

## Demo web provisional — exploración

Hay un despliegue temporal de QA en PythonAnywhere con datos sintéticos que sirve estadísticas públicas y administración autenticada en la misma app: <https://dannyfiallo.pythonanywhere.com/>. Inicio, `/consulta/`, `/acceso/` y el panel administrativo cargaron por HTTPS; se comprobó un inicio de sesión de superusuario. Al crear la cuenta se aceptó omitir la validación de contraseña, así que debe cambiarse por una clave larga y única antes de continuar el QA. Siguen pendientes el recorrido de permisos y funciones administrativas, el acceso desde las redes de revisores, la matriz de filtros/exportaciones y la revisión de seguridad. No es institucional ni permite datos reales. Ver [guía PythonAnywhere](deploy/pythonanywhere/README.md), [arquitectura y operación](docs/ARQUITECTURA-OBJETIVO-OPERACION.md) y [DEC-014](../rnc-research/docs/07-decisiones/DEC-014-demo-web-provisional.md).

## Ejecutar

Para preparar el entorno paso a paso, crear la cuenta local y publicar datos de demostración, consulta [LEVANTAR-LOCAL.md](LEVANTAR-LOCAL.md).

La estrategia, matriz de requisitos/cobertura y comandos de regresión están en [TESTING.md](TESTING.md). La evidencia de cada recorrido de navegador se guarda localmente bajo `docs/` y no se versiona.

La política, prioridad y estado verificable de traducciones está en [TRANSLATIONS.md](TRANSLATIONS.md). Español es el idioma fuente; inglés está disponible con cobertura parcial. No se afirma que la web esté completamente traducida.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8010
```

Abrir http://127.0.0.1:8010/. `seed_demo` genera personas/tumores sintéticos y un CSV privado, lo registra y publica mediante los servicios del panel. Si ya hay entregas, conserva el estado existente. No modifica cuentas ni genera contraseñas compartidas.

En otra terminal, activar el mismo entorno y ejecutar el worker de correo:

```bash
python manage.py deliver_account_mail --watch
```

Sin `--watch`, procesa una vez los mensajes pendientes. En local, Django guarda los mensajes en `private/mail/`; no los envía a Gmail ni a otros destinatarios reales. Abra allí el enlace de invitación/recuperación. El archivo contiene un enlace sensible y no debe compartirse. Un envío fallido se muestra en Usuarios; puede reenviarse desde Editar cuenta. Una interrupción del worker mientras procesa un mensaje requiere revisión de su estado antes de reintentar.

Para enviar correos reales, configurar SMTP autorizado y un remitente válido mediante variables de entorno. `.env.example` describe las variables; el proyecto no carga `.env` automáticamente. En el perfil combinado, `RNC_PUBLIC_ORIGIN` debe coincidir con la dirección accesible al destinatario; en `settings_admin`, usar `RNC_ADMIN_ORIGIN` para que invitaciones y recuperación apunten al servicio restringido. Usar HTTPS y no construir enlaces de seguridad desde el Host de una solicitud.

## Prototipo de separación pública/privada

La publicación de un corte sintético crea un archivo versionado con agregados. Las vistas públicas leen ese archivo y no consultan `Delivery`, SQLite administrativo ni `PRIVATE_STORAGE_ROOT`. El paquete conserva consultas por período, territorio, sexo, edad y grupo ilustrativo de localización. La consulta admite seleccionar varios valores en cada filtro y agrega tumores a partir del cubo; no guarda IDs de personas o tumores en el paquete. Los conteos exactos de personas distintas están disponibles si cada filtro selecciona cero o un valor. Al combinar varios valores no se suman esos conteos —una persona podría aparecer en varias categorías— y la interfaz los marca como no disponibles. La selección de personas distintas con varios valores queda pendiente de un diseño de agregados que conserve deduplicación exacta sin exponer registros individuales.

El repo ofrece perfiles Django separados. `config.settings_admin` expone las rutas de acceso, cuentas, cargas y publicación; `config.settings_public` solo registra archivos estáticos, usa una base de datos dummy que rechaza consultas y monta las rutas públicas. Configurar `RNC_PUBLIC_RELEASE_ROOT` igual en ambos procesos; el servicio administrativo escribe allí y el público debe montarlo solo de lectura. `PRIVATE_STORAGE_ROOT` permanece únicamente en el servicio administrativo. `RNC_PUBLIC_SITE_URL` y `RNC_ADMIN_ORIGIN` definen las direcciones que conectan la interfaz y los enlaces administrativos.

Para probar ambos perfiles en local, después de crear/migrar el entorno y preparar un corte sintético:

```bash
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" DJANGO_SETTINGS_MODULE=config.settings_admin python manage.py runserver 127.0.0.1:8011
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" DJANGO_SETTINGS_MODULE=config.settings_public python manage.py runserver 127.0.0.1:8010
```

La semilla local genera el paquete al publicar. Para regenerarlo desde la publicación activa existente, ejecutar `DJANGO_SETTINGS_MODULE=config.settings_admin python manage.py sync_public_release`. El comando valida que el corte siga siendo sintético. El perfil predeterminado `config.settings` conserva ambas áreas para desarrollo local y **no** constituye separación de despliegue.

Este cubo está habilitado solo para datos sintéticos: incluye muchos agregados solapados y aún no aplica supresión de celdas ni controles de inferencia. No cargar datos del RNC ni desplegar el perfil público con datos reales hasta que el RNC valide `Q-007`/`Q-027`, el esquema de publicación y la operación de revisión. La base administrativa sigue siendo SQLite local y los perfiles no son una configuración productiva aprobada.

## Recorrido

El orden de trabajo para cerrar las brechas identificadas en filtros, catálogos y visualizaciones está en el [plan de implementación GCO–RNC](../rnc-research/docs/06-arquitectura/plan-implementacion-filtros-y-analisis.md); distingue mejoras del demo sintético, requisitos bloqueados por validación y ampliaciones posteriores a Prácticas II.

- **Inicio:** indicadores del último año y localizaciones principales de la publicación activa; cambia al publicar/revocar.
- **Consulta `/consulta/`:** filtros de año de incidencia, ámbito geográfico, sexo, edad y grupo ilustrativo de localización en un panel lateral plegable que permanece visible al desplazarse en escritorio; todos aceptan selección múltiple y ausencia de selección equivale a todos los valores disponibles. Al aplicar filtros, la página lleva al gráfico y la tabla manteniendo el panel accesible. En móvil el panel queda antes de los resultados y puede plegarse. Los grupos sintéticos solo aparecen si tienen registros en el corte; no son un catálogo completo. Permite tumores o personas distintas cuando cada filtro usa cero o un valor; al combinar varios valores se limita a tumores para evitar presentar una suma incorrecta de personas. Incluye conteos, porcentajes, tasa cruda/específica y ajuste directo Segi–Doll candidato.
- **Ámbito geográfico:** se ofrece “Cuba (nacional)” solo cuando todos los años del corte incluyen las 16 provincias/territorios del catálogo del Manual. En cortes parciales la opción general advierte que no equivale necesariamente a Cuba completa. La selección provincial se rotula como residencia y no como provincia/unidad informante. No se incorpora selector de países de GCO. La semántica del archivo real y las variables adicionales del Manual requieren validación. Ver la [auditoría comparativa](../rnc-research/docs/04-ux-ui/auditoria-filtros-gco-rnc-2026-10-22.md) y el [plan de implementación](../rnc-research/docs/06-arquitectura/plan-implementacion-filtros-y-analisis.md).
- **Gráficos:** barras horizontales, columnas, líneas, agrupadas, apiladas, porcentuales, circular y anillo. Solo se genera el gráfico elegido. El backend rechaza combinaciones incompatibles. Los gráficos por sexo respetan la misma selección.
- **Exportaciones:** PNG, SVG, PDF con gráfico y detalle tabular, CSV y Excel. Incluyen filtros, unidad, condición sintética, versión y contexto metodológico. La caché de exportaciones está ligada a versión; no evita comprobar la publicación activa.
- **Privacidad de consulta:** explorar y descargar no requiere cuenta ni crea un historial individual. `/consulta/` responde con `Cache-Control: no-store` y `Referrer-Policy: no-referrer`. El servidor/proxy puede mantener sus propios access logs; antes de desplegar deben configurarse para no conservar los filtros de la URL sin finalidad, acceso y retención acordados. No se registran todavía métricas públicas agregadas.
- **Publicación pública/privada:** el corte activo se exporta como cubo agregado versionado; las vistas del perfil público consultan ese cubo sin leer filas privadas. Los perfiles `settings_admin` y `settings_public` separan URLconf y permisos de datos; el perfil público no instala los modelos de administración y no tiene almacenamiento privado configurado. Solo prototipo sintético; falta política RNC para inferencia/supresión.
- **Administración:** carga CSV, informe técnico, historial de entregas con paginación, publicación y revocación auditadas. El CSV de actualización descargable añade un tumor sintético al corte activo y permite ensayar otra publicación. Un corte sustituye el conjunto completo anterior; no hay cargas incrementales ni restauración automática de una publicación revocada. Las descargas ya realizadas no pueden retirarse.
- **Usuarios:** interfaz propia con búsqueda/paginación, altas, edición, activación/desactivación y roles. Las invitaciones permiten elegir contraseña sin que soporte la conozca. La contraseña temporal obliga a cambiarla antes de navegar. Recuperación por enlace temporal de una hora; cambio autenticado con contraseña actual.

## Consulta local y PWA experimental

El perfil aislado `config.settings_public` ofrece `/consulta-offline/`: permite guardar explícitamente en IndexedDB la publicación sintética activa y ejecutar filtros, frecuencias, tasas y tasa ajustada en un Web Worker del navegador. El gráfico y las tablas se generan localmente. La pantalla muestra versión, fecha, tamaño aproximado y tiempo de cálculo; la medición online informa latencia de ida y vuelta y bytes de HTML. No mide por sí sola uso de CPU del servidor ni sustituye una evaluación de rendimiento.

La PWA se sirve desde el origen público aislado y usa el scope `/`. Precarga una pantalla local sin datos y recursos estáticos; las páginas públicas intentan la red y, si no está disponible, muestran esa pantalla. No almacena la administración, resultados de `/consulta/` ni el endpoint del paquete. La consulta descargable ejecuta filtros, cálculos y gráficos en un Web Worker del dispositivo, después de que la persona guarde explícitamente la publicación en IndexedDB. El usuario decide cuándo guardar o borrar el paquete. Los navegadores pueden desalojar IndexedDB y una copia desconectada no puede actualizarse o revocarse hasta recuperar conexión. Esta implementación es una prueba técnica con datos sintéticos, no una autorización para publicar agregados reales. No se deben cargar microdatos ni habilitar este perfil con una publicación real antes de validar con el RNC divulgación, supresión, autorización, actualización y retención de copias. La administración permanece online.

La arquitectura y las decisiones institucionales pendientes se describen en [arquitectura objetivo y operación](docs/ARQUITECTURA-OBJETIVO-OPERACION.md) y [DEC-013](../rnc-research/docs/07-decisiones/DEC-013-pwa-solo-publica.md).

Roles propuestos para el MVP: `operator` (cargas), `publisher` (cargas, publicación/revocación), `superadmin` (todas las capacidades y cuentas). Un superusuario Django también tiene acceso de soporte. Son roles locales de producto, no designaciones institucionales aprobadas. La ruta antigua `/admin/` redirige a Usuarios del portal; las páginas internas del administrador Django ya no se exponen, para evitar caminos que eludan las políticas de cuentas de la interfaz propia.

## Entrada sintética y privacidad

El CSV de demostración usa 10 columnas, en este orden:

`synthetic,person_id,tumor_id,period,territory_id,sex_id,age_group_id,site_id,population,standard_weight`

No es el contrato RNC de 84 columnas. Los campos categóricos llevan identificadores de catálogos con `concept_id`, `name`, `description`, cero o más `identifiers` externos y metadatos de versión/estado; la interfaz resuelve las etiquetas desde esos catálogos. `territory_id` usa los códigos de provincia documentados en el Manual RNC VII; los IDs de sexo, edad y grupos de localización ilustrativos son internos del demo y no tienen crosswalk ICD-O. Como referencia inicial de este proyecto, y pendiente de validación del RNC, se toma ICD-O-3 para topografía/morfología e ICCC-3 para grupos diagnósticos infantiles, conforme a lo documentado en el Manual RNC VII. Esto no elige una subversión concreta de ICD-O-3 para los archivos de origen: se conserva la edición declarada; si no consta, no se infiere. La entrada RNC deberá preservar literalmente `TOPO`, `MORF` y cada código de origen; las correspondencias entre ediciones o clasificadores se gestionarán aparte y con versión, y no se usarán para combinar estadísticas hasta que estén validadas. El usuario identifica `509` como TOPO de mama bajo ICD-O-2 en el formato recibido; falta cotejar esa forma y los demás campos con el diccionario autorizado. IARC publicó tablas finales ICD-O-4 en julio de 2026, pero esa actualización internacional no cambia automáticamente la referencia elegida. `site_id` sigue siendo una agrupación sintética, no el nomenclador completo que requiere el producto. Antes de copiar tablas oficiales extensas a la web hay que obtener/confirmar permiso de reproducción y traducción; ver [Q-002 y evidencia de clasificación](../rnc-research/docs/05-requisitos/mapa-de-preguntas.md). La interfaz futura deberá presentar código literal, sistema/edición, nombre, descripción y fuente con ayuda accesible al pasar el puntero, enfocar o tocar el código. El directorio de unidades informantes del Anexo 1 se conserva como catálogo versionado, con filas repetidas o discordantes marcadas. Ningún catálogo convierte este contrato en el formato real autorizado por el RNC. Exige `synthetic=TRUE`, identificadores `SYN-P-` / `SYN-T-`, IDs admitidos, coherencia de personas/estratos, claves de tumor únicas y cobertura completa de ambos sexos y 18 grupos etarios por territorio/año. No incluye nombres personales. El límite local es 12 MB y 60 000 filas. Los marcadores no demuestran por sí mismos que un archivo sea sintético: el responsable no debe cargar datos reales.

### Búsqueda de nomencladores

`/nomencladores/` ofrece búsqueda por código/texto y filtros de sistema, edición y eje. La referencia inicial de este proyecto, pendiente de validación RNC, es ICD-O-3 para topografía/morfología e ICCC-3 para grupos diagnósticos infantiles; no implica elegir la subversión exacta de ICD-O-3 cuando el archivo de origen no la especifique. Agrupa códigos bajo conceptos explícitos con `concept_id`, nombre y descripción; cada código conserva código literal, sistema, edición, eje, nombre, descripción, estado, fuente, licencia y relación declarada. El archivo raíz versiona el catálogo; cada concepto conserva su procedencia e idioma. La interfaz muestra estas relaciones y permite desplegar descripciones con ratón, teclado o tacto. Para habilitar tablas se define `RNC_CODING_CATALOG` con la ruta a un JSON UTF‑8. El contrato está en `analytics/coding-catalog.schema.json`; se puede validar sin imprimir códigos con `python manage.py validate_coding_catalog <ruta>`. Los borradores y relaciones pendientes no se publican. No hay datos clínicos ni tablas oficiales empaquetadas en el repositorio. Sin archivo configurado se muestran enlaces a las fuentes oficiales; un archivo inválido no se publica. Los grupos sintéticos `site_id` siguen separados de los códigos ICD‑O. No se deben agrupar códigos de ediciones distintas bajo un concepto ni crear correspondencias sin procedencia y validación documentadas.

Para generar ese JSON desde un CSV preparado manualmente, se puede usar `python manage.py import_coding_catalog_csv entrada.csv catalogo.json --catalog-version <version> --source <url>`. El convertidor exige estos encabezados exactos y en este orden: `concept_id,concept_name,concept_description,language,concept_source,concept_license,publication_status,system,edition,axis,code,code_name,code_description,code_status,code_source,code_license,relationship,relationship_status`. Cada fila describe un código y repite los metadatos de su concepto. El comando agrupa solo por `concept_id` explícito, rechaza metadatos inconsistentes, valida el contrato y escribe el JSON de manera atómica. `code` se conserva como texto literal (incluidos ceros iniciales); no pegar códigos en una hoja que los convierta a números. Los ejes admiten topografía, morfología, comportamiento, grado, estadio y clasificación (para grupos de sistemas como ICCC-3), además de otros. Se necesita `--force` para reemplazar una salida existente. Este formato normalizado no es el esquema de entrada del RNC ni un importador automático de hojas originales OMS/IARC. Revisar procedencia, edición, licencia y estado antes de preparar filas; el comando no concede permiso para publicar.

Los identificadores de persona y tumor sintéticos no salen a consultas ni exportaciones públicas. Los originales de cargas nuevas que superan la validación sintética y las representaciones privadas usan claves opacas y permisos de filesystem restringidos, fuera de cualquier ruta pública. La BD registra metadatos, huellas, responsables, estados, informes y auditoría, no las filas de carga. La validación es atómica; de una carga nueva rechazada solo se conserva el informe técnico y la huella para detectar duplicados, no el archivo. Registros de rechazo creados por versiones anteriores pueden tener un original local; no se borran automáticamente. La misma huella no crea otra entrega.

El importador admite una misma persona en varios años, conservando su identidad sintética y la coherencia de estrato dentro de cada año. El conteo de personas es único en la selección completa, incluso al combinar años. Las categorías por edad, territorio, localización o período pueden solaparse y no se suman para obtener personas distintas. Una persona puede aparecer en varias localizaciones: sus conteos por localización no se suman ni se ofrecen como composición circular. Los denominadores son sintéticos y se deduplican por año/territorio/sexo/edad; filtrar una localización no reduce la población denominadora. Los pesos Segi–Doll y métodos son candidatos, pendientes de cotejo RNC.

## Organización y trazabilidad

La arquitectura lógica, los límites entre módulos, la estructura objetivo y el diseño de clases están documentados en [`../rnc-research/docs/06-arquitectura/diseno-arquitectura-y-clases-2026-11-04.md`](../rnc-research/docs/06-arquitectura/diseno-arquitectura-y-clases-2026-11-04.md). La revisión estática del código, las correcciones recientes y la deuda arquitectónica se registran en [REVISION-TECNICA-2026-11-04.md](REVISION-TECNICA-2026-11-04.md). La estructura no se migró en bloque: primero se establecen límites y contratos para que el movimiento incremental conserve URL, migraciones y datos locales.

- `config/`: configuración y puntos de entrada Django.
- `public_site/models.py`, `migrations/`: metadatos administrativos de cargas, publicación activa, auditoría y políticas/correo de cuentas.
- `public_site/services.py`: almacenamiento privado, validación y transiciones administrativas; al publicar, prepara el paquete agregado.
- `public_site/aggregate_release.py`, `aggregate_statistics.py`: escritura versionada y lectura/consulta del cubo público sin IDs.
- `public_site/public_portal.py`: vistas públicas; `portal.py`: operaciones administrativas; `exports.py`: renderizado de imágenes, PDF y hojas de cálculo.
- `config/settings_admin.py` / `settings_public.py`, `config/urls_admin.py` / `urls_public.py`: perfiles separados para procesos administrativos y públicos.
- `public_site/accounts.py`, `forms.py`, `middleware.py`: gestión de cuentas, contraseñas y restricciones.
- `templates/`, `static/`: interfaz propia; Chart.js 4.5.1 se distribuye localmente con licencia MIT en `static/vendor/`.
- `analytics/`: funciones estadísticas y fixtures sintéticas; el perfil público usa el paquete agregado y el administrador conserva las filas sintéticas en almacenamiento privado.

Investigación y requisitos: repositorio hermano `rnc-research`. Dirección de esta ampliación: `SRC-PRJ-002` → `EVD-101..102` → `DEC-012-mvp-funcional-sintetico.md`; capacidades relacionadas `REQ-F-001..015`, `REQ-D-003..005`. El adelanto funcional no cambia por sí mismo el alcance aprobado del Anexo A.

## Ramas y archivos

El flujo concurrente obligatorio para todas las áreas del proyecto está en [`../CONCURRENCIA.md`](../CONCURRENCIA.md). Usa un worktree propio para cada tarea que edite este repositorio; aísla base, almacenamiento, correo, artefactos y puertos por ejecución. Solo paraleliza pruebas si no escriben en recursos compartidos.

`main` es la rama predeterminada protegida. El trabajo se realiza en `develop`; los cambios hacia `main` pasan por PR y el control `repository-policy`. Ver [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

Versionar código, migraciones, pruebas y fixtures agregadas permitidas. `.gitignore` excluye documentos de trabajo, evidencias, archivos privados, bases locales, correo y secretos. `docs/` contiene evidencia local no publicada. No añadir `BD PARA DANI.csv` ni ningún archivo de salud identificable.

## Verificación y límites

El 23-10-2026 pasaron **70 pruebas Django**, incluidas matrices de 46 400 cruces de selectores/filtros simples, 262 158 estados multiselección enumerados por filtro y 750 exportaciones. La corrida E2E aprobó **1358 comprobaciones de navegador** y guardó **185 capturas** en PC (1440×1000), laptop (1024×900) y móvil emulado (390×844), sin excepciones JavaScript, fallos de recursos ni HTTP 500. [Estrategia, conteos y límites de la matriz](TESTING.md); reporte local: `docs/revision-completa-2026-10-23/`. El producto cartesiano de multiselecciones simultáneas aún contiene 33 554 432 estados y no se ejecutó íntegramente; ver el detalle y límites en el reporte de investigación. La suite usa recursos temporales y datos sintéticos. `.github/workflows/tests.yml` automatiza backend y E2E en CI; su ejecución remota y check obligatorio dependen de GitHub. Esto no equivale a validación RNC, auditoría de seguridad, evaluación con usuarios ni despliegue institucional.

El 10-11-2026 se probaron las tres matrices extensas (76 pruebas Django en total, sin fallos); 73 pruebas regulares midieron 83% de cobertura combinada de líneas/ramas. La PWA aprobó 45 comprobaciones funcionales, la carga sintética completó 290/290 consultas GET hasta concurrencia 16, y el recorrido general aprobó 1 520 checks en tres anchos emulados. [Reporte PWA, rendimiento y límites](PWA-TEST-RESULTS-2026-11-10.md). Los tiempos son del equipo local y no son objetivos de producción.

La revisión de interfaz y entradas se traza en `SRC-PRJ-003` → `EVD-103..104`, `EVD-396` → `DEC-012`. Los formularios previenen entradas incompatibles según campo y el servidor repite la validación; nombres y contraseñas conservan símbolos legítimos. Errores enlazados al control y política CSP complementan el tratamiento seguro de datos.

SQLite, caché local, auditoría en BD y servidor de desarrollo son para este entorno. Antes de uso institucional: contrato de entrada autorizado, política de divulgación, cálculo contrastado, SMTP/TLS, caché compartida y límites de proxy, MFA/operación de soporte, auditoría resistente a manipulación, retención, backups/restauración coordinados, pruebas de concurrencia, seguridad y accesibilidad. El secreto de desarrollo provoca un error si se intenta arrancar con DEBUG desactivado; esto no sustituye configurar el resto del despliegue.
