# Verificación de PWA y consulta local — 10-11-2026

## Alcance

Prototipo PWA sobre perfil público aislado, únicamente con publicaciones agregadas sintéticas. Se probó en Chrome 156.0.8078.47, Linux, con servidor Django WSGI temporal en loopback. Los artefactos se aislaron y eliminaron al salir. No se usó la base de desarrollo, datos clínicos ni despliegue remoto.

El service worker trabaja en el origen público (`/`). Precarga solo el shell local sin datos y recursos estáticos. La navegación pública intenta la red y usa el shell local si falla. No almacena administración, resultados de consulta ni el endpoint del paquete. La consulta offline opera sobre una copia guardada explícitamente en IndexedDB y calcula agregados en un Web Worker.

## Resultados

| Corrida | Resultado |
|---|---|
| Suite Django regular con cobertura de ramas, sin `long_running` | Corrida de cobertura: 73/73 pasaron; 83% de cobertura combinada. Suite completa más reciente: 80/80 pasaron en 359.613 s. `exports.py` 99%, `public_forms.py` 97%, `aggregate_statistics.py` 88%, `public_portal.py` 86%. |
| Matriz Django `long_running`, sin instrumentación | 3/3 pasaron en 325 s: 46 400 cruces de selectores/filtros, 262 158 subconjuntos por filtro y 750 exportaciones. |
| PWA en Chromium | Corrida base: 51/51; verificación anterior: 100/100; worktree aislado 11-11: 183/183. Añade pluralización cotejada con GNU gettext para ocho cantidades por borrador, fecha local visible, nueve catálogos compilados en temporal, persistencia/fallback, categorías, exportaciones y datos numéricos localizados. Shell sin conexión conserva locale y `dir`; RTL para árabe y urdu cabe a 390 px. Sin excepciones JS ni HTTP 5xx. |
| E2E general en Chromium | Worktree aislado 11-11: 1 520 comprobaciones pasaron en PC (1440 px), laptop (1024 px) y móvil emulado (390 px); 197 capturas en `docs/revision-completa-2026-11-11/`. Sin errores JS, recursos fallidos ni HTTP 500. |
| Carga sintética (worktree aislado 11-11) | 28 800 filas, 62 073 celdas agregadas, paquete de 8 217 079 bytes. 290/290 GET correctos con concurrencia 1, 4, 8 y 16; recuperación 79,09 ms. |

### Rendimiento y recursos

En la corrida del worktree aislado, el navegador tardó 97,5 ms en leer el paquete JSON de 8,2 MB y 161,5 ms en inicializar el worker con 62 073 celdas. Procesó 30 consultas locales con p50 13,8 ms, p95 14,6 ms y máximo 28,8 ms; ida/vuelta del worker: p50 14,1 ms y p95 15 ms. Heap JS reportado: 22 722 073 bytes. Django usó 22,003 s CPU durante 20,847 s de pared; RSS observado antes/después: 115 660/172 836 KiB; máximo reportado: 172 672 KiB. La solicitud de recuperación respondió en 79,09 ms con 40 409 bytes.

| Concurrencia servidor | Solicitudes correctas | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|
| 1 | 10/10 | 67,40 ms | 234,06 ms | 234,06 ms |
| 4 | 40/40 | 269,79 ms | 380,99 ms | 384,76 ms |
| 8 | 80/80 | 570,07 ms | 676,19 ms | 830,20 ms |
| 16 | 160/160 | 1 140,20 ms | 1 402,92 ms | 2 373,79 ms |

Estas cifras caracterizan esta máquina, versión, fixture y topología local. No son un SLA ni predicen rendimiento en móviles, redes cubanas, CDN o infraestructura institucional.

### Revalidación de traducciones

En la revalidación aislada en worktree `codex/translation-release-gate` (11-11-2026), el recorrido PWA pasó 183/183 comprobaciones en Chrome 156: nueve previews de locale comprobaron la fecha visible de publicación y compararon la forma plural que el catálogo JavaScript selecciona para 0, 1, 2, 3, 5, 11, 21 y 101 con GNU gettext. La comparación verifica el mecanismo de selección, no la calidad lingüística de las traducciones. El preview administrativo pasó 154/154 verificaciones e incluyó fechas de recepción localizadas en la lista y el detalle para los once locales. La suite Django completa pasó 81/81 en 297,747 s, incluidas las pruebas largas; el recorrido UI pasó 1 520/1 520 y 197 capturas. La prueba de estrés completó 290/290 GET de solo lectura con concurrencia 1, 4, 8 y 16. Las 21 pruebas unitarias de catálogo/gate también pasaron; el gate mantuvo los 11 locales parciales al faltar manifiestos de revisión.

Revalidación del fallback frío (11-11-2026): 183/183 comprobaciones PWA aprobadas en Chrome 156 tras cambiar la caché del service worker a `v8`. La nueva auditoría asegura igualdad exacta entre mensajes de respaldo offline y gettext para todos los idiomas activos. La suite enfocada de catálogo/auditoría/gate pasó 31/31 tras ampliar auditorías JS y de calidad de borradores. El gate sigue reportando los 11 idiomas parciales por falta de manifiestos de revisión humana.

La revisión estática de JavaScript inspeccionó 9 archivos de producción y no encontró literales directos en destinos DOM, ARIA, validación del navegador, opciones o diálogos. Se añadió `scripts/audit_unmarked_javascript_text.py` con pruebas de detección y exclusión de texto ya localizado; es una auditoría acotada a esos sinks y no sustituye la revisión visual/e2e.

Validación y limpieza de borradores (11-11-2026): se corrigió “Marque esta confirmación” por “Marque esta casilla” en fuente y catálogo español; inglés y nueve sugerencias fuzzy se alinearon sin publicar estas últimas. Se corrigieron siete cadenas españolas pendientes en francés, etiquetas de gráficos confundidas con bares/pasteles en chino y ruso, términos de tasas en ruso y bloques enteros de inglés mezclados en chino. La auditoría ahora detecta esos patrones y conserva excepciones para acrónimos/nombres válidos; CI ejecuta la auditoría completa de borradores junto con sus pruebas. PWA pasó 183/183, preview administrativo 308/308, suite Django 83/83 y pruebas de catálogo/auditoría 31/31. Los borradores siguen fuzzy e inactivos.

El último recurso del service worker, usado cuando todavía no existe una copia localizada de la respuesta, también queda auditado: el mensaje para cada idioma activo debe coincidir exactamente con `django.po`. `scripts/audit_service_worker_fallbacks.py` verifica esto y CI ejecuta la auditoría y sus pruebas; al activar otro idioma se exige añadir su mensaje revisado.

## Ampliación de cobertura de errores (11-11-2026)

La revisión detectó que las respuestas CSRF 403 y 404 del perfil combinado entregaban textos españoles sin gettext. Se marcaron los mensajes, se añadieron traducciones inglesas y borradores `fuzzy` para los nueve locales adicionales, y el compilador activo produjo 631 mensajes Django en inglés. El preview de rutas se amplió para cubrir 16 rutas de cuenta, contenido público y administración, además de acceso sin sesión y respuestas 403/404. Resultado: 286/286 comprobaciones aprobadas entre los once locales. Los borradores siguen inactivos y la ejecución no constituye revisión lingüística.

## Auditoría de mensajes del backend (reporte previo)

La inspección AST de destinos de mensajes reveló errores de carga CSV y mensajes de nomencladores aún sin marca gettext, además de validaciones auxiliares. Se marcaron y añadieron al catálogo inglés; se generaron sugerencias `fuzzy` para los nueve locales. La auditoría `scripts/audit_unmarked_python_messages.py` cubre respuestas HTTP, errores de formulario, mensajes Django y excepciones mostradas por vistas; revisó 66 archivos sin encontrar literales pendientes. El preview añadió un nomenclador y una carga CSV sintéticos únicos por locale: 308/308 en los once idiomas. La suite Django pasó 82/82 en 337,545 s y las pruebas de traducción/auditorías 24/24. Chromium PWA volvió a pasar 183/183. Catálogos actuales: 702 mensajes Django y 162 JS en inglés; 702 + 162 por cada borrador adicional. Todos los idiomas continúan parciales.

## Limitaciones

- La instalación interactiva del navegador no se automatizó; tampoco Android, iOS ni Safari. Offline se validó en Chrome de escritorio.
- Exportaciones offline implementadas: CSV, PNG e impresión/PDF del navegador. XLSX y SVG siguen disponibles online.
- No se evaluaron WCAG completa, lector de pantalla físico, participantes, auditoría de seguridad especializada, equipos/redes reales, restauración u operación multi-proceso.
- Copias offline pueden quedar obsoletas después de revocación y el navegador puede desalojar IndexedDB. No se probó publicación real: faltan autorización RNC, reglas de divulgación/supresión, método epidemiológico validado y política de retención.
- Los nueve previews adicionales usan traducciones automáticas `fuzzy`, compiladas solo en un directorio temporal para probar la infraestructura. No se sirvieron desde los catálogos de la aplicación y no se consideran revisión lingüística ni validación editorial; permanecen inactivos.

## Reproducir

Comandos y aislamiento: [`TESTING.md`](TESTING.md). Los JSON detallados/galerías se generan bajo `docs/` (ignorado por Git) con `scripts/review_pwa.py`, `scripts/stress_pwa.py` y `scripts/review_ui.py`.
