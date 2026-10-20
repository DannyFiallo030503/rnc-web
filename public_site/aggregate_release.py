"""Build and read the public aggregate package for the synthetic prototype."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings

FIELDS = ("period", "territory", "sex", "age_group", "site")
STRATUM = ("period", "territory", "sex", "age_group")


def _cube_key(fields):
    return ",".join(fields)


def build_release(delivery, records):
    """Aggregate all filter/grouping combinations without retaining row IDs."""
    if not records or any(
        row.get("synthetic") != "TRUE"
        or not str(row.get("person_id", "")).startswith("SYN-P-")
        or not str(row.get("tumor_id", "")).startswith("SYN-T-")
        for row in records
    ):
        raise ValueError("Solo se puede liberar el conjunto sintético de demostración.")

    cube = {}
    for mask in range(1 << len(FIELDS)):
        fields = tuple(field for i, field in enumerate(FIELDS) if mask & (1 << i))
        groups = {}
        for row in records:
            key = tuple(str(row[field]) for field in fields)
            state = groups.setdefault(key, [0, set(), {}])
            state[0] += 1
            state[1].add(row["person_id"])
            stratum = tuple(row[field] for field in STRATUM)
            state[2][stratum] = int(row["population"])
        cube[_cube_key(fields)] = [
            {
                **dict(zip(fields, key)),
                "tumors": tumors,
                "persons": len(persons),
                "population": sum(strata.values()),
            }
            for key, (tumors, persons, strata) in groups.items()
        ]

    options = {
        "period": sorted({str(row["period"]) for row in records}),
        "territory": sorted({row["territory"] for row in records}),
        "sex": sorted({row["sex"] for row in records}),
        "age_group": sorted({row["age_group"] for row in records}),
        "site": sorted({row["site"] for row in records}),
    }
    return {
        "schema_version": 1,
        "synthetic": True,
        "release_id": str(delivery.pk),
        "title": delivery.title,
        "published_at": delivery.published_at.isoformat()
        if delivery.published_at
        else None,
        "report": delivery.report,
        "options": options,
        "fields": list(FIELDS),
        "cube": cube,
    }


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
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


def prepare_release(delivery, records):
    """Write a versioned artifact, without making it the active public release."""
    payload = build_release(delivery, records)
    root = Path(settings.PUBLIC_RELEASE_ROOT)
    release_id = str(delivery.pk)
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", release_id):
        raise ValueError("Identificador de publicación inválido.")
    artifact = root / f"{release_id}.json"
    digest = _atomic_json(artifact, payload)
    return {"release_id": release_id, "sha256": digest}


def activate_release(manifest):
    """Atomically point public readers at an already written aggregate artifact."""
    _atomic_json(Path(settings.PUBLIC_RELEASE_ROOT) / "current.json", manifest)


def publish_release(delivery, records):
    """Write a versioned aggregate artifact and switch the public pointer."""
    activate_release(prepare_release(delivery, records))


def revoke_public_release():
    root = Path(settings.PUBLIC_RELEASE_ROOT)
    _atomic_json(root / "current.json", {"release_id": None, "sha256": None})


@lru_cache(maxsize=2)
def _read_artifact(path, expected_digest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        return None
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != 1 or data.get("synthetic") is not True:
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
        data = _read_artifact(str(root / f"{release_id}.json"), digest)
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
