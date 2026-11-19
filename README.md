# RNC Web

Portal de consulta de estadísticas del RNC. La instancia de trabajo usa el archivo
real `Nuevo/BD_2022.csv`, el diccionario `Nuevo/variables para Danny_OK.docx` y el
Excel poblacional suministrado `Nuevo/POBLACION _2022.xlsx`.

## Ejecutar localmente

Para consultar una publicación ya preparada, coloque sus archivos una sola vez en
`public_releases/`, que Git ignora. El perfil público usa esa carpeta por defecto
y no requiere migraciones. Consulte [la guía local](LEVANTAR-LOCAL.md).

### Preparar una publicación con la entrada autorizada

Use un worktree propio y su entorno virtual. La configuración predeterminada
mantiene la base, los archivos privados y las publicaciones dentro del worktree.
No use rutas escribibles de otra tarea. Instale `requirements.txt` y aplique las
migraciones con `python manage.py migrate --settings config.settings_admin`.

Para incorporar el corte de 2022 se necesitan los archivos autorizados y los
tres catálogos de clasificación entregados para esa integración. Coloque
`rnc_reference_terms.json`, `rnc_child_groups.json` y `rnc_site_groups.json` en
`private/catalogs/`, o configure `RNC_CLASSIFICATION_CATALOG_DIR` con su ruta
privada. Estos archivos se requieren para preparar una nueva publicación.

La incorporación local de 2022 se ejecuta una sola vez:

```bash
python manage.py activate_rnc_local "../Nuevo/BD_2022.csv" --settings config.settings_admin
```

El comando valida el diccionario y los campos de entrada, guarda el CSV preparado
en almacenamiento privado y activa un agregado sin identificadores. Registra la
operación mediante un actor técnico inactivo, sin contraseña ni permisos de acceso.
La administración habitual conserva sus cuentas y permisos existentes.

```bash
python manage.py runserver 127.0.0.1:8010 --settings config.settings_public
python manage.py runserver 127.0.0.1:8011 --settings config.settings_admin
```

Ambos perfiles usan el mismo `RNC_PUBLIC_RELEASE_ROOT`: el administrador escribe
publicaciones y el público solo las lee. El público no accede a la base privada.
`RNC_POPULATION_XLSX` y `RNC_DICTIONARY_DOCX` permiten configurar las fuentes.
`RNC_PRIVATE_STORAGE` y `RNC_DATABASE_PATH` permiten aislar los recursos privados.

## Reglas implementadas

- Año desde FECHAD, grupos de edad desde EDAD y residencia desde PROV.
- Comportamiento: adultos COMP=3; menores de 20, todos excepto COMP=2.
- CIE-10 para adultos y CICN para menores de 20, en espacios separados.
- Localizaciones y grupos principales transcritos del DOCX; cada nivel se consulta
  por separado. El total C00-97 es una selección explícita y no incorpora códigos D.
- Histología MORF; códigos de etapa recibidos; VH y SCD según el diccionario.
- Frecuencia absoluta, relativa, tasa cruda/específica y ajuste directo Segi–Doll.
  Para poblaciones adulta/infantil se explicita el ajuste truncado y se normalizan
  los pesos de las edades correspondientes. El cálculo se contrasta con los
  archivos suministrados; no establece por sí solo una decisión metodológica del RNC.
- Personas distintas por NOCASO, según aclaración del responsable. Los identificadores
  solo se utilizan en privado; el cubo contiene cardinalidades, nunca claves.
- Nombres y jerarquía infantil del Excel CLASIFICACION DE LOS NIÑOS.
- Tasas infantiles por 1 000 000; generales/adultas por 100 000, según Anuario.
- Totales C00-96 (Anuario) y C00-97 (DOCX) identificados por separado.
- La excepción de etapa escrita como «****» sigue incompleta en las fuentes.

## Integridad y comprobación

Las publicaciones de esquema 3 se guardan comprimidas, con manifiesto SHA-256,
huellas del CSV original, CSV preparado, DOCX y Excel. El lector no acepta los
paquetes de demostración anteriores. La consulta offline rechaza paquetes antiguos.

```bash
python scripts/verify_real_data.py
```

El verificador requiere Node.js para comprobar el worker.
La verificación usa los originales en modo de lectura, compara las fórmulas y
agrupaciones, y contrasta el worker offline con el motor online. Solo imprime
resultados de comprobaciones, sin registros ni cifras clínicas. Las comprobaciones
no equivalen a una validación institucional. La suite de aplicación fue adaptada
al flujo real: pasaron 56 pruebas, incluidas las de cuentas, permisos, traducciones
y publicación/revocación. Se ejecuta con `python manage.py test analytics public_site`.
Para compilar los catálogos activos utilice `python scripts/compile_translations.py`
con la dependencia de desarrollo polib declarada en requirements-test.txt.

[Informe de integración y pendientes](REAL_DATA_INTEGRATION.md).
[Vistas y administración de disponibilidad](VISUALIZATIONS.md).
El repositorio documental de referencia es `../rnc-research`; siga `../CONCURRENCIA.md`.
Los CSV, bases, paquetes de datos y archivos privados quedan excluidos de Git.

[Consulta unificada y PWA](OFFLINE_CONSULTATION.md): el modo sin conexión utiliza
la misma Consulta estadística y prepara automáticamente la copia pública.

[Idioma, acceso administrativo y sesiones](LANGUAGE_AND_SESSION.md). El enlace
público al acceso del personal se configura con RNC_ADMIN_SITE_URL.
