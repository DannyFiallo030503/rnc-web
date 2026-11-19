"""Private handlers for real RNC deliveries."""

import csv
import hashlib
import io
import os
import uuid
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Delivery, Publication, AuditEvent


def private_root():
    root = Path(settings.PRIVATE_STORAGE_ROOT)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def audit(user, action, target, reason=""):
    AuditEvent.objects.create(
        actor=user, action=action, target=str(target), reason=reason
    )


def _is_rnc_input(upload):
    """Recognize the received RNC schema without retaining its contents."""
    from analytics.rnc_input import SOURCE_FIELDS

    try:
        upload.seek(0)
        header = next(csv.reader(io.StringIO(upload.read().decode("utf-8-sig"))), [])
    except (UnicodeError, csv.Error, AttributeError):
        return False
    finally:
        upload.seek(0)
    normalized = {name.strip() for name in header if name.strip()}
    return len(normalized.intersection(SOURCE_FIELDS)) >= 4


def _ingest_rnc(upload, title, user):
    """Validate the real CSV and keep only its normalized copy in private storage."""
    from analytics.rnc_input import InputValidationError, write_clean_csv

    if upload.size > 12 * 1024 * 1024 or not upload.name.lower().endswith(".csv"):
        raise ValueError("Utilice un CSV de hasta 12 MB.")
    upload.seek(0)
    raw = upload.read(12 * 1024 * 1024 + 1)
    checksum = hashlib.sha256(raw).hexdigest()
    if Delivery.objects.filter(checksum=checksum).exists():
        raise ValueError("Esta entrega ya está registrada; no se incorporó otra copia.")

    root = private_root()
    key = f"prepared/{uuid.uuid4().hex}.csv"
    destination = root / key
    temporary_source = root / f".incoming-{uuid.uuid4().hex}.csv"
    temporary_source.write_bytes(raw)
    os.chmod(temporary_source, 0o600)
    try:
        try:
            report = write_clean_csv(temporary_source, destination)
        except InputValidationError as exc:
            with transaction.atomic():
                delivery = Delivery.objects.create(
                    title=title,
                    checksum=checksum,
                    storage_key="",
                    created_by=user,
                    status="rejected",
                    report={
                        "synthetic": False,
                        "source_retained": False,
                        "received_rows": exc.rows_seen,
                        "accepted_rows": 0,
                        "rejected_rows": exc.rows_seen,
                        "errors": list(exc.issues),
                    },
                )
                audit(user, "Carga real rechazada", delivery.pk)
            return delivery

        with transaction.atomic():
            delivery = Delivery.objects.create(
                title=title,
                checksum=checksum,
                storage_key=key,
                created_by=user,
                row_count=report["rows_written"],
                person_count=report["person_count"],
                report={
                    "synthetic": False,
                    "person_identity_verified": True,
                    "source_retained": False,
                    "cleaned_private_file": True,
                    "received_rows": report["rows_seen"],
                    "accepted_rows": report["rows_written"],
                    "rejected_rows": 0,
                    "empty_rows_removed": report["empty_rows_removed"],
                    "source_columns": report["source_columns"],
                    "kept_columns": report["kept_columns"],
                    "unused_columns_removed": report["unused_columns_removed"],
                    "optional_blanks": report["optional_blanks"],
                    "ready_for_publication": False,
                },
            )
            audit(user, "Carga real validada en estructura", delivery.pk)
        return delivery
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        temporary_source.unlink(missing_ok=True)


def current_delivery():
    publication = Publication.objects.select_related("delivery").filter(pk=1).first()
    return publication.delivery if publication and publication.delivery_id else None


def transition(pk, action, user, reason):
    with transaction.atomic():
        pointer, _ = Publication.objects.get_or_create(pk=1)
        pointer = Publication.objects.select_for_update().get(pk=1)
        delivery = Delivery.objects.select_for_update().get(pk=pk)
        if action == "publish" and delivery.status == "validated":
            if delivery.report.get("synthetic") is not False:
                raise ValueError("Solo se puede publicar una entrega real validada.")
            from .aggregate_release import activate_release, prepare_release

            manifest = prepare_release(delivery)
            delivery.published_at = timezone.now()
            if pointer.delivery_id:
                previous = Delivery.objects.select_for_update().get(pk=pointer.delivery_id)
                previous.status = "revoked"
                previous.save(update_fields=["status"])
                audit(user, "Corte sustituido", previous.pk, reason)
            delivery.status = "published"
            pointer.delivery = delivery
            transaction.on_commit(lambda: activate_release(manifest))
        elif (
            action == "revoke"
            and delivery.status == "published"
            and pointer.delivery_id == delivery.pk
        ):
            from .aggregate_release import revoke_public_release

            delivery.status = "revoked"
            pointer.delivery = None
            transaction.on_commit(revoke_public_release)
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
    """Accept only the documented real RNC source schema."""
    from django.db import IntegrityError

    if not _is_rnc_input(upload):
        raise ValueError("El portal solo acepta el formato real del CSV del RNC.")
    try:
        return _ingest_rnc(upload, title, user)
    except IntegrityError as exc:
        raise ValueError("Esta entrega ya está registrada.") from exc
