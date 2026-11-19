"""Read only approved real aggregate releases for the public portal."""

import hashlib
import gzip
import json
import os
import re
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.utils import timezone

FIELDS = ("period", "territory", "municipality", "sex", "age_group", "site")
STRATUM = ("period", "territory", "sex", "age_group")
POPULATION_FIELDS = ("period", "territory", "municipality", "sex", "age_group")


def _atomic_json(path, payload, *, compressed=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if compressed:
        encoded = gzip.compress(encoded, mtime=0)
    handle, temporary = tempfile.mkstemp(prefix=".release-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return hashlib.sha256(encoded).hexdigest()


def prepare_release(delivery):
    """Create an identifier-free real aggregate for an authorized publisher."""
    from analytics.rnc_aggregation import build_real_aggregate

    if delivery.report.get("synthetic") is not False or not delivery.storage_key:
        raise ValueError("Solo se puede publicar una entrega real validada.")
    private_root = Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    source = (private_root / delivery.storage_key).resolve()
    if private_root not in source.parents or not source.is_file():
        raise ValueError("No se encontró el archivo real en almacenamiento privado.")
    payload = build_real_aggregate(
        source,
        settings.RNC_POPULATION_XLSX,
        release_id=str(delivery.pk),
        title=delivery.title,
    )
    payload["publication_approved"] = True
    payload["provenance"]["original_csv_sha256"] = delivery.checksum
    payload["provenance"]["source_name"] = "BD_2022.csv"
    payload["published_at"] = timezone.now().isoformat()
    root = Path(settings.PUBLIC_RELEASE_ROOT)
    release_id = str(delivery.pk)
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", release_id):
        raise ValueError("Identificador de publicación inválido.")
    digest = _atomic_json(root / f"{release_id}.json.gz", payload, compressed=True)
    return {"release_id": release_id, "sha256": digest, "encoding": "gzip"}


def activate_release(manifest):
    _atomic_json(Path(settings.PUBLIC_RELEASE_ROOT) / "current.json", manifest)


def revoke_public_release():
    activate_release({"release_id": None, "sha256": None})


@lru_cache(maxsize=2)
def _read_artifact(path, expected_digest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        return None
    data = json.loads(gzip.decompress(raw).decode("utf-8") if str(path).endswith(".gz") else raw.decode("utf-8"))
    if (
        data.get("schema_version") != 3
        or data.get("synthetic") is not False
        or data.get("publication_approved") is not True
    ):
        return None
    return data


def current_public_release():
    root = Path(settings.PUBLIC_RELEASE_ROOT)
    pointer_path = root / "current.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        release_id = pointer.get("release_id")
        digest = pointer.get("sha256")
        if not release_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", release_id):
            return None
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        encoding = pointer.get("encoding")
        if encoding not in (None, "gzip"):
            return None
        suffix = ".json.gz" if encoding == "gzip" else ".json"
        data = _read_artifact(str(root / f"{release_id}{suffix}"), digest)
        if not data or data.get("release_id") != release_id:
            return None
        public_data = dict(data)
        if public_data.get("published_at"):
            public_data["published_at"] = datetime.fromisoformat(
                public_data["published_at"]
            )
        return public_data
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
