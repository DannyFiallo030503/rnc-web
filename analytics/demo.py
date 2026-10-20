"""Consulta local de demostración sobre agregados inventados."""

import csv
from collections import defaultdict
from pathlib import Path

from .metrics import direct_standardized_rate, incidence_rate, relative_frequency
from .catalogs import resolve


FIXTURE = Path(__file__).parent / "fixtures" / "consulta_demo_sintetica.csv"


def load_rows():
    with FIXTURE.open(encoding="utf-8", newline="") as source:
        return [
            {
                **row,
                "territory": resolve("territory_id", row["territory_id"])["name"],
                "sex": resolve("sex_id", row["sex_id"])["name"],
                "age_group": resolve("age_group_id", row["age_group_id"])["name"],
                "site": resolve("site_id", row["site_id"])["name"],
                "period": int(row["period"]),
                "tumor_count": int(row["tumor_count"]),
                "person_count": int(row["person_count"]),
                "population": int(row["population"]),
                "standard_weight": int(row["standard_weight"]),
            }
            for row in csv.DictReader(source)
        ]


def choices(rows, field):
    values = dict.fromkeys(row[field] for row in rows)
    return sorted(values, key=int) if field == "period" else list(values)


def summarize(rows):
    """Aggregate counts and deduplicate repeated population denominators."""
    tumors = sum(row["tumor_count"] for row in rows)
    persons = sum(row["person_count"] for row in rows)
    denominators = {}
    cases_by_age = defaultdict(int)
    population_by_age = {}
    weights = {}
    for row in rows:
        denominator_key = (row["period"], row["territory"], row["sex"], row["age_group"])
        denominators[denominator_key] = row["population"]
        cases_by_age[row["age_group"]] += row["tumor_count"]
        weights[row["age_group"]] = row["standard_weight"]
    population = sum(denominators.values())
    for key, value in denominators.items():
        population_by_age[key[3]] = population_by_age.get(key[3], 0) + value
    age_groups = list(cases_by_age)
    tumor_rate = incidence_rate(tumors, population)
    person_rate = incidence_rate(persons, population)
    tumor_asr = direct_standardized_rate(cases_by_age, population_by_age, weights)
    person_cases_by_age = defaultdict(int)
    for row in rows:
        person_cases_by_age[row["age_group"]] += row["person_count"]
    person_asr = direct_standardized_rate(person_cases_by_age, population_by_age, weights)
    return {
        "tumors": tumors,
        "persons": persons,
        "population": population,
        "tumor_rate": tumor_rate,
        "person_rate": person_rate,
        "tumor_asr": tumor_asr,
        "person_asr": person_asr,
        "cases_by_age": cases_by_age,
        "persons_by_age": person_cases_by_age,
        "population_by_age": population_by_age,
        "weights": weights,
        "age_groups": age_groups,
    }


def query_data(filters):
    """Return all chart/table data for an already validated filter selection."""
    rows = load_rows()
    selected = [row for row in rows if all(
        filters[key] == "" or str(row[field]) == filters[key]
        for key, field in (("year", "period"), ("territory", "territory"), ("sex", "sex"), ("site", "site"), ("age", "age_group"))
    )]
    if not selected:
        return None
    summary = summarize(selected)
    total_tumors = summary["tumors"]
    total_persons = summary["persons"]
    age_rows = []
    for age in summary["age_groups"]:
        population = summary["population_by_age"][age]
        tumors = summary["cases_by_age"][age]
        persons = summary["persons_by_age"][age]
        age_rows.append({
            "age": age,
            "tumors": tumors,
            "persons": persons,
            "tumor_share": relative_frequency(tumors, total_tumors) if total_tumors else 0,
            "person_share": relative_frequency(persons, total_persons) if total_persons else 0,
            "tumor_rate": incidence_rate(tumors, population),
            "person_rate": incidence_rate(persons, population),
        })

    periods = choices(rows, "period")
    trend = []
    for year in periods:
        period_rows = [row for row in rows if row["period"] == year and
                       (filters["territory"] == "" or row["territory"] == filters["territory"]) and
                       (filters["sex"] == "" or row["sex"] == filters["sex"]) and
                       (filters["site"] == "" or row["site"] == filters["site"]) and
                       (filters["age"] == "" or row["age_group"] == filters["age"])]
        period_summary = summarize(period_rows)
        numerator = period_summary["persons"] if filters["unit"] == "persons" else period_summary["tumors"]
        trend.append({"year": year, "count": numerator,
                      "rate": period_summary["person_rate"] if filters["unit"] == "persons" else period_summary["tumor_rate"]})

    site_rows = [row for row in rows if (filters["year"] == "" or str(row["period"]) == filters["year"]) and
                 (filters["territory"] == "" or row["territory"] == filters["territory"]) and
                 (filters["sex"] == "" or row["sex"] == filters["sex"]) and
                 (filters["age"] == "" or row["age_group"] == filters["age"])]
    site_summary = []
    for site in choices(rows, "site"):
        site_data = summarize([row for row in site_rows if row["site"] == site])
        site_value = site_data["persons"] if filters["unit"] == "persons" else site_data["tumors"]
        site_summary.append({"label": site, "value": site_value})

    return {
        "summary": summary,
        "age_rows": age_rows,
        "trend": trend,
        "site_summary": site_summary,
        "unit_label": "Personas distintas" if filters["unit"] == "persons" else "Tumores registrados",
        "measure_label": "Tasa cruda por 100 000" if filters["measure"] == "crude" else "Tasa estandarizada por edad (Segi–Doll)",
    }
