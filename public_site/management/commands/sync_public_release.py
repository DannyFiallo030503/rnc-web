"""Rebuild the real aggregate from the active private delivery."""

from django.core.management.base import BaseCommand, CommandError

from public_site.aggregate_release import activate_release, prepare_release
from public_site.services import current_delivery
from django.conf import settings
from pathlib import Path
import csv


class Command(BaseCommand):
    help = "Sincronizar el agregado público con el corte real activo."

    def handle(self, *args, **options):
        delivery = current_delivery()
        if not delivery:
            raise CommandError("No hay corte real activo; no se modificó la publicación.")
        if delivery.status != "published":
            raise CommandError("El corte activo no está marcado como publicado.")
        try:
            activate_release(prepare_release(delivery))
            with (Path(settings.PRIVATE_STORAGE_ROOT) / delivery.storage_key).open(encoding="utf-8-sig", newline="") as stream:
                delivery.person_count = len({row["NOCASO"].strip() for row in csv.DictReader(stream)})
            delivery.report = {**delivery.report, "person_identity_verified": True, "person_key": "NOCASO"}
            delivery.save(update_fields=["person_count", "report"])
        except (OSError, ValueError) as exc:
            raise CommandError(f"No se pudo preparar el agregado público: {exc}") from exc
        self.stdout.write("Agregado real sincronizado.")
