from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from analytics.rnc_input import InputValidationError, write_clean_csv
from public_site.services import private_root


class Command(BaseCommand):
    help = "Limpia un CSV RNC a un archivo restringido, validando sus campos necesarios."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path, help="Ruta del CSV de entrada")

    def handle(self, *args, **options):
        source = options["source"]
        if not source.is_file():
            raise CommandError("No se encontró el archivo de entrada.")
        destination = private_root() / "prepared" / "BD_2022_limpio.csv"
        try:
            report = write_clean_csv(source, destination)
        except InputValidationError as exc:
            self.stderr.write("No se generó el archivo limpio:")
            for issue in exc.issues:
                self.stderr.write(f"- {issue}")
            if len(exc.issues) == 100:
                self.stderr.write("Se detuvo el informe tras 100 errores.")
            raise CommandError("Corrija el archivo de entrada y vuelva a cargarlo.") from exc
        except FileExistsError as exc:
            raise CommandError(
                "Ya existe un archivo limpio; muévalo de forma segura antes de repetir."
            ) from exc

        self.stdout.write("CSV limpio creado en almacenamiento privado.")
        self.stdout.write(f"Filas válidas: {report['rows_written']}")
        self.stdout.write(f"Filas vacías eliminadas: {report['empty_rows_removed']}")
        self.stdout.write(f"Columnas descartadas: {report['unused_columns_removed']}")
        self.stdout.write(f"Columnas conservadas: {report['kept_columns']}")
        for field, missing_count in report["optional_blanks"].items():
            if missing_count:
                self.stderr.write(
                    f"Aviso: {field} está vacío en {missing_count} filas; "
                    "los indicadores que dependan de ese campo quedan incompletos."
                )
