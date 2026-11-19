# Distribución portátil de consulta

Objetivo: extraer el ZIP y abrir `Abrir RNC.cmd` en Windows de 64 bits. El comando ejecuta el intérprete incluido, inicia Waitress únicamente en 127.0.0.1:8765 y abre el navegador. La ventana del servidor permanece abierta y se cierra con Ctrl+C o cerrando su ventana. No instala componentes ni requiere Internet, privilegios administrativos o Docker.

La distribución es solo de consulta. Usa `settings_portable`, sin base administrativa ni rutas de cuentas/cargas. Conserva los agregados del corte suministrado, su huella y los recursos públicos. No incluye archivos de origen clínico, identificadores, contraseñas ni cuentas. Online/Offline informa disponibilidad del servidor local, no conectividad de Internet.

El intérprete embebido procede de python.org; los paquetes binarios de PyPI. Las versiones exactas se conservan en `requirements-windows.lock`; la entrega incluye licencias, metadatos y huellas de componentes. Los paquetes se descargan para Windows x64/CPython 3.13 antes de construir. El destinatario no descarga dependencias.

Construcción desde Linux o Windows: descargar el ZIP embebido Python 3.13.17 x64 y las wheels de la lista bloqueada con `pip download --platform win_amd64 --python-version 3.13 --implementation cp --abi cp313 --only-binary=:all:`. Ejecutar `build.py --runtime <zip> --wheels <directorio> --release <publicación> --output <salida-nueva>`. El constructor acepta exclusivamente rutas relativas seguras de los archivos ZIP y copia código versionado y los agregados señalados por el manifiesto.

Verificación: el intérprete de Windows, Django y Waitress arrancaron bajo Wine; la importación científica completa no pudo comprobarse allí por una función UCRT no implementada en Wine. El lanzador y las rutas del sitio se comprobaron con Python Linux y las dependencias de la aplicación. Esto no acredita una ejecución nativa de Windows: antes de enviar a revisión general se debe comprobar el primer arranque en un Windows real, gráficos, exportaciones y funcionamiento sin Internet. No se afirma validación de Windows sin esa ejecución.

Se eligió un puerto fijo para conservar la copia del navegador entre aperturas. Si está ocupado se muestra un error y no se detienen programas ajenos. Las políticas de ejecución de cada organización pueden requerir revisión por su soporte informático.
