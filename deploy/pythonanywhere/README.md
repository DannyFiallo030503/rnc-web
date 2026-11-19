# PWA en la instalación existente de PythonAnywhere

La instalación observada usa `config.settings` con cuentas y archivos privados. El perfil combinado mantiene PWA deshabilitada por defecto. Esta revisión añade `RNC_PUBLIC_PWA_ENABLED=1`, que habilita indicador, manifiesto, scripts públicos y rutas de conexión/paquete/trabajador. No carga esos scripts en las páginas administrativas.

El contexto de las vistas públicas es anónimo incluso cuando la aplicación incluye administración. Las descargas de preparación y las navegaciones del service worker omiten credenciales. La caché mantiene una lista explícita de páginas públicas y excluye administración, acceso, cuentas, paquetes y respuestas del sondeo. El enlace de administración se muestra únicamente tras confirmar el servidor y se oculta en modo independiente.

`apply_pwa_patch.py` es la plantilla del parche autocontenido: el proceso de empaquetado sustituye PAYLOAD por el contenido comprimido de los ocho archivos modificados y sus huellas previas y posteriores. El parche distribuido comprueba que no haya modificaciones desconocidas, respalda archivos y WSGI, activa la variable antes de inicializar Django, ejecuta check y collectstatic. No ejecuta migraciones ni modifica datos o credenciales. El operador pulsa Reload después de observar el éxito.

Despliegue previo, confirmado mediante la salida del operador: backup `rnc-backup-20261113-180014`; código anterior `rnc-web-anterior-20261113-180014`; migraciones 0003, 0004 y 0005 aplicadas y 156 estáticos recopilados. La inspección HTTPS posterior comprobó las páginas públicas y recursos de columnas, pero service-worker devolvió 404. El parche corrige esa configuración; su aplicación remota sigue pendiente hasta que el operador ejecute el archivo y recargue.
