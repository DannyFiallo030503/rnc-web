# Evidencia de salida de traducciones

`<locale>.json` es el registro de revisión para que un idioma pueda pasar de
parcial a completo. No lo genera el verificador ni se acepta una aprobación
implícita. Use `manifest.schema.json` para su estructura.

La puerta comprueba que:

- cada catálogo requerido existe, no contiene mensajes fuzzy/vacíos, conserva
  placeholders y plurales, y su hash/total revisado coinciden con el PO actual;
- para español, la revisión cubre además los msgid fuente en español del dominio
  Django, aunque no exista `locale/es/LC_MESSAGES/django.po`;
- consta una revisión lingüística humana con revisor, competencia, fecha e
  informe versionado por SHA-256;
- consta la validación institucional de las afirmaciones del RNC;
- las pruebas funcionales se ejecutaron sobre una revisión identificada y
  cubren las superficies pública, administración, JavaScript, exportaciones,
  funcionamiento offline y formatos, y el informe coincide con su SHA-256;
- la aprobación final declara responsable y fecha.

La puerta valida consistencia documental; no autentica la identidad, competencia
ni autoridad de quien firma. Conserve los informes y aprobaciones en el sistema
documental del proyecto y refiéralos aquí. No añada nombres, afirmaciones ni
aprobaciones inventadas. Mantenga el estado parcial hasta tener evidencia real.

Comprobar todos los locales prioritarios:

```bash
rtk .venv/bin/python scripts/translation_release_gate.py
```

Comprobar uno o más locales:

```bash
rtk .venv/bin/python scripts/translation_release_gate.py --locale en --locale es
```

## Paquete para revisión lingüística

Para entregar el inventario completo a revisores, genere un ZIP con fuente
española, referencia inglesa, borrador actual, contexto, referencias, estado
`fuzzy` y columnas para decisión/corrección/notas:

```bash
rtk .venv/bin/python scripts/export_translation_review.py \
  --locale en --locale zh-hans --locale hi --locale es --locale ar \
  --locale fr --locale bn --locale pt-br --locale id --locale ur --locale ru \
  --output locale/reviews/pending-human-review-YYYY-MM-DD.zip
```

El ZIP registra hashes de los catálogos de referencia y hojas CSV para cada
dominio. En la revisión de español Django, donde no hay un catálogo traducido
separado, presenta los `msgid` fuente como texto que debe revisar la persona.
Las hojas vacías de decisión no son evidencia de aprobación. El revisor debe
marcar cada fila `approved` o `needs_changes`, anotar las correcciones y
completar su nombre, competencia y fecha en `REVIEW-MANIFEST.json`. Después de
la aprobación de todas las filas, aplique la revisión con:

```bash
rtk .venv/bin/python scripts/apply_translation_review.py \
  --locale fr \
  --bundle ruta/al/paquete-revisado.zip \
  --report locale/reviews/reports/fr-linguistic-report.json
```

El aplicador comprueba los hashes contra los catálogos actuales, el inventario
completo, la decisión de cada fila, placeholders y plurales; actualiza los `.po`
solo después de validar todo el locale, registra un informe con los hashes
resultantes y quita `fuzzy` únicamente tras aprobación de todas las filas. Si
cambió la fuente española, se debe modificar el código y volver a extraer los
mensajes en lugar de editar el `msgid` dentro del paquete. El aplicador no activa
idiomas ni sustituye la aprobación institucional, pruebas funcionales o la
aprobación final que exige el gate. Copie las secciones `linguistic_review`,
`catalogs` y, para español, `source_copy_review` del informe resultante a
`<locale>.json`; en `linguistic_review.report` registre la ruta del informe y el
SHA-256 que imprime el comando. El hash del paquete devuelto permanece en el
informe para enlazar la revisión por fila con los catálogos aplicados.

La puerta solo informa el estado; no cambia `config/languages.py`, no compila
catálogos y no activa idiomas.

## Vista previa técnica de borradores

Los nueve locales adicionales pueden mostrarse solo en una instancia de
evaluación. Genere primero un bundle aislado con hashes:

```bash
rtk .venv/bin/python scripts/compile_translation_preview.py \
  --output-dir /ruta/aislada/locale-preview
RNC_TRANSLATION_PREVIEW=1 \
RNC_TRANSLATION_PREVIEW_LOCALE_PATH=/ruta/aislada/locale-preview \
  rtk .venv/bin/python manage.py runserver
```

El selector y aviso indican que las traducciones son borradores automáticos y
no deben usarse para interpretar estadísticas. El arranque compara el manifiesto
con los hashes de los PO/MO y falla cerrado ante archivos ausentes o modificados.
Este modo no agrega idiomas a `ACTIVE_LANGUAGES` ni cambia el estado del gate.
Mantenga `RNC_TRANSLATION_PREVIEW` apagado en la publicación normal.
El workflow de CI también compila este directorio y lo sube como artefacto de
revisión (`rnc-translation-preview-<commit>`) con retención de siete días, pero
solo después de que las comprobaciones del job pasen. Es un bundle para desplegar
en una instancia aislada de evaluación; no es un lanzamiento lingüístico aprobado.

### Entrega separada por idioma

Para asignar o revisar los idiomas de forma independiente, la versión más reciente
está en `pending-by-locale-2026-11-11-r9/`: un ZIP por locale, cada uno con 881 filas
(723 Django y 158 JavaScript), incluido el idioma fuente español. El paquete combinado es
`pending-human-review-2026-11-11-r9.zip`. Esta revisión actualiza la referencia inglesa
para conservar la sigla institucional `RNC` y corrige borradores de etiquetas comunes de
navegación, dimensión territorial, datos de gráficos y acceso al personal; las correcciones siguen fuzzy, no compiladas y sin
aprobación humana. Los paquetes r8 y anteriores permanecen como historial. Se puede
regenerar un paquete individual con `--locale <locale>` y su propio `--output`:

```bash
rtk .venv/bin/python scripts/export_translation_review.py \
  --locale fr \
  --output locale/reviews/pending-by-locale-YYYY-MM-DD/fr.zip
```

Cada paquete conserva el hash de los catálogos revisables; si el `.po` cambia,
el aplicador rechaza la revisión anterior y se debe exportar un paquete nuevo.
Estos archivos son material de trabajo, no evidencia de aprobación.
