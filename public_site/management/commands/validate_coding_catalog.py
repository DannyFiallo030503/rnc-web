"""Validate an authorized versioned tumor-coding catalog without printing codes."""

from django.core.management.base import BaseCommand, CommandError

from analytics.coding_nomenclators import CatalogError, catalog_summary, load_catalog


class Command(BaseCommand):
    help = "Valida el esquema de un catálogo de codificación tumoral JSON."

    def add_arguments(self, parser):
        parser.add_argument("catalog_path", help="Ruta al JSON UTF-8 del catálogo")

    def handle(self, *args, **options):
        try:
            catalog = load_catalog(options["catalog_path"])
        except CatalogError as error:
            raise CommandError(str(error)) from error
        summary = catalog_summary(catalog)
        self.stdout.write(self.style.SUCCESS(f"Catálogo válido · versión {catalog['version']}"))
        for label, count in sorted(summary.items()):
            self.stdout.write(f"{label}: {count}")
