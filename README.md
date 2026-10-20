# RNC Web

Portal de consulta de incidencia de cáncer en Cuba. MVP local funcional con datos exclusivamente sintéticos; no es un despliegue institucional ni está autorizado para recibir microdatos reales.

## Demo web provisional — exploración

Se está explorando un alojamiento temporal para mostrar avances desde distintos dispositivos. Primero se consultará por un subdominio y entorno de ensayo de CUJAE/RNC; CITMATEL es candidato a consultar si no hay entorno institucional. Vercel soporta Django, pero se deben confirmar elegibilidad/condiciones desde Cuba y adaptar almacenamiento/base de datos. GitHub Pages podría alojar solo una demo estática separada. No se ha elegido proveedor ni realizado despliegue. Un eventual demo público usará solo datos sintéticos y no expondrá administración, cuentas/cargas ni envío de correo real. Esta configuración local no está lista para publicarse: usa SQLite y archivos locales, `DEBUG=True` por defecto y `seed_demo` solo corre en DEBUG. Ver [arquitectura y operación](docs/ARQUITECTURA-OBJETIVO-OPERACION.md) y [DEC-014](../rnc-research/docs/07-decisiones/DEC-014-demo-web-provisional.md).

## Ejecutar

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

La publicación de un corte sintético crea un archivo versionado con agregados. Las vistas públicas leen ese archivo y no consultan `Delivery`, SQLite administrativo ni `PRIVATE_STORAGE_ROOT`. El paquete conserva consultas por período, territorio, sexo, edad y grupo ilustrativo de localización, incluidos conteos exactos de personas distintas al combinar años. Para hacerlo, el prototipo calcula márgenes agregados por combinaciones de esas dimensiones; no guarda IDs de personas o tumores en el paquete.

El repo ofrece perfiles Django separados. `config.settings_admin` expone las rutas de acceso, cuentas, cargas y publicación; `config.settings_public` solo registra archivos estáticos, usa una base de datos dummy que rechaza consultas y monta las rutas públicas. Configurar `RNC_PUBLIC_RELEASE_ROOT` igual en ambos procesos; el servicio administrativo escribe allí y el público debe montarlo solo de lectura. `PRIVATE_STORAGE_ROOT` permanece únicamente en el servicio administrativo. `RNC_PUBLIC_SITE_URL` y `RNC_ADMIN_ORIGIN` definen las direcciones que conectan la interfaz y los enlaces administrativos.

Para probar ambos perfiles en local, después de crear/migrar el entorno y preparar un corte sintético:

```bash
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" DJANGO_SETTINGS_MODULE=config.settings_admin python manage.py runserver 127.0.0.1:8011
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" DJANGO_SETTINGS_MODULE=config.settings_public python manage.py runserver 127.0.0.1:8010
```

La semilla local genera el paquete al publicar. Para regenerarlo desde la publicación activa existente, ejecutar `DJANGO_SETTINGS_MODULE=config.settings_admin python manage.py sync_public_release`. El comando valida que el corte siga siendo sintético. El perfil predeterminado `config.settings` conserva ambas áreas para desarrollo local y **no** constituye separación de despliegue.

Este cubo está habilitado solo para datos sintéticos: incluye muchos agregados solapados y aún no aplica supresión de celdas ni controles de inferencia. No cargar datos del RNC ni desplegar el perfil público con datos reales hasta que el RNC valide `Q-007`/`Q-027`, el esquema de publicación y la operación de revisión. La base administrativa sigue siendo SQLite local y los perfiles no son una configuración productiva aprobada.

## Recorrido

- **Inicio:** indicadores del último año y localizaciones principales de la publicación activa; cambia al publicar/revocar.
- **Consulta `/consulta/`:** filtros de período, territorio, sexo, edad y localización; tumores o personas distintas; conteos, porcentajes, tasa cruda/específica y ajuste directo Segi–Doll candidato.
- **Gráficos:** barras horizontales, columnas, líneas, agrupadas, apiladas, porcentuales, circular y anillo. Solo se genera el gráfico elegido. El backend rechaza combinaciones incompatibles. Los gráficos por sexo respetan la misma selección.
- **Exportaciones:** PNG, SVG, PDF con gráfico y detalle tabular, CSV y Excel. Incluyen filtros, unidad, condición sintética, versión y contexto metodológico. La caché de exportaciones está ligada a versión; no evita comprobar la publicación activa.
- **Privacidad de consulta:** explorar y descargar no requiere cuenta ni crea un historial individual. `/consulta/` responde con `Cache-Control: no-store` y `Referrer-Policy: no-referrer`. El servidor/proxy puede mantener sus propios access logs; antes de desplegar deben configurarse para no conservar los filtros de la URL sin finalidad, acceso y retención acordados. No se registran todavía métricas públicas agregadas.
- **Publicación pública/privada:** el corte activo se exporta como cubo agregado versionado; las vistas del perfil público consultan ese cubo sin leer filas privadas. Los perfiles `settings_admin` y `settings_public` separan URLconf y permisos de datos; el perfil público no instala los modelos de administración y no tiene almacenamiento privado configurado. Solo prototipo sintético; falta política RNC para inferencia/supresión.
- **Administración:** carga CSV, informe técnico, historial de entregas con paginación, publicación y revocación auditadas. El CSV de actualización descargable añade un tumor sintético al corte activo y permite ensayar otra publicación. Un corte sustituye el conjunto completo anterior; no hay cargas incrementales ni restauración automática de una publicación revocada. Las descargas ya realizadas no pueden retirarse.
- **Usuarios:** interfaz propia con búsqueda/paginación, altas, edición, activación/desactivación y roles. Las invitaciones permiten elegir contraseña sin que soporte la conozca. La contraseña temporal obliga a cambiarla antes de navegar. Recuperación por enlace temporal de una hora; cambio autenticado con contraseña actual.

## PWA futura — propuesta, no implementada

La dirección documentada es una PWA solo para consulta pública: instalada en el dispositivo, podría generar gráficos offline a partir de un paquete de agregados aprobados con corte, versión y fecha visibles. No incluirá administración, sesiones administrativas, microdatos ni respuestas restringidas. El panel seguirá online y autorizado por el servidor. No se usará la detección del navegador ni una hora de desconexión como control de seguridad. El contenido, cálculo, actualización y política de copias offline siguen pendientes; ver [arquitectura objetivo y operación](docs/ARQUITECTURA-OBJETIVO-OPERACION.md) y [DEC-013](../rnc-research/docs/07-decisiones/DEC-013-pwa-solo-publica.md).

Roles propuestos para el MVP: `operator` (cargas), `publisher` (cargas, publicación/revocación), `superadmin` (todas las capacidades y cuentas). Un superusuario Django también tiene acceso de soporte. Son roles locales de producto, no designaciones institucionales aprobadas. La ruta antigua `/admin/` redirige a Usuarios del portal; las páginas internas del administrador Django ya no se exponen, para evitar caminos que eludan las políticas de cuentas de la interfaz propia.

## Entrada sintética y privacidad

El CSV de demostración usa 10 columnas, en este orden:

`synthetic,person_id,tumor_id,period,territory_id,sex_id,age_group_id,site_id,population,standard_weight`

No es el contrato RNC de 84 columnas. Los campos categóricos llevan identificadores de catálogos con `concept_id`, `name`, `description`, cero o más `identifiers` externos y metadatos de versión/estado; la interfaz resuelve las etiquetas desde esos catálogos. `territory_id` usa los códigos de provincia documentados en el Manual RNC VII; los IDs de sexo, edad y grupos de localización ilustrativos son internos del demo y no tienen crosswalk ICD-O. La entrada RNC deberá preservar literalmente `TOPO`, `MORF` y cada código de origen, más su sistema/edición; las correspondencias entre ediciones o clasificadores se gestionarán aparte y con versión. El usuario identifica `509` como TOPO de mama bajo ICD-O-2 en el formato recibido; falta cotejar esa forma y los demás campos con el diccionario autorizado. El Manual documenta CIE-O-3/ICCC-3; IARC publicó tablas finales ICD-O-4 en julio de 2026, pero esa actualización internacional no cambia automáticamente la codificación cubana documentada. `site_id` sigue siendo una agrupación sintética, no el nomenclador completo que requiere el producto. Antes de copiar tablas oficiales extensas a la web hay que obtener/confirmar permiso de reproducción y traducción; ver [Q-002 y evidencia de clasificación](../rnc-research/docs/05-requisitos/mapa-de-preguntas.md). La interfaz futura deberá presentar código literal, sistema/edición, nombre, descripción y fuente con ayuda accesible al pasar el puntero, enfocar o tocar el código. El directorio de unidades informantes del Anexo 1 se conserva como catálogo versionado, con filas repetidas o discordantes marcadas. Ningún catálogo convierte este contrato en el formato real autorizado por el RNC. Exige `synthetic=TRUE`, identificadores `SYN-P-` / `SYN-T-`, IDs admitidos, coherencia de personas/estratos, claves de tumor únicas y cobertura completa de ambos sexos y 18 grupos etarios por territorio/año. No incluye nombres personales. El límite local es 12 MB y 60 000 filas. Los marcadores no demuestran por sí mismos que un archivo sea sintético: el responsable no debe cargar datos reales.

Los identificadores de persona y tumor sintéticos no salen a consultas ni exportaciones públicas. Los originales y representaciones privadas usan claves opacas y permisos de filesystem restringidos, fuera de cualquier ruta pública. La BD registra metadatos, huellas, responsables, estados, informes y auditoría, no las filas nominales. La validación es atómica; las entregas rechazadas conservan su informe y original privado cuando cumplen el límite/extensión. La misma huella no crea otra entrega.

El importador admite una misma persona en varios años, conservando su identidad sintética y la coherencia de estrato dentro de cada año. El conteo de personas es único en la selección completa, incluso al combinar años. Las categorías por edad, territorio, localización o período pueden solaparse y no se suman para obtener personas distintas. Una persona puede aparecer en varias localizaciones: sus conteos por localización no se suman ni se ofrecen como composición circular. Los denominadores son sintéticos y se deduplican por año/territorio/sexo/edad; filtrar una localización no reduce la población denominadora. Los pesos Segi–Doll y métodos son candidatos, pendientes de cotejo RNC.

## Organización y trazabilidad

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

`main` es la rama predeterminada protegida. El trabajo se realiza en `develop`; los cambios hacia `main` pasan por PR y el control `repository-policy`. Ver [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

Versionar código, migraciones, pruebas y fixtures agregadas permitidas. `.gitignore` excluye documentos de trabajo, evidencias, archivos privados, bases locales, correo y secretos. `docs/` contiene evidencia local no publicada. No añadir `BD PARA DANI.csv` ni ningún archivo de salud identificable.

## Verificación y límites

El 20-10-2026 pasaron **57 pruebas Django y 1333 comprobaciones de navegador**, con **182 capturas** en PC (1440), laptop (1024) y móvil emulado (390). Se recorrieron formularios y persistencia de errores, alineación de columnas en las tablas de Inicio, cortes, Consulta y usuarios, acceso visible desde Inicio, sincronización de sesión entre pestañas, permisos, publicación/revocación, ocho gráficos y cinco exportaciones. La prueba de frontera cubre carga sintética → publicación → lectura con perfil público y BD dummy → revocación; confirma rutas administrativas ausentes y un paquete sin IDs de persona/tumor. Informe, galería y resultados locales: `docs/revision-completa-2026-10-20/`. El runner reproducible usa BD/archivos/cuentas/buzón/publicación temporales y puerto libre. No equivale a auditoría de seguridad, validación RNC ni despliegue de dos procesos separados; SMTP real y dispositivos físicos siguen pendientes.

La revisión de interfaz y entradas se traza en `SRC-PRJ-003` → `EVD-103..104` → `DEC-012`. Los formularios previenen entradas incompatibles según campo y el servidor repite la validación; nombres y contraseñas conservan símbolos legítimos. Errores enlazados al control y política CSP complementan el tratamiento seguro de datos.

SQLite, caché local, auditoría en BD y servidor de desarrollo son para este entorno. Antes de uso institucional: contrato de entrada autorizado, política de divulgación, cálculo contrastado, SMTP/TLS, caché compartida y límites de proxy, MFA/operación de soporte, auditoría resistente a manipulación, retención, backups/restauración coordinados, pruebas de concurrencia, seguridad y accesibilidad. El secreto de desarrollo provoca un error si se intenta arrancar con DEBUG desactivado; esto no sustituye configurar el resto del despliegue.
