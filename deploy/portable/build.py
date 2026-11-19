"""Build an offline Windows x64 distribution from verified vendor archives.

Usage: python build.py --runtime python-embed.zip --wheels wheels/ \
    --release /private/path/public_releases --output /path/output
Downloads are done before building. No installation or network is needed by recipients.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile


def unpack(source, target):
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe package path")
        archive.extractall(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    product = args.output / "RNC-Consulta-Windows"
    product.mkdir(parents=True, exist_ok=False)
    runtime = product / "runtime"
    runtime.mkdir()
    unpack(args.runtime, runtime)
    dependencies = runtime / "Lib/site-packages"
    dependencies.mkdir(parents=True)
    inputs = [args.runtime]
    for wheel in sorted(args.wheels.glob("*.whl")):
        unpack(wheel, dependencies)
        inputs.append(wheel)
    pth = next(runtime.glob("python*._pth"))
    stdlib = next(runtime.glob("python*.zip")).name
    pth.write_text(stdlib + "\n.\nLib/site-packages\n..\n../app\nimport site\n")
    # Relocate wheel .data/purelib or platlib payloads if present.
    for data in dependencies.glob("*.data"):
        for section in ("purelib", "platlib"):
            if (data / section).exists():
                shutil.copytree(data / section, dependencies, dirs_exist_ok=True)
    app = product / "app"
    app.mkdir()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    for name in tracked:
        if not name or not name.startswith(("analytics/", "config/", "public_site/", "templates/", "static/", "locale/")):
            continue
        source = repo / name
        if not source.is_file() or source.suffix in {".pyc", ".csv", ".sqlite3"} or "fixtures" in source.parts:
            continue
        destination = app / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    # The portable settings is new and may not yet be staged in Git.
    shutil.copy2(repo / "config/settings_portable.py", app / "config/settings_portable.py")
    for mo in (repo / "locale").glob("*/LC_MESSAGES/*.mo"):
        target = app / mo.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mo, target)
    publication = json.loads((args.release / "current.json").read_text())
    release_id = publication["release_id"]
    if Path(release_id).name != release_id:
        raise ValueError("Invalid release ID")
    release = args.release / (release_id + ".json.gz")
    if hashlib.sha256(release.read_bytes()).hexdigest() != publication["sha256"]:
        raise ValueError("Release hash mismatch")
    releases = product / "public_releases"
    releases.mkdir()
    for source in (args.release / "current.json", release):
        shutil.copy2(source, releases / source.name)
    for name in ("launcher.py", "Abrir RNC.cmd", "LEEME.txt"):
        shutil.copy2(repo / "deploy/portable" / name, product / name)
    build = {
        "platform": "Windows x64", "python": "3.13.17",
        "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "publication_sha256": publication["sha256"],
        "code_base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip(),
        "sources": ["https://www.python.org/ftp/python/3.13.17/", "https://pypi.org/"],
    }
    (product / "componentes.json").write_text(json.dumps(build, ensure_ascii=False, indent=2))
    inventory = {str(p.relative_to(product)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(product.rglob("*")) if p.is_file()}
    (product / "integridad.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    target = shutil.make_archive(str(args.output / "RNC-Consulta-Windows-x64"), "zip", args.output, product.name)
    print(target)


if __name__ == "__main__":
    main()
