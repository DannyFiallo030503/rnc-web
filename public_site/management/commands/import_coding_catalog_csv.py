"""Convert an explicitly normalized CSV into the versioned JSON catalog."""

import csv
import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from analytics.coding_nomenclators import CatalogError, validate_catalog_payload


CSV_FIELDS = (
    "concept_id", "concept_name", "concept_description", "language",
    "concept_source", "concept_license", "publication_status", "system",
    "edition", "axis", "code", "code_name", "code_description",
    "code_status", "code_source", "code_license", "relationship",
    "relationship_status",
)
CONCEPT_FIELDS = {
    "concept_id": "concept_id",
    "concept_name": "name",
    "concept_description": "description",
    "language": "language",
    "concept_source": "source",
    "concept_license": "license",
    "publication_status": "publication_status",
}
CODE_FIELDS = {
    "system": "system", "edition": "edition", "axis": "axis",
    "code": "code", "code_name": "name", "code_description": "description",
    "code_status": "status", "code_source": "source", "code_license": "license",
    "relationship": "relationship", "relationship_status": "relationship_status",
}


class Command(BaseCommand):
    help = "Convierte un CSV normalizado en el catálogo JSON versionado."

    def add_arguments(self, parser):
        parser.add_argument("input_path", help="CSV UTF-8 normalizado con encabezados exactos")
        parser.add_argument("output_path", help="Ruta de salida JSON; no debe existir")
        parser.add_argument("--catalog-version", required=True, help="Versión explícita del conjunto")
        parser.add_argument("--source", required=True, help="URL de procedencia del conjunto")
        parser.add_argument("--force", action="store_true", help="Reemplaza el JSON de salida")

    def handle(self, *args, **options):
        input_path = Path(options["input_path"])
        output_path = Path(options["output_path"])
        if input_path.resolve() == output_path.resolve():
            raise CommandError("La entrada CSV y la salida JSON deben ser archivos distintos.")
        if output_path.exists() and not options["force"]:
            raise CommandError("La salida ya existe; usa --force para reemplazarla.")
        if not output_path.parent.is_dir():
            raise CommandError("El directorio de salida debe existir.")

        payload = self._read_csv(input_path, options["catalog_version"], options["source"])
        try:
            catalog = validate_catalog_payload(payload)
        except CatalogError as error:
            raise CommandError(str(error)) from error

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=output_path.parent,
                prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
            ) as target:
                temporary_path = Path(target.name)
                json.dump(
                    {key: catalog[key] for key in ("version", "source", "concepts")},
                    target, ensure_ascii=False, indent=2,
                )
                target.write("\n")
            if output_path.exists() and not options["force"]:
                raise CommandError("La salida ya existe; usa --force para reemplazarla.")
            os.replace(temporary_path, output_path)
        except OSError as error:
            raise CommandError("No se pudo escribir el catálogo JSON de salida.") from error
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo JSON creado · versión {catalog['version']} · "
            f"{sum(len(item['codes']) for item in catalog['concepts'])} códigos"
        ))

    @staticmethod
    def _read_csv(path, version, source):
        try:
            stream = path.open("r", encoding="utf-8-sig", newline="")
        except OSError as error:
            raise CommandError("No se pudo abrir el CSV normalizado.") from error

        concepts, by_id = [], {}
        try:
            with stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames != list(CSV_FIELDS):
                    raise CommandError(
                        "Los encabezados del CSV deben coincidir exactamente con el contrato documentado."
                    )
                for row_number, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        raise CommandError(f"Fila {row_number}: cantidad de columnas inválida.")
                    if not any(value.strip() for value in row.values()):
                        continue
                    concept_data = {
                        target: row[column].strip()
                        for column, target in CONCEPT_FIELDS.items()
                    }
                    code_data = {
                        target: row[column] if column == "code" else row[column].strip()
                        for column, target in CODE_FIELDS.items()
                    }
                    if not code_data["code"].strip() or code_data["code"] != code_data["code"].strip():
                        raise CommandError(f"Fila {row_number}: el código está vacío o tiene espacios externos.")
                    concept_id = concept_data["concept_id"]
                    if not concept_id:
                        raise CommandError(f"Fila {row_number}: falta el identificador explícito del concepto.")
                    concept = by_id.get(concept_id)
                    if concept is None:
                        concept = {**concept_data, "codes": []}
                        by_id[concept_id] = concept
                        concepts.append(concept)
                    elif any(concept[key] != value for key, value in concept_data.items()):
                        raise CommandError(
                            f"Fila {row_number}: los metadatos del concepto no coinciden entre sus códigos."
                        )
                    concept["codes"].append(code_data)
        except (OSError, UnicodeError, csv.Error) as error:
            raise CommandError("El CSV no se puede leer como UTF-8 válido y con la estructura esperada.") from error

        return {"version": version, "source": source, "concepts": concepts}
