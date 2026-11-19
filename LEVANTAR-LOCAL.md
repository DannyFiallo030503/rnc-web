# Levantar RNC Web en local

Requiere Python 3.12 y una publicación agregada compatible con el esquema 3.
Mantén los archivos de la publicación, incluido `current.json`, en
`public_releases/` dentro de tu worktree. Es una carpeta local ignorada por Git.

## Primera vez

Desde el directorio del repositorio:

```bash
rtk proxy python3.12 -m venv .venv
rtk proxy .venv/bin/python -m pip install -r requirements.txt
```

## Iniciar la consulta

```bash
rtk proxy env DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 127.0.0.1:8010 --settings config.settings_public
```

Abre <http://127.0.0.1:8010/consulta/>. La publicación guardada en
`public_releases/` se reutiliza en cada inicio. El perfil público lee esos
agregados y usa una base dummy. Detén el servidor con `Ctrl+C`.

Para preparar una publicación nueva desde las fuentes autorizadas, sigue
[la sección de incorporación del README](README.md#preparar-una-publicación-con-la-entrada-autorizada).
