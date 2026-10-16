# RNC Web

Portal de consulta de incidencia de cáncer en Cuba. MVP local funcional con datos exclusivamente sintéticos; no es un despliegue institucional ni está autorizado para recibir microdatos reales.

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

Para enviar correos reales, configurar SMTP autorizado y un remitente válido mediante variables de entorno. `.env.example` describe las variables; el proyecto no carga `.env` automáticamente. `RNC_PUBLIC_ORIGIN` debe coincidir con la dirección accesible al destinatario y utilizar HTTPS en un despliegue compartido. No usar el nombre Host de una solicitud para construir enlaces de seguridad.

## Recorrido

- **Inicio:** indicadores del último año y localizaciones principales de la publicación activa; cambia al publicar/revocar.
- **Consulta `/consulta/`:** filtros de período, territorio, sexo, edad y localización; tumores o personas distintas; conteos, porcentajes, tasa cruda/específica y ajuste directo Segi–Doll candidato.
- **Gráficos:** barras horizontales, columnas, líneas, agrupadas, apiladas, porcentuales, circular y anillo. Solo se genera el gráfico elegido. El backend rechaza combinaciones incompatibles. Los gráficos por sexo respetan la misma selección.
- **Exportaciones:** PNG, SVG, PDF con gráfico y detalle tabular, CSV y Excel. Incluyen filtros, unidad, condición sintética, versión y contexto metodológico. La caché de exportaciones está ligada a versión; no evita comprobar la publicación activa.
- **Administración:** carga CSV, informe técnico, historial de entregas con paginación, publicación y revocación auditadas. El CSV de actualización descargable añade un tumor sintético al corte activo y permite ensayar otra publicación. Un corte sustituye el conjunto completo anterior; no hay cargas incrementales ni restauración automática de una publicación revocada. Las descargas ya realizadas no pueden retirarse.
- **Usuarios:** interfaz propia con búsqueda/paginación, altas, edición, activación/desactivación y roles. Las invitaciones permiten elegir contraseña sin que soporte la conozca. La contraseña temporal obliga a cambiarla antes de navegar. Recuperación por enlace temporal de una hora; cambio autenticado con contraseña actual.

Roles propuestos para el MVP: `operator` (cargas), `publisher` (cargas, publicación/revocación), `superadmin` (todas las capacidades y cuentas). Un superusuario Django también tiene acceso de soporte. Son roles locales de producto, no designaciones institucionales aprobadas. La ruta antigua `/admin/` redirige a Usuarios del portal; las páginas internas del administrador Django ya no se exponen, para evitar caminos que eludan las políticas de cuentas de la interfaz propia.

## Entrada sintética y privacidad

El CSV de demostración usa 11 columnas, en este orden:

`synthetic,person_id,tumor_id,name,period,territory,sex,age_group,site,population,standard_weight`

No es el contrato clínico RNC de 84 columnas. Exige `synthetic=TRUE`, identificadores `SYN-P-` / `SYN-T-`, categorías admitidas, coherencia de personas/estratos, claves de tumor únicas y cobertura completa de ambos sexos y 18 grupos etarios por territorio/año. El límite local es 12 MB y 60 000 filas. Los marcadores no demuestran por sí mismos que un archivo sea sintético: el responsable no debe cargar datos reales.

Los nombres e identificadores no salen a consultas ni exportaciones públicas. Los originales y representaciones privadas usan claves opacas y permisos de filesystem restringidos, fuera de cualquier ruta pública. La BD registra metadatos, huellas, responsables, estados, informes y auditoría, no las filas nominales. La validación es atómica; las entregas rechazadas conservan su informe y original privado cuando cumplen el límite/extensión. La misma huella no crea otra entrega.

El importador admite una misma persona en varios años, conservando su identidad sintética y la coherencia de estrato dentro de cada año. El conteo de personas es único en la selección completa, incluso al combinar años. Las categorías por edad, territorio, localización o período pueden solaparse y no se suman para obtener personas distintas. Una persona puede aparecer en varias localizaciones: sus conteos por localización no se suman ni se ofrecen como composición circular. Los denominadores son sintéticos y se deduplican por año/territorio/sexo/edad; filtrar una localización no reduce la población denominadora. Los pesos Segi–Doll y métodos son candidatos, pendientes de cotejo RNC.

## Organización y trazabilidad

- `config/`: configuración y puntos de entrada Django.
- `public_site/models.py`, `migrations/`: metadatos de cargas, publicación activa, auditoría y políticas/correo de cuentas.
- `public_site/services.py`: almacenamiento privado, validación y transiciones de cortes.
- `public_site/statistics.py`: selección, agregación y personas distintas.
- `public_site/portal.py`: vistas del portal; `exports.py`: renderizado de imágenes, PDF y hojas de cálculo.
- `public_site/accounts.py`, `forms.py`, `middleware.py`: gestión de cuentas, contraseñas y restricciones.
- `templates/`, `static/`: interfaz propia; Chart.js 4.5.1 se distribuye localmente con licencia MIT en `static/vendor/`.
- `analytics/`: funciones estadísticas y fixtures agregadas anteriores; el portal actual usa la publicación privada persistente.

Investigación y requisitos: repositorio hermano `rnc-research`. Dirección de esta ampliación: `SRC-PRJ-002` → `EVD-101..102` → `DEC-012-mvp-funcional-sintetico.md`; capacidades relacionadas `REQ-F-001..015`, `REQ-D-003..005`. El adelanto funcional no cambia por sí mismo el alcance aprobado del Anexo A.

## Ramas y archivos

`main` es la rama predeterminada protegida. El trabajo se realiza en `develop`; los cambios hacia `main` pasan por PR y el control `repository-policy`. Ver [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

Versionar código, migraciones, pruebas y fixtures agregadas permitidas. `.gitignore` excluye documentos de trabajo, evidencias, archivos privados, bases locales, correo y secretos. `docs/` contiene evidencia local no publicada. No añadir `BD PARA DANI.csv` ni ningún archivo de salud identificable.

## Verificación y límites

La revisión local del 16-10-2026 comprobó renderizado de Inicio/consulta/acceso/panel/usuarios, respuestas de los cinco formatos de exportación, ausencia de errores JavaScript en las pantallas privadas recorridas y presentación móvil de Inicio/Usuarios. Se inspeccionó visualmente el PDF exportado. Evidencia local: `docs/revision-ui-2026-10-16/`. No equivale a una auditoría de seguridad ni a validación RNC. La suite y el script de regresión existentes corresponden al recorrido anterior; no se ejecutaron ni actualizaron durante esta ampliación.

SQLite, caché local, auditoría en BD y servidor de desarrollo son para este entorno. Antes de uso institucional: contrato de entrada autorizado, política de divulgación, cálculo contrastado, SMTP/TLS, caché compartida y límites de proxy, MFA/operación de soporte, auditoría resistente a manipulación, retención, backups/restauración coordinados, pruebas de concurrencia, seguridad y accesibilidad. El secreto de desarrollo provoca un error si se intenta arrancar con DEBUG desactivado; esto no sustituye configurar el resto del despliegue.
