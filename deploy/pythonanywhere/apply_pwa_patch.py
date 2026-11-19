"""Apply the generated, hash-checked public PWA patch to the existing installation."""
from pathlib import Path
from datetime import datetime
import ast
import base64
import hashlib
import json
import os
import runpy
import shutil
import zlib

PAYLOAD = "__PAYLOAD__"


def main():
    root = Path.home() / "rnc-web"
    wsgi = Path("/var/www/dannyfiallo_pythonanywhere_com_wsgi.py")
    patch = json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))
    for name, item in patch.items():
        path = root / name
        if hashlib.sha256(path.read_bytes()).hexdigest() not in (item["before"], item["after"]):
            raise SystemExit("El archivo tiene otros cambios; no se ha aplicado el parche: " + name)
    backup = Path.home() / ("rnc-pwa-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup.mkdir(mode=0o700)
    shutil.copy2(wsgi, backup / "wsgi.py")
    tree = ast.parse(wsgi.read_text())
    enable = ast.parse('os.environ["RNC_PUBLIC_PWA_ENABLED"] = "1"').body[0]
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "application" for t in node.targets):
            tree.body.insert(i, enable)
            break
    else:
        raise SystemExit("No se encontró la inicialización WSGI. No se cambió el sitio.")
    ast.fix_missing_locations(tree)
    updated_wsgi = ast.unparse(tree) + "\n"
    compile(updated_wsgi, str(wsgi), "exec")
    for name, item in patch.items():
        target = root / name
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
        temporary = target.with_suffix(target.suffix + ".pwa-new")
        temporary.write_bytes(base64.b64decode(item["content"]))
        os.replace(temporary, target)
    temporary = wsgi.with_suffix(".py.pwa-new")
    temporary.write_text(updated_wsgi)
    os.replace(temporary, wsgi)
    runpy.run_path(str(wsgi))
    from django.core.management import call_command
    call_command("check")
    call_command("collectstatic", interactive=False, verbosity=1)
    print("Parche PWA aplicado. Respaldo:", backup)
    print("Pulse Reload en la pestaña Web de PythonAnywhere.")


if __name__ == "__main__":
    main()
