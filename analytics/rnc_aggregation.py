"""Build private, identifier-free aggregates from the RNC input and census file.

Source identifiers are not retained in aggregate records. The returned cubes contain grouped
counts and no source rows or person identifiers. It does not authorize a
public release or choose a disclosure-suppression policy.
"""

import csv
import hashlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .rnc_input import age_group, behavior_is_included, incidence_year, municipality_code, province_code, site_code
from .catalogs import TERRITORIES
from .standard import AGE_STANDARD_ID, AGE_STANDARD_WEIGHTS
from .rnc_classification import classify, catalog, child_catalog, reference_catalog

CASE_FIELDS = ("period", "territory", "municipality", "sex", "age_group", "site")
BREAKDOWN_FIELDS = ("morphology", "stage")
QUALITY_FIELDS = ("vh", "vh_known", "scd", "scd_known")
POPULATION_FIELDS = ("period", "territory", "municipality", "sex", "age_group")
SEX_LABELS = {"1": "Hombres", "2": "Mujeres"}
AGE_GROUPS = tuple([f"{age}-{age + 4}" for age in range(0, 85, 5)] + ["85+"])


def _aggregate_population_cube(strata):
    rows = list(strata)
    cube = {}
    for mask in range(1 << len(POPULATION_FIELDS)):
        fields = tuple(
            field for index, field in enumerate(POPULATION_FIELDS)
            if mask & (1 << index)
        )
        grouped = defaultdict(float)
        for row in rows:
            key = tuple(str(row[field]) for field in fields)
            grouped[key] += float(row["population"])
        cube[",".join(fields)] = [
            {**dict(zip(fields, key)), "population": population}
            for key, population in grouped.items()
        ]
    return cube


def read_census_population(path):
    """Read only the municipal age/sex block of the supplied 2022 workbook."""
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    header = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))
    if tuple(header[2:9]) != ("Provincia", "GrupoEdad", "Edad", "Municipio", "CodigoMunicipio", "Sexo", "Poblacion"):
        workbook.close()
        raise ValueError("El Excel no corresponde al esquema poblacional revisado.")
    totals = defaultdict(float)
    municipality_names = {}
    seen = 0
    source_keys = set()
    try:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            province, age, name, code, sex, population = (
                row[2], row[4], row[5], row[6], row[7], row[8]
            )
            if province is None or age is None or code is None or sex is None:
                continue
            if not isinstance(population, (int, float)):
                continue
            province_code_value = str(int(province))
            municipality = str(int(code))
            sex_label = SEX_LABELS.get(str(int(sex)))
            if sex_label is None:
                raise ValueError("El Excel poblacional contiene un código de sexo no reconocido.")
            source_key = (province_code_value, municipality, str(age), sex_label)
            if source_key in source_keys or not municipality.startswith(province_code_value) or population < 0:
                raise ValueError("El Excel poblacional contiene estratos repetidos o incompatibles.")
            source_keys.add(source_key)
            try:
                age_value = int(age)
            except (TypeError, ValueError):
                age_label = " ".join(str(age).strip().upper().split())
                if age_label != "85 MAS":
                    raise ValueError("El Excel de población contiene un grupo de edad no reconocido.")
                age_value = 85
            age_band = "85+" if age_value >= 85 else f"{(age_value // 5) * 5}-{(age_value // 5) * 5 + 4}"
            key = ("2022", province_code_value, municipality, sex_label, age_band)
            totals[key] += float(population)
            municipality_names[municipality] = str(name).strip()
            seen += 1
    finally:
        workbook.close()
    if not seen or not totals:
        raise ValueError("El bloque municipal de población no contiene estratos utilizables.")
    strata = [
        {**dict(zip(POPULATION_FIELDS, key)), "population": value}
        for key, value in totals.items()
    ]
    return strata, municipality_names


def _normalize_case(row):
    year = str(incidence_year(row))
    if year != "2022":
        raise ValueError("La población suministrada solo corresponde al año 2022.")
    source_sex = str(row["SEXO"]).strip()
    if source_sex not in SEX_LABELS:
        raise ValueError("SEXO contiene un código fuera del diccionario documentado.")
    age = int(row["EDAD"])
    if not behavior_is_included(row):
        return None
    province = province_code(row)
    municipality_suffix = municipality_code(row)
    municipality = province + municipality_suffix
    code_system = "CICN" if age < 20 else "C10"
    location = str(site_code(row)).strip()
    if not location:
        raise ValueError(f"Falta el campo {code_system} aplicable a la edad.")
    classification = classify(row)
    category = classification["category"]
    stage_eligible = age >= 20 and not (category.startswith("C") and (81 <= int(category[1:]) <= 86 or 91 <= int(category[1:]) <= 96))
    return {
        "person_id": row["NOCASO"].strip(),
        "period": year,
        "territory": province,
        "municipality": municipality,
        "sex": SEX_LABELS[source_sex],
        "age_group": age_group(row),
        # Preserve the source axis with the code; never imply a crosswalk.
        "site": classification["key"],
        "classification": classification,
        "morphology": row["MORF"].strip(),
        "morphology_behavior": row["MORF"].strip() + "/" + row["COMP"].strip(),
        "stage": row["ETAPA"].strip() or "missing",
        "stage_eligible": stage_eligible,
        "vh": int(row["MORF"].strip() != "8000"),
        "vh_known": int(bool(row["MORF"].strip())),
        "scd": int(row["UNIDIDAD"].strip() == "0000"),
        "scd_known": int(bool(row["UNIDIDAD"].strip())),
    }


def build_real_aggregate(clean_csv, population_xlsx, *, release_id, title):
    """Build a query-compatible in-memory candidate from the real 2022 files."""
    population, municipality_names = read_census_population(population_xlsx)
    population_keys = {
        tuple(str(row[field]) for field in POPULATION_FIELDS)
        for row in population
    }
    case_rows = []
    source_rows = excluded_behavior = unmatched_population = 0
    with Path(clean_csv).open(encoding="utf-8-sig", newline="") as stream:
        for source in csv.DictReader(stream):
            source_rows += 1
            normalized = _normalize_case(source)
            if normalized is None:
                excluded_behavior += 1
                continue
            population_key = tuple(normalized[field] for field in POPULATION_FIELDS)
            if population_key not in population_keys:
                unmatched_population += 1
            case_rows.append(normalized)
    if not case_rows:
        raise ValueError("No hay casos elegibles para construir el agregado.")
    if unmatched_population:
        raise ValueError("Hay estratos de casos sin correspondencia de población.")

    # NOCASO is the person key confirmed by the responsible user on 12-11-2026.
    # Sets stay private; only their cardinalities enter the public cube.
    person_ids = {row["person_id"] for row in case_rows}
    persons_disjoint = len(person_ids) == len(case_rows)
    cube = {}
    for mask in range(1 << len(CASE_FIELDS)):
        filters = tuple(
            field for index, field in enumerate(CASE_FIELDS)
            if mask & (1 << index)
        )
        for breakdown in (None, *BREAKDOWN_FIELDS):
            fields = filters + ((breakdown,) if breakdown else ())
            grouped = {}
            for row in case_rows:
                if breakdown == "stage" and not row["stage_eligible"]:
                    continue
                key = tuple(str(row[field]) for field in fields)
                state = grouped.setdefault(key, {"tumors": 0, "person_ids": set(), **dict.fromkeys(QUALITY_FIELDS, 0)})
                state["tumors"] += 1
                state["person_ids"].add(row["person_id"])
                for field in QUALITY_FIELDS:
                    state[field] += row[field]
            cube[",".join(fields)] = []
            for key, state in grouped.items():
                state["persons"] = len(state.pop("person_ids"))
                cube[",".join(fields)].append({**dict(zip(fields, key)), **state})

    options = {
        "period": sorted({row["period"] for row in case_rows}),
        "territory": sorted({row["territory"] for row in case_rows}),
        "municipality": sorted({row["municipality"] for row in case_rows}),
        "sex": sorted({row["sex"] for row in case_rows}),
        "age_group": [age for age in AGE_GROUPS if any(row["age_group"] == age for row in case_rows)],
        "site": sorted({row["site"] for row in case_rows}),
    }
    option_labels = {
        "site": {row["site"]: row["classification"]["label"] for row in case_rows},
        "morphology": {row["morphology"]: f"MORF {row['morphology']}" for row in case_rows},
        "stage": {row["stage"]: ("Sin información" if row["stage"] == "missing" else f"Etapa · código {row['stage']}") for row in case_rows if row["stage_eligible"]},
        "territory": {
            code: TERRITORIES.get(code, {}).get("name", code)
            for code in options["territory"]
        },
        "municipality": {
            code: municipality_names.get(code, code)
            for code in options["municipality"]
        },
    }
    option_labels["site_group"] = {row["classification"]["group"]: row["classification"]["group_label"] for row in case_rows}
    morphology_descriptions = defaultdict(set)
    for row in case_rows:
        code = row["morphology_behavior"]
        for term in reference_catalog()["morphology"].get(code, []):
            morphology_descriptions[row["morphology"]].add(f"{code}: {term}")
    return {
        "schema_version": 3,
        "synthetic": False,
        "publication_approved": False,
        "release_id": str(release_id),
        "title": str(title),
        "published_at": None,
        "prepared_at": datetime.now().astimezone().isoformat(),
        "options": options,
        "municipality_names": municipality_names,
        "option_labels": option_labels,
        "option_descriptions": {"morphology": {code: "; ".join(sorted(terms)) for code, terms in morphology_descriptions.items()}},
        "fields": list(CASE_FIELDS + BREAKDOWN_FIELDS),
        "person_identity_verified": True,
        "persons_disjoint": persons_disjoint,
        "persons_note": "Personas distintas por NOCASO, según aclaración del responsable de 12-11-2026.",
        "site_groups": {row["site"]: row["classification"]["group"] for row in case_rows},
        "site_group_labels": {row["classification"]["group"]: row["classification"]["group_label"] for row in case_rows},
        "site_systems": {row["site"]: row["classification"]["system"] for row in case_rows},
        "classification_version": catalog()[0]["version"],
        "rate_reference": reference_catalog()["rate_reference"],
        "provenance": {
            "prepared_csv_sha256": hashlib.sha256(Path(clean_csv).read_bytes()).hexdigest(),
            "population_xlsx_sha256": hashlib.sha256(Path(population_xlsx).read_bytes()).hexdigest(),
            "dictionary_docx_sha256": catalog()[0]["source_sha256"],
            "child_classification_xlsx_sha256": child_catalog()["source_sha256"],
            "reference_dictionary_sha256": reference_catalog()["sources"],
            "annuary_docx_sha256": reference_catalog()["rate_reference"]["sha256"],
        },
        "stage_note": "Códigos recibidos sin equivalencias inventadas. Leucemias y linfomas excluidos; excepción **** pendiente.",
        "population_fields": list(POPULATION_FIELDS),
        "population_cube": _aggregate_population_cube(population),
        "standard_id": AGE_STANDARD_ID,
        "standard_weights": AGE_STANDARD_WEIGHTS,
        "standard_authorized": True,
        "cube": cube,
        "audit": {
            "source_rows": source_rows,
            "included_rows": len(case_rows),
            "excluded_behavior_rows": excluded_behavior,
            "population_strata": len(population),
            "unmatched_population_strata": unmatched_population,
        },
    }
