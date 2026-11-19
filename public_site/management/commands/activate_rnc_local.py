"""Activate the authorized 2022 source in this isolated development instance."""

import hashlib
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from public_site.models import Delivery
from public_site.services import ingest, transition
from analytics.rnc_classification import catalog


class Command(BaseCommand):
    help = "Incorpora y activa BD_2022 en desarrollo, con trazabilidad y auditoría."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("La activación local solo se admite en desarrollo.")
        source = options["source"]
        if not source.is_file() or not Path(settings.RNC_POPULATION_XLSX).is_file():
            raise CommandError("Falta el CSV original o el Excel poblacional de 2022.")
        dictionary = Path(settings.RNC_DICTIONARY_DOCX)
        if not dictionary.is_file() or hashlib.sha256(dictionary.read_bytes()).hexdigest() != catalog()[0]["source_sha256"]:
            raise CommandError("El diccionario no coincide con el catálogo transcrito y revisado.")
        actor, created = get_user_model().objects.get_or_create(
            username="rnc_local_import",
            defaults={"is_active": False, "first_name": "Integración local"},
        )
        if created:
            actor.set_unusable_password()
            actor.save(update_fields=["password"])
        if actor.is_active or actor.is_staff or actor.is_superuser:
            raise CommandError("El actor técnico local debe carecer de acceso y privilegios.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        delivery = Delivery.objects.filter(checksum=digest).first()
        if delivery is None:
            with source.open("rb") as stream:
                delivery = ingest(File(stream, name=source.name), "BD_2022 · Integración local", actor)
        if delivery.status == "rejected":
            raise CommandError("La validación rechazó el archivo. Revise el informe privado de la entrega.")
        if delivery.status == "published":
            self.stdout.write("La entrega ya está publicada en esta instancia local.")
            return
        transition(delivery.pk, "publish", actor, "Integración local de BD_2022 solicitada por el responsable del proyecto.")
        self.stdout.write("Agregado real de 2022 activado. Los registros e identificadores permanecen privados.")
