"""Private synthetic delivery contract. Never maps the confidential RNC CSV."""

import re
import csv
import hashlib
import io
import json
import os
import uuid
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Delivery, Publication, AuditEvent
from analytics.catalogs import CATALOGS, id_for, resolve

HEADER = [
    "synthetic",
    "person_id",
    "tumor_id",
    "period",
    "territory_id",
    "sex_id",
    "age_group_id",
    "site_id",
    "population",
    "standard_weight",
]
WEIGHTS = dict(
    zip(
        [f"{n}-{n+4}" for n in range(0, 85, 5)] + ["85+"],
        [
            12000,
            10000,
            9000,
            9000,
            8000,
            8000,
            6000,
            6000,
            6000,
            6000,
            5000,
            4000,
            4000,
            3000,
            2000,
            1000,
            500,
            500,
        ],
    )
)


def private_root():
    root = Path(settings.PRIVATE_STORAGE_ROOT)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def audit(user, action, target, reason=""):
    AuditEvent.objects.create(
        actor=user, action=action, target=str(target), reason=reason
    )


def _ingest(upload, title, user):
    if upload.size > 12 * 1024 * 1024 or not upload.name.lower().endswith(".csv"):
        raise ValueError("Utilice un CSV de hasta 12 MB.")
    raw = upload.read(12 * 1024 * 1024 + 1)
    checksum = hashlib.sha256(raw).hexdigest()
    if Delivery.objects.filter(checksum=checksum).exists():
        raise ValueError("Esta entrega ya está registrada; no se incorporó otra copia.")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if reader.fieldnames != HEADER:
            raise ValueError(
                "Estructura incompatible. Descargue el CSV sintético de ejemplo."
            )
        records, people, tumors, strata = [], {}, set(), {}
        identities = {}
        from analytics.demo import load_rows as reference_rows

        territories = {r["territory_id"] for r in reference_rows()}
        sites = {r["site_id"] for r in reference_rows()}
        for number, r in enumerate(reader, 2):
            if number > 60001:
                raise ValueError("El límite local es de 60 000 filas.")
            if None in r or any(v is None or len(v) > 150 for v in r.values()):
                raise ValueError(f"Fila {number}: estructura o longitud incorrecta.")
            if (
                r["synthetic"] != "TRUE"
                or not r["person_id"].startswith("SYN-P-")
                or not r["tumor_id"].startswith("SYN-T-")
            ):
                raise ValueError(
                    f"Fila {number}: solo se admite el contrato sintético de demostración."
                )
            if not re.fullmatch(
                r"SYN-P-[A-Za-z0-9-]+", r["person_id"]
            ) or not re.fullmatch(r"SYN-T-[A-Za-z0-9-]+", r["tumor_id"]):
                raise ValueError(
                    f"Fila {number}: formato de identificador sintético no admitido."
                )
            try:
                territory = resolve("territory_id", r["territory_id"])["name"]
                sex = resolve("sex_id", r["sex_id"])["name"]
                age_group = resolve("age_group_id", r["age_group_id"])["name"]
                site = resolve("site_id", r["site_id"])["name"]
            except KeyError as exc:
                raise ValueError(f"Fila {number}: identificador de catálogo desconocido.") from exc
            if r["territory_id"] not in territories or r["site_id"] not in sites:
                raise ValueError(f"Fila {number}: categoría no admitida.")
            try:
                year, population, weight = (
                    int(r["period"]),
                    int(r["population"]),
                    int(r["standard_weight"]),
                )
            except ValueError as exc:
                raise ValueError(
                    f"Fila {number}: se requieren números enteros."
                ) from exc
            if (
                not 2000 <= year <= 2100
                or population <= 0
                or weight != WEIGHTS[age_group]
            ):
                raise ValueError(
                    f"Fila {number}: período, población o peso incompatible."
                )
            stratum = (year, territory, sex, age_group)
            if stratum in strata and strata[stratum] != population:
                raise ValueError(f"Fila {number}: denominador inconsistente.")
            strata[stratum] = population
            identity_key = (r["person_id"], year)
            if (
                identity_key in people
                and people[identity_key] != stratum
            ):
                raise ValueError(
                    f"Fila {number}: persona incompatible con el estrato declarado."
                )
            people[identity_key] = stratum
            identity = r["sex_id"]
            if r["person_id"] in identities and identities[r["person_id"]] != identity:
                raise ValueError(f"Fila {number}: identidad sintética inconsistente.")
            identities[r["person_id"]] = identity
            if r["tumor_id"]:
                if r["tumor_id"] in tumors:
                    raise ValueError(f"Fila {number}: identificador de tumor repetido.")
                tumors.add(r["tumor_id"])
            r.update(
                period=year,
                population=population,
                standard_weight=weight,
                territory=territory,
                sex=sex,
                age_group=age_group,
                site=site,
            )
            records.append(r)
        if not records:
            raise ValueError("El archivo no contiene registros.")
        # All age/sex strata are required for meaningful unrestricted denominators.
        for year, territory in {(s[0], s[1]) for s in strata}:
            if any(
                (year, territory, sex, age) not in strata
                for sex in ["Mujeres", "Hombres"]
                for age in WEIGHTS
            ):
                raise ValueError(
                    "Cada territorio y año debe cubrir ambos sexos y los 18 grupos de edad."
                )
    except (UnicodeError, csv.Error, TypeError, KeyError, OverflowError) as exc:
        raise ValueError("CSV no válido; revise codificación y estructura.") from exc
    key = uuid.uuid4().hex + ".json"
    path = private_root() / key
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    os.chmod(path, 0o600)
    original = path.with_suffix(".csv")
    original.write_bytes(raw)
    os.chmod(original, 0o600)
    try:
        with transaction.atomic():
            delivery = Delivery.objects.create(
                title=title,
                checksum=checksum,
                storage_key=key,
                created_by=user,
                row_count=len(tumors),
                person_count=len(identities),
                report={
                    "received_rows": len(records),
                    "accepted_rows": len(records),
                    "rejected_rows": 0,
                    "periods": sorted({r["period"] for r in records}),
                    "territories": len({r["territory"] for r in records}),
                    "synthetic": True,
                    "method": "Segi–Doll; denominadores sintéticos; personas distintas en la selección",
                },
            )
            audit(user, "Carga validada", delivery.pk)
    except Exception:
        path.unlink(missing_ok=True)
        original.unlink(missing_ok=True)
        raise
    return delivery


@lru_cache(maxsize=4)
def delivery_records(key):
    records = json.loads((private_root() / key).read_text(encoding="utf-8"))
    # Normalize earlier local demo releases on read; do not surface old invented names.
    for record in records:
        for field in ("territory", "sex", "age_group", "site"):
            code_field = f"{field}_id"
            if (
                code_field not in record
                or record[code_field] not in CATALOGS[code_field]
            ):
                record[code_field] = id_for(code_field, record[field])
        record.pop("name", None)
    return records


def current_delivery():
    publication = Publication.objects.select_related("delivery").filter(pk=1).first()
    return publication.delivery if publication and publication.delivery_id else None


def published_records():
    """Private-only compatibility helper for the local ingestion prototype."""
    delivery = current_delivery()
    return delivery_records(delivery.storage_key) if delivery else []


def transition(pk, action, user, reason):
    with transaction.atomic():
        pointer, _ = Publication.objects.get_or_create(pk=1)
        pointer = Publication.objects.select_for_update().get(pk=1)
        delivery = Delivery.objects.select_for_update().get(pk=pk)
        if action == "publish" and delivery.status == "validated":
            from .aggregate_release import activate_release, prepare_release

            delivery.published_at = timezone.now()
            release_records = delivery_records(delivery.storage_key)
            # The public package is built before changing the active pointer. It
            # contains grouped counts only, never person/tumor identifiers.
            manifest = prepare_release(delivery, release_records)
            if pointer.delivery_id:
                Delivery.objects.filter(pk=pointer.delivery_id).update(status="revoked")
                audit(user, "Corte sustituido", pointer.delivery_id, reason)
            delivery.status = "published"
            pointer.delivery = delivery
            transaction.on_commit(lambda: activate_release(manifest))
        elif (
            action == "revoke"
            and delivery.status == "published"
            and pointer.delivery_id == delivery.pk
        ):
            from .aggregate_release import revoke_public_release

            transaction.on_commit(revoke_public_release)
            delivery.status = "revoked"
            pointer.delivery = None
        else:
            raise ValueError("La acción ya no es válida para el estado actual.")
        delivery.save()
        pointer.save()
        audit(
            user,
            "Publicación" if action == "publish" else "Revocación",
            delivery.pk,
            reason,
        )


def ingest(upload, title, user):
    """Keep failed technical attempts without exposing source values in reports."""
    from django.db import IntegrityError

    try:
        return _ingest(upload, title, user)
    except IntegrityError as exc:
        raise ValueError("Esta entrega ya está registrada.") from exc
    except ValueError as exc:
        if upload.size <= 12 * 1024 * 1024 and upload.name.lower().endswith(".csv"):
            upload.seek(0)
            raw = upload.read(12 * 1024 * 1024 + 1)
            checksum = hashlib.sha256(raw).hexdigest()
            if not Delivery.objects.filter(checksum=checksum).exists():
                try:
                    received = max(
                        0,
                        sum(1 for _ in csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
                        - 1,
                    )
                except (UnicodeError, csv.Error):
                    received = None
                key = uuid.uuid4().hex + ".csv"
                path = private_root() / key
                path.write_bytes(raw)
                os.chmod(path, 0o600)
                try:
                    with transaction.atomic():
                        delivery = Delivery.objects.create(
                            title=title,
                            checksum=checksum,
                            storage_key=key,
                            created_by=user,
                            status="rejected",
                            report={
                                "error": str(exc),
                                "synthetic": True,
                                "received_rows": received,
                                "accepted_rows": 0,
                                "rejected_rows": received,
                            },
                        )
                        audit(user, "Carga rechazada técnicamente", delivery.pk)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
        raise
