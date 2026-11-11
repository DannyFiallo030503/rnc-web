# Levantar RNC Web en local

Guía para ejecutar el prototipo de desarrollo en esta computadora. El modo inicial usa Django, SQLite y datos sintéticos.

## Requisitos

- Python 3.12.
- Terminal ubicada en el repositorio `rnc-web`.
- Acceso a Internet durante la primera instalación de dependencias.

## Primera ejecución

Desde la carpeta `Practicas 2`:

```bash
cd rnc-web
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8010
```

Al crear el superusuario, escribe un nombre, correo opcional y contraseña para esta computadora. No reutilices una contraseña institucional.

Cuando Django muestre que el servidor está listo, abre:

- Inicio: <http://127.0.0.1:8010/>
- Consulta: <http://127.0.0.1:8010/consulta/>
- Acceso administrativo: <http://127.0.0.1:8010/acceso/>

`seed_demo` crea y publica un corte de demostración. Solo funciona con `DEBUG` activado. Si ya existe una entrega, conserva el estado local y no genera otra. Los datos, la base SQLite, archivos privados y paquetes agregados se guardan en esta computadora.

## Ejecuciones posteriores

Abre una terminal en `rnc-web` y activa el entorno antes de iniciar Django:

```bash
source .venv/bin/activate
python manage.py runserver 127.0.0.1:8010
```

No vuelvas a ejecutar `migrate`, `createsuperuser` ni `seed_demo` en cada inicio. Ejecuta `migrate` cuando cambien las migraciones. Ejecuta `seed_demo` solo para una base local nueva sin entregas.

Para detener el servidor, vuelve a la terminal y presiona `Ctrl+C`.

## Correo local para invitaciones y recuperación

El envío de correo no es necesario para consultar el portal. Si ensayas invitaciones o recuperación de cuentas, abre una segunda terminal en `rnc-web`, activa el mismo entorno y ejecuta:

```bash
source .venv/bin/activate
python manage.py deliver_account_mail --watch
```

Django guarda los mensajes en `private/mail/`; no los envía a una dirección real. Abre localmente el mensaje para seguir el enlace. Ese enlace permite acceder o cambiar una contraseña: no lo compartas ni lo publiques.

## Modo opcional con procesos público y administrativo separados

El modo sencillo anterior ejecuta el perfil combinado de desarrollo. Para probar las configuraciones separadas, primero inicializa la base y genera la publicación sintética con el modo sencillo. Detén ese servidor con `Ctrl+C`. Luego, desde dos terminales en `rnc-web`, activa `.venv` en ambas y ejecuta:

Terminal administrativa:

```bash
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" \
RNC_ADMIN_ORIGIN="http://127.0.0.1:8011" \
RNC_PUBLIC_SITE_URL="http://127.0.0.1:8010" \
DJANGO_SETTINGS_MODULE=config.settings_admin \
python manage.py runserver 127.0.0.1:8011
```

Terminal pública:

```bash
RNC_PUBLIC_RELEASE_ROOT="$PWD/public_releases" \
RNC_PUBLIC_SITE_URL="http://127.0.0.1:8010" \
DJANGO_SETTINGS_MODULE=config.settings_public \
python manage.py runserver 127.0.0.1:8010
```

Abre la consulta pública en <http://127.0.0.1:8010/> y la administración en <http://127.0.0.1:8011/>. En este perfil el servicio público lee la carpeta de agregados y no usa la base administrativa. Sigue siendo una separación local de demostración; no es un despliegue productivo.

Con el perfil público abierto, visita <http://127.0.0.1:8010/consulta-offline/>. Pulsa **Guardar / actualizar publicación** mientras estás conectado y luego **Calcular en este dispositivo**. Para comprobar el modo offline, carga una vez esa pantalla, desconecta la red y vuelve a abrirla. Los datos de esta demostración son sintéticos. Usa **Eliminar copia local** para borrar el paquete de IndexedDB del navegador. El service worker solo se instala en este perfil separado; el modo combinado no habilita la PWA.

## Si algo falla

- **Puerto ocupado:** detén el otro servidor local o elige otro puerto. Si cambias 8010, define también `RNC_PUBLIC_SITE_URL` y `RNC_PUBLIC_ORIGIN` con la dirección elegida antes de iniciar Django.
- **No encuentra Django:** activa `.venv` y repite `python -m pip install -r requirements.txt`.
- **La consulta indica que no hay publicación:** inicia el perfil combinado y ejecuta `python manage.py seed_demo` una vez. Si ya existen entregas, el comando no las reemplaza.
- **Cambió el modelo de datos:** ejecuta `python manage.py migrate` con `.venv` activo.
- **El correo no aparece:** confirma que `deliver_account_mail --watch` sigue corriendo y revisa `private/mail/`.

## Límites

Este repositorio sirve para desarrollo y demostración local. Usa solo datos sintéticos. No cargues `BD PARA DANI.csv`, datos clínicos ni información de salud real. El paquete agregado sintético actual no tiene una política institucional de supresión de celdas y no está autorizado para publicarse con datos reales. Las credenciales creadas aquí son locales; no se reutilizan para servicios compartidos.

Para detalles del producto y la arquitectura, consulta el [README del repositorio](README.md) y `docs/ARQUITECTURA-OBJETIVO-OPERACION.md`.
