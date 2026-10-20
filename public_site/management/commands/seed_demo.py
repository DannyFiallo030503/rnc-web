"""Generate private synthetic people, then use the same ingestion/publication services."""

import csv
import io
import random
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from analytics.demo import load_rows
from public_site.models import Delivery
from public_site.services import HEADER, ingest, transition, private_root
from analytics.catalogs import id_for


class Command(BaseCommand):
    help = "Crear y publicar un corte sintético local reproducible (solo DEBUG)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Comando limitado al entorno local DEBUG.")
        if Delivery.objects.exists():
            self.stdout.write(
                "Se conservan las entregas existentes; no se modificó la publicación."
            )
            return
        user = (
            get_user_model().objects.filter(is_superuser=True, is_active=True).first()
        )
        if not user:
            raise CommandError("Cree primero un superusuario.")
        randomizer = random.Random(20261016)
        reference = load_rows()
        strata = {}
        known = {r["site"] for r in reference}
        for row in reference:
            key = (row["period"], row["territory"], row["sex"], row["age_group"])
            strata[key] = row
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(HEADER)
        person = 0
        tumor = 0
        for (year, territory, sex, age), row in strata.items():
            years = int(age.split("-")[0].replace("+", ""))
            count = 1 + int(
                row["population"]
                * (0.00008 if years < 35 else 0.0005 if years < 60 else 0.0012)
            )
            for _ in range(min(count, 18)):
                person += 1
                for _ in range(2 if randomizer.random() < 0.09 else 1):
                    tumor += 1
                    sites = (
                        ["Leucemias", "Linfomas", "Tiroides"]
                        if years < 20
                        else (
                            [
                                "Mama",
                                "Cuello del útero",
                                "Colon y recto",
                                "Tiroides",
                                "Tráquea, bronquios y pulmón",
                            ]
                            if sex == "Mujeres"
                            else [
                                "Próstata",
                                "Colon y recto",
                                "Tráquea, bronquios y pulmón",
                                "Estómago",
                                "Vejiga urinaria",
                            ]
                        )
                    )
                    sites = [s for s in sites if s in known]
                    writer.writerow(
                        [
                            "TRUE",
                            f"SYN-P-{person:07}",
                            f"SYN-T-{tumor:07}",
                            year,
                            id_for("territory_id", territory),
                            id_for("sex_id", sex),
                            id_for("age_group_id", age),
                            id_for("site_id", randomizer.choice(sites)),
                            row["population"],
                            row["standard_weight"],
                        ]
                    )
        raw = output.getvalue().encode()
        (private_root() / "ejemplo_sintetico.csv").write_bytes(raw)
        delivery = ingest(
            SimpleUploadedFile("ejemplo.csv", raw),
            "Incidencia 2021–2024 · corte sintético",
            user,
        )
        transition(
            delivery.pk,
            "publish",
            user,
            "Publicación inicial de demostración; exclusivamente datos sintéticos.",
        )
        self.stdout.write(
            f"Corte sintético publicado: {delivery.row_count} tumores; {delivery.person_count} personas distintas."
        )
