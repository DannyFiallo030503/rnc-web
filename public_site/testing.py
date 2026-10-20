"""Synthetic test contracts, independent of every local/private dataset."""

import csv
import io
from django.core.files.uploadedfile import SimpleUploadedFile
from .services import HEADER, WEIGHTS
from analytics.catalogs import id_for


def synthetic_rows(extra=1):
    rows = []
    for year in (2023, 2024):
        for sex_index, sex in enumerate(("Mujeres", "Hombres")):
            for index, (age, weight) in enumerate(WEIGHTS.items()):
                rows.append(
                    dict(
                        zip(
                            HEADER,
                            [
                                "TRUE",
                                f"SYN-P-{sex_index}-{index}",
                                f"SYN-T-{year}-{sex_index}-{index}",
                                str(year),
                                id_for("territory_id", "La Habana"),
                                id_for("sex_id", sex),
                                id_for("age_group_id", age),
                                id_for("site_id", "Mama" if sex_index == 0 else "Colon y recto"),
                                "10000",
                                str(weight),
                            ],
                        )
                    )
                )
    source = next(
        r
        for r in rows
        if r["period"] == "2024"
        and r["age_group_id"] == id_for("age_group_id", "45-49")
        and r["sex_id"] == id_for("sex_id", "Mujeres")
    )
    for number in range(extra):
        rows.append(
            {
                **source,
                "tumor_id": f"SYN-T-EXTRA-{number}",
                "site_id": id_for("site_id", "Colon y recto"),
            }
        )
    return rows


def csv_bytes(rows=None, extra=1):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(synthetic_rows(extra) if rows is None else rows)
    return output.getvalue().encode()


def uploaded(extra=1, rows=None, name="sintetico.csv"):
    return SimpleUploadedFile(name, csv_bytes(rows, extra), content_type="text/csv")
