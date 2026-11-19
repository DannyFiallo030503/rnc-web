"""Private input cleanup for the RNC integration CSV.

Output contains the restricted case identifier NOCASO and belongs in private
storage. It must never be placed in the static/public release directory.
"""

import csv
from datetime import datetime


# Fields used by the DOCX-defined charts and quality indicator.
SOURCE_FIELDS = (
    "UNIDIDAD",
    "EDAD",
    "FECHAD",
    "MORF",
    "COMP",
    "ETAPA",
    "C10",
    "CICN",
    "NOCASO",
    "SEXO",
    "PROV",
)
REQUIRED_FIELDS = tuple(
    field for field in SOURCE_FIELDS
    if field not in {"UNIDIDAD", "ETAPA", "C10", "CICN"}
)
OPTIONAL_FIELDS = ("UNIDIDAD", "ETAPA")
OUTPUT_FIELDS = SOURCE_FIELDS

class InputValidationError(ValueError):
    def __init__(self, issues, rows_seen):
        self.issues = tuple(issues)
        self.rows_seen = rows_seen
        super().__init__("El CSV contiene filas incompletas o incompatibles.")


def _parse_date(value):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError("FECHAD no tiene un formato de fecha admitido")


def incidence_year(row):
    """Return the year component of the source field FECHAD."""
    return _parse_date(row["FECHAD"]).year


def age_group(row):
    """Return a five-year band calculated from the source field EDAD."""
    age = int(row["EDAD"])
    start = min((age // 5) * 5, 85)
    return "85+" if start == 85 else f"{start}-{start + 4}"


def province_code(row):
    """The DOCX defines the first two characters of PROV as province."""
    return row["PROV"].strip()[:2]


def municipality_code(row):
    """The remaining characters of the source field PROV are municipality."""
    return row["PROV"].strip()[2:]


def site_code(row):
    """Select the documented source site field using EDAD's under-20 rule."""
    return row["CICN"] if int(row["EDAD"]) < 20 else row["C10"]


def behavior_is_included(row):
    """Apply the DOCX behavior rule directly to COMP and EDAD."""
    return row["COMP"].strip() != "2" if int(row["EDAD"]) < 20 else row["COMP"].strip() == "3"


def _normalize(row):
    cleaned = {field: row[field].strip() for field in SOURCE_FIELDS}
    try:
        age = int(cleaned["EDAD"])
    except ValueError as exc:
        raise ValueError("EDAD debe ser un entero") from exc
    if not 0 <= age <= 120:
        raise ValueError("EDAD está fuera del rango admitido")
    if cleaned["COMP"] not in {str(value) for value in range(10)}:
        raise ValueError("COMP debe contener un código de comportamiento de un dígito")
    if len(cleaned["MORF"]) != 4 or not cleaned["MORF"].isdigit():
        raise ValueError("MORF debe conservar el código histológico de cuatro dígitos")
    if cleaned["SEXO"] not in {"1", "2"}:
        raise ValueError("SEXO no corresponde al diccionario suministrado")
    incidence_year(cleaned)

    territory = cleaned["PROV"].strip()
    if not territory.isdigit() or len(territory) < 3:
        raise ValueError("PROV debe contener el código territorial documentado")
    site_field = "CICN" if age < 20 else "C10"
    if not site_code(cleaned):
        raise ValueError(f"Falta el campo {site_field} aplicable a la edad")
    from .rnc_classification import classify
    classify(cleaned)

    # Validate the DOCX-driven derivations here, but persist only source fields.
    # Query code derives year, age band, geography and age-specific site from
    # FECHAD, EDAD, PROV, C10 and CICN at calculation time.
    return cleaned


def write_clean_csv(source, destination):
    """Remove empty rows/unused columns and atomically write a private CSV.

    Validation issues contain only line numbers and field names, not source
    values. The destination is never overwritten.
    """
    import os
    import tempfile
    from pathlib import Path

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination.parent, 0o700)
    handle, temporary = tempfile.mkstemp(prefix=".rnc-clean-", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            with open(source, "r", encoding="utf-8-sig", newline="") as input_stream:
                reader = csv.reader(input_stream)
                headers = [header.strip() for header in next(reader, [])]
                if not headers or any(not header for header in headers):
                    raise InputValidationError(["Encabezado ausente o vacío"], 0)
                if len(headers) != len(set(headers)):
                    raise InputValidationError(["Hay encabezados duplicados"], 0)
                missing_headers = [field for field in SOURCE_FIELDS if field not in headers]
                if missing_headers:
                    raise InputValidationError(
                        ["Faltan campos requeridos: " + ", ".join(missing_headers)], 0
                    )
                positions = {field: headers.index(field) for field in SOURCE_FIELDS}
                issues = []
                optional_blanks = {field: 0 for field in OPTIONAL_FIELDS}
                rows_seen = rows_written = empty_rows = 0
                persons = set()

                for line_number, values in enumerate(reader, start=2):
                    if not values or not any(value.strip() for value in values):
                        empty_rows += 1
                        continue
                    rows_seen += 1
                    row = {
                        field: values[index] if index < len(values) else ""
                        for field, index in positions.items()
                    }
                    missing = [field for field in REQUIRED_FIELDS if not row[field].strip()]
                    if missing:
                        issues.append(
                            f"Fila {line_number}: faltan campos requeridos: {', '.join(missing)}"
                        )
                    else:
                        for field in OPTIONAL_FIELDS:
                            if not row[field].strip():
                                optional_blanks[field] += 1
                        try:
                            writer.writerow(_normalize(row))
                            persons.add(row["NOCASO"].strip())
                            rows_written += 1
                        except ValueError as exc:
                            issues.append(f"Fila {line_number}: {exc}")
                    if len(issues) >= 100:
                        break

            if issues:
                raise InputValidationError(issues, rows_seen)
            if not rows_written:
                raise InputValidationError(["El CSV no contiene filas de datos"], rows_seen)
            output.flush()
            os.fsync(output.fileno())

        os.chmod(temporary, 0o600)
        if destination.exists():
            raise FileExistsError("El destino ya existe; no se sobrescribió")
        os.replace(temporary, destination)
        return {
            "rows_seen": rows_seen,
            "person_count": len(persons),
            "rows_written": rows_written,
            "empty_rows_removed": empty_rows,
            "source_columns": len(headers),
            "kept_columns": len(SOURCE_FIELDS),
            "unused_columns_removed": len(headers) - len(SOURCE_FIELDS),
            "optional_blanks": optional_blanks,
        }
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
