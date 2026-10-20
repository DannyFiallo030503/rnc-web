"""Catálogos del demo y transcripción versionada del Manual RNC VII."""

import csv
from pathlib import Path


def _items(rows, *, version="demo-1", status="synthetic"):
    return {
        code: {
            "id": code,
            "concept_id": code,
            "name": name,
            "description": detail,
            "identifiers": [],
            "version": version,
            "status": status,
        }
        for code, name, detail in rows
    }


TERRITORIES = _items(
    [
        ("21", "Pinar del Río", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("22", "Artemisa", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("23", "La Habana", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("24", "Mayabeque", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("25", "Matanzas", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("26", "Villa Clara", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("27", "Cienfuegos", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("28", "Sancti Spíritus", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("29", "Ciego de Ávila", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("30", "Camagüey", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("31", "Las Tunas", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("32", "Holguín", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("33", "Granma", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("34", "Santiago de Cuba", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("35", "Guantánamo", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
        ("40", "Isla de la Juventud", "Código de provincia documentado en el Manual RNC VII, Anexo 1."),
    ],
    version="Manual RNC VII (2024); DPA 2011",
    status="documented",
)
SEXES = _items(
    [
        ("01", "Mujeres", "Categoría de sexo del conjunto sintético."),
        ("02", "Hombres", "Categoría de sexo del conjunto sintético."),
    ]
)
AGES = _items(
    [
        (f"{i + 1:02}", f"{start}-{start + 4}", "Grupo quinquenal sintético.")
        for i, start in enumerate(range(0, 85, 5))
    ] + [("18", "85+", "Grupo abierto sintético desde 85 años.")]
)
SITES = _items(
    [
            (f"{i:03}", name, f"Grupo ilustrativo sintético; no representa un código TOPO ni un crosswalk: {name}.")
        for i, name in enumerate(
            [
                "Tráquea, bronquios y pulmón", "Próstata", "Mama", "Colon y recto",
                "Estómago", "Cuello del útero", "Cuerpo del útero", "Tiroides",
                "Páncreas", "Vejiga urinaria", "Riñón", "Hígado y vías biliares",
                "Ovario", "Laringe y faringe",
            ],
            1,
        )
    ]
)


def _load_unit_informants():
    path = Path(__file__).parent / "fixtures" / "catalogo_unidades_informantes_manual_vii.csv"
    with path.open(encoding="utf-8", newline="") as source:
        return {
            row["id"]: {
                **row,
                "name": row["name"],
                "description": row["description"],
                "version": row["version"],
            }
            for row in csv.DictReader(source)
        }


UNIT_INFORMANTS = _load_unit_informants()

CATALOGS = {
    "territory_id": TERRITORIES,
    "sex_id": SEXES,
    "age_group_id": AGES,
    "site_id": SITES,
    "unit_informant_id": UNIT_INFORMANTS,
}


def resolve(code_field, code):
    """Return catalog metadata for an ID, failing closed on unknown identifiers."""
    return CATALOGS[code_field][str(code)]


def id_for(code_field, name):
    return next(
        code for code, item in CATALOGS[code_field].items() if item["name"] == name
    )
