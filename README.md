# RNC Web

Portal web de consulta de estadísticas de incidencia del Registro Nacional de Cáncer de Cuba.

## Ramas y contribuciones

`main` es la rama predeterminada y está protegida: recibe PR desde `develop`, exige el control `repository-policy` y no permite borrado ni force push. El trabajo se realiza en `develop`, cuya única restricción es impedir su eliminación. Consulta el [flujo de contribución](.github/CONTRIBUTING.md).

Se versionan el código, las pruebas y las fixtures sintéticas permitidas. La documentación de trabajo en `docs/`, las capturas/resultados, archivos privados, bases locales y secretos quedan excluidos. Las referencias a `docs/` de este README corresponden a documentos locales; la documentación de referencia se conserva en `rnc-research`. `.gitignore` no sustituye la revisión del contenido antes de fusionar.

## Estado

Este repositorio contiene una primera versión de la interfaz web de estadísticas. El explorador público presenta el estado vacío cuando no hay cortes publicados. La consulta local de ejemplo sirve agregados sintéticos con nombres reales de provincias y localizaciones; sus supuestos y límites están documentados en `analytics/fixtures/README.md`.

Python 3.12 y Django 6.1.2 se usan como base provisional del prototipo, de acuerdo con la recomendación tecnológica documentada. El estudiante ya ha usado Django y emplea Python a diario, una ventaja de experiencia para desarrollar el prototipo durante Prácticas II. El RNC no ha comunicado una preferencia previa de tecnología o diseño; el proyecto comparará opciones y llevará una recomendación que cumpla los requisitos. Se comprobarán las restricciones de infraestructura y operación antes de proponer un despliegue. SQLite solo está configurado para desarrollo local.

## Preparar el entorno local

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8010
```

Abre `http://127.0.0.1:8010/` en el navegador. Se usa `8010` porque el `8000` está ocupado en el entorno de desarrollo. Para cerrar el servidor, usa `Ctrl+C`.

## Organización

- `config/`: configuración Django y puntos de entrada ASGI/WSGI.
- `public_site/`: vistas y rutas públicas.
- `analytics/`: funciones estadísticas candidatas y consulta local de agregados ficticios; fixtures documentadas en `analytics/fixtures/README.md`.
- `templates/`: plantillas HTML.
- `static/css/`: estilos locales; no requiere bibliotecas visuales externas.
- `docs/PLAN-INICIAL.md`: etapas de trabajo conectadas con la línea base académica.
- `docs/DISENO-ARQUITECTURA-SEGURIDAD.md`: propuesta de páginas, arquitectura modular, paginación y controles de seguridad por etapas.
- `docs/ARQUITECTURA-OBJETIVO-OPERACION.md`: arquitectura objetivo del monorepo, login/roles, despliegue institucional, almacenamiento privado, backups/restauración y caché; distingue el login local ya implementado de los controles productivos pendientes.
- `docs/CONTRATO-RESULTADO-AGREGADO.md` y `docs/FLUJO-INCORPORACION-PUBLICACION.md`: contratos y flujo candidatos para revisar con requisitos/equipo RNC.

La portada presenta el explorador estadístico sin publicaciones. `/consulta-sintetica/` ofrece una vista de consulta local con datos agregados ficticios para ensayar filtros, indicadores, gráficos, tablas y descarga CSV; solo está disponible con `DEBUG=True`. `/acceso/` autentica cuentas creadas por un superusuario; no existe registro público. `/administracion/cortes/` exige una cuenta superusuario o miembro del grupo `superadmin`; se muestra su enlace solo a esas cuentas. Tras ejecutar migraciones se crea el grupo `superadmin` con permisos para gestionar usuarios y grupos en `/admin/`; sus miembros deben tener `is_staff=True`. El panel de cortes sigue siendo una vista demostrativa y aún no procesa archivos.

Todas las pantallas comparten barra superior persistente, menú lateral con páginas e índice de secciones, ruta de navegación y footer con accesos al inicio y a la consulta. En móvil el menú lateral se sustituye por un menú desplegable accesible desde la cabecera. La consulta demostrativa solo aparece con `DEBUG=True`; administración se muestra solo a cuentas con rol `superadmin`. La autenticación usa el sistema de cuentas/grupos de Django y la ruta de cortes comprueba el rol en backend. Es una base funcional local, no un despliegue productivo endurecido: faltan integración de identidad institucional, limitación de intentos, auditoría de seguridad, configuración HTTPS/secretos, política de alta/baja de usuarios y revisión de seguridad del entorno RNC.

## Verificación local

`python manage.py test` ejecuta las regresiones de acceso, cuentas, filtros y aritmética de indicadores. La revisión visual reproducible usa `scripts/review_ui.py` con Playwright (dependencia opcional en `requirements-review.txt`); crea una base temporal, cuentas sintéticas y servidor en un puerto libre asignado por el sistema, y elimina esos recursos al finalizar. Puede usar Chromium instalado mediante `RNC_REVIEW_BROWSER=/ruta/al/ejecutable` o el navegador de Playwright. Evidencias y límites de la revisión: [reporte del 15-10-2026](docs/revision-ui-2026-10-15/README.md).

## Contexto y decisiones del proyecto

La marca RNC/Cuba de la cabecera abre el login para visitantes y el panel para superadministradores. El sidebar de escritorio se pliega a una columna de iconos con nombres accesibles y conserva la preferencia en el navegador; en móvil se usa el menú desplegable. Las páginas públicas siguen disponibles sin cuenta. Solo cuentas activas con rol `superadmin` o superusuario ven Administración; la gestión en `/admin/` exige además acceso de personal (`is_staff`). Ambos accesos se comprueban en servidor.

La documentación investigativa, los requisitos trazables y las decisiones de Prácticas II se mantienen en [`../rnc-research/`](../rnc-research/). Consultar su [contexto del proyecto](../CONTEXT.md), [línea base de requisitos](../rnc-research/docs/05-requisitos/linea-base-practicas-ii.md), [esquema observado del CSV](../rnc-research/docs/05-requisitos/esquema-archivo-recibido.md) y [decisión provisional de tecnologías](../rnc-research/docs/07-decisiones/DEC-003-no-cerrar-stack.md) antes de implementar cálculos o importar datos.

## Datos de salud

No copies `BD PARA DANI.csv` ni otros datos identificables o clínicos en este repositorio. Antes de implementar una carga real, hay que confirmar con el RNC el origen y autorización del archivo, su diccionario, la unidad por fila, los códigos territoriales/tumorales y las reglas de publicación. Usa datos sintéticos cuando se acuerde preparar escenarios de prueba.
