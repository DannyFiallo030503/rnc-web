# Idioma, acceso administrativo y sesión

Petición del responsable del 12-11-2026: reparar el selector de idioma y la mezcla
español/inglés, recuperar acceso a Administración desde la web online y limitar
la sesión a doce horas desde el inicio. Petición adicional: recuperar Acerca de
y sus apartados en el sidebar, incluido /el-rnc/#que-hacemos.

## Cambios

La navegación usa etiquetas diferidas al idioma de cada petición. El selector
actualiza la cookie mediante el endpoint Django y conserva ruta, filtros y
fragmento. Cuando no hay red, navega al shell del idioma elegido. Los shells
públicos español/inglés y los catálogos JavaScript se distinguen por idioma,
incluso si la cookie del navegador contiene otro valor. Al reconectar se
sincroniza la preferencia elegida sin red.

Los textos nuevos de filtros, cohortes, controles de gráficos, notas y
exportaciones se incorporan a los catálogos. El cliente local reutiliza las
traducciones del servidor. Los rótulos de localizaciones/grupos se traducen para
la presentación, conservando códigos, catálogo original y significado del DOCX;
no se reclasifican tumores. Las denominaciones propias y los títulos literales de
las fuentes conservan su identidad. El paquete conserva etiquetas canónicas y
el cliente las presenta con el catálogo del idioma activo.

Acerca de vuelve a la navegación pública, con enlaces a sus ocho apartados.
El enlace de Administración apunta a RNC_ADMIN_SITE_URL/acceso/ (por defecto,
http://127.0.0.1:8011/acceso/). Solo se ofrece en la web conectada; se oculta
sin conexión y en modo standalone/iOS PWA. El proceso público conserva BD dummy:
el enlace no incorpora cuentas ni administración a la caché pública.

La sesión se fija a 43 200 segundos desde el login correcto mediante una fecha
de expiración absoluta. La actividad no amplía ese plazo. El middleware también
comprueba la marca del inicio, cierra sesiones vencidas y solicita autenticación
de nuevo, aunque una cookie o una modificación posterior intenten prolongarla.
Las sesiones heredadas sin marca requieren iniciar sesión de nuevo; no se
inventa su hora histórica de apertura ni se les concede un plazo adicional. No cambia ninguna
contraseña ni se crean cuentas reales para verificarlo.

## Verificación

Suite de aplicación: 61 pruebas aprobadas en base/almacenamiento temporales,
incluidas caducidad fija, actividad sin renovación, marca vencida con cookie aún
vigente, catálogo JavaScript explícito y navegación Acerca de en ambos idiomas.
No se envían correos. Las pruebas de cuentas utilizan únicamente cuentas de QA
no clínicas; las estadísticas conservan su fuente real.

La comprobación del plazo usa el servidor y el reloj de prueba; no se afirma
haber esperado doce horas reales con una sesión humana abierta. Los cambios
quedan en el worktree/rama codex/chart-filters-layout.

Verificación Chromium completada: 11 comprobaciones de cambio ES/EN online y
sin red, rótulos de consulta y categorías, Acerca de con ancla que-hacemos,
acceso al formulario administrativo, ocultación offline/standalone y conservación
del idioma al reconectar. No se utilizaron credenciales de cuentas humanas.
La URL local mantiene el idioma y la sincronización de cookie se serializa para
que una petición anterior no sobrescriba una selección más reciente. El servidor
reconectado confirma la disponibilidad; no se depende solo del evento online.
Suite final: 61 pruebas, OK, 51,605 s. No hay migraciones nuevas.
