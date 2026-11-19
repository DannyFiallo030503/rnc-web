"""Start a loopback-only RNC website and open the user's browser."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))


def main():
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings_portable",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
        "DJANGO_DEBUG": "0",
        "DJANGO_SECURE_SSL_REDIRECT": "0",
        "RNC_PUBLIC_RELEASE_ROOT": str(ROOT / "public_releases"),
        "RNC_ADMIN_SITE_URL": "",
        "MPLCONFIGDIR": str(Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "RNC-Consulta" / "matplotlib"),
    })
    manifest = json.loads((ROOT / "public_releases/current.json").read_text())
    release_id = manifest["release_id"]
    if Path(release_id).name != release_id:
        raise ValueError("Identificador de publicación inválido")
    publication = ROOT / "public_releases" / (release_id + ".json.gz")
    if hashlib.sha256(publication.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("La publicación está incompleta o dañada. Vuelva a extraer el ZIP.")
    from django.core.wsgi import get_wsgi_application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from waitress import create_server
    application = StaticFilesHandler(get_wsgi_application())
    # Stable port preserves PWA and IndexedDB across launches; fail on conflicts.
    server = create_server(application, host="127.0.0.1", port=8765, threads=4)
    address = "http://127.0.0.1:8765/"
    print("RNC - Consulta local", flush=True)
    print("Se abrirá el navegador en " + address, flush=True)
    print("Mantenga esta ventana abierta. Para terminar, cierre la ventana o pulse Ctrl+C.", flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(address)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("No se pudo iniciar RNC: " + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
