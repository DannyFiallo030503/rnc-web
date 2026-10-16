# Flujo de trabajo

- `main` es la rama predeterminada y recibe cambios mediante pull request desde `develop` del mismo repositorio.
- `main` exige el control `repository-policy` y resolver las conversaciones; no permite borrado ni force push. Las reglas también se aplican a administradores, sin excepciones de bypass.
- `develop` es la rama de trabajo y permite push directo. Su única restricción es impedir su eliminación.
- No se exige una aprobación de otra persona mientras el desarrollo sea individual. Revisar el diff completo antes de fusionar una PR.
- No activar el borrado automático de la rama después de fusionar: `develop` es permanente.

## Archivos versionados

Versionar código, migraciones, configuración sin secretos, pruebas automatizadas y fixtures sintéticas explícitamente autorizadas. El README, las instrucciones de contribución y la documentación mínima junto al código forman parte del repositorio.

La documentación académica y de trabajo se mantiene en `rnc-research`. `docs/` y los reportes, capturas, bases locales, archivos cargados, backups y secretos quedan excluidos por `.gitignore`. Los archivos locales existentes no se eliminan.

`.gitignore` se aplica a todas las ramas y no elimina archivos ya versionados. El control de la PR revisa el árbol completo propuesto para `main`, incluso archivos añadidos con `git add -f`. No detecta todos los secretos ni garantiza ausencia de datos clínicos: revisar contenido, fixtures y cambios de la propia política antes de fusionar.

Los scripts y el código de pruebas son necesarios para mantener el producto; sus resultados generados no se versionan. Un despliegue debe empaquetar únicamente los componentes necesarios para ejecutar la aplicación.

## Trabajo local

```bash
git switch develop
# Editar y añadir explícitamente los archivos pertinentes.
git add ruta/al/archivo
git commit
git push origin develop
```

Abrir una PR con base `main` y origen `develop`. Revisar los archivos, esperar el control y fusionar. Actualizar después la copia local con `git fetch origin`. No incluir credenciales, bases locales ni datos de pacientes.
