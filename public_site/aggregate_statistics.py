"""Query the public aggregate cube; this module never reads private rows."""

from analytics.metrics import direct_standardized_rate
from analytics.standard import AGE_STANDARD_WEIGHTS as WEIGHTS
from django.utils.translation import gettext_lazy as _

DIMENSIONS = {
    "site": _("Grupo de localización"),
    "territory": _("Provincia de residencia"),
    "sex": _("Sexo"),
    "age_group": _("Edad"),
    "period": _("Año de incidencia"),
}
FILTER_FIELDS = {
    "year": "period",
    "territory": "territory",
    "municipality": "municipality",
    "sex": "sex",
    "age": "age_group",
    "site": "site",
}


def _values(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _cells(release, conditions):
    fields = tuple(field for field in release["fields"] if field in conditions)
    cells = release["cube"].get(",".join(fields), [])
    return [
        cell
        for cell in cells
        if all(
            not _values(values) or str(cell.get(field)) in _values(values)
            for field, values in conditions.items()
        )
    ]


def _summary(release, conditions):
    cells = _cells(release, conditions)
    if not cells:
        return {"tumors": 0, "persons": None if _has_multiple_values(conditions) else 0, "population": 0}
    persons = (
        None
        if _has_multiple_values(conditions)
        else sum(cell["persons"] for cell in cells)
    )
    return {
        "tumors": sum(cell["tumors"] for cell in cells),
        "persons": persons,
        "population": sum(cell["population"] for cell in cells),
    }


def _has_multiple_values(conditions):
    return any(len(_values(value)) > 1 for value in conditions.values())


def _matches(cell, conditions):
    return all(
        not _values(values) or str(cell.get(field)) in _values(values)
        for field, values in conditions.items()
    )


def _number(summary, unit):
    return summary["persons"] if unit == "persons" else summary["tumors"]


def _adjusted_rate(release, conditions, dimension, label, unit):
    if "age_group" in conditions or dimension == "age_group":
        return None

    cases_base = {field: values for field, values in conditions.items() if field != "age_group"}
    population_base = {
        field: values
        for field, values in conditions.items()
        if field not in {"age_group", "site"}
    }
    if dimension != "site":
        cases_base[dimension] = [label]
        population_base[dimension] = [label]
    else:
        cases_base["site"] = [label]

    age_cases = {}
    age_population = {}
    for age in WEIGHTS:
        case_conditions = {**cases_base, "age_group": [age]}
        pop_conditions = {**population_base, "age_group": [age]}
        case_count = _number(_summary(release, case_conditions), unit)
        population = _summary(release, pop_conditions)["population"]
        if case_count is None or population <= 0:
            return None
        age_cases[age] = case_count
        age_population[age] = population

    return round(direct_standardized_rate(age_cases, age_population, WEIGHTS), 2)


def results(params, release):
    conditions = {
        field: _values(params[key])
        for key, field in FILTER_FIELDS.items()
        if _values(params.get(key))
    }
    dimension = params.get("dimension", "site")
    unit = params.get("unit", "tumors")
    measure = params.get("metric", "count")
    total = _summary(release, conditions)

    group_conditions = dict(conditions)
    group_fields = set(group_conditions)
    if dimension not in group_fields:
        group_fields.add(dimension)
    case_cells = release["cube"].get(",".join(f for f in release["fields"] if f in group_fields), [])
    multiple_values = _has_multiple_values(conditions)
    grouped = {}
    for cell in case_cells:
        if dimension not in cell or not _matches(cell, conditions):
            continue
        label = str(cell[dimension])
        row = grouped.setdefault(
            label,
            {"tumors": 0, "persons": None if multiple_values else 0},
        )
        row["tumors"] += cell["tumors"]
        if not multiple_values:
            row["persons"] += cell["persons"]

    if dimension != "site":
        coverage_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        coverage_fields = set(coverage_conditions) | {dimension}
        coverage_cells = release["cube"].get(",".join(f for f in release["fields"] if f in coverage_fields), [])
        for cell in coverage_cells:
            if _matches(cell, coverage_conditions):
                grouped.setdefault(
                    str(cell[dimension]),
                    {"tumors": 0, "persons": None if multiple_values else 0},
                )
    elif conditions.get("site"):
        coverage_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        if _cells(release, coverage_conditions):
            for site in conditions["site"]:
                grouped.setdefault(
                    str(site),
                    {"tumors": 0, "persons": None if multiple_values else 0},
                )

    labels = list(grouped)
    if dimension == "age_group":
        labels.sort(key=lambda age: list(WEIGHTS).index(age))
    elif dimension == "period":
        labels.sort()

    output = []
    for label in labels:
        counts = grouped[label]
        base_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        if dimension != "site":
            base_conditions[dimension] = [label]
        denominator = _summary(release, base_conditions)["population"]
        count = counts[unit]
        value = count
        if measure == "share":
            value = count / total[unit] * 100 if count is not None and total[unit] else 0
        elif measure == "rate":
            value = count / denominator * 100000 if count is not None and denominator else 0
        elif measure == "asr":
            age_cases = {age: 0 for age in WEIGHTS}
            age_population = {age: 0 for age in WEIGHTS}
            for age in WEIGHTS:
                case_conditions = dict(conditions)
                case_conditions["age_group"] = [age]
                if dimension != "site":
                    case_conditions[dimension] = [label]
                age_cases[age] = _number(_summary(release, case_conditions), unit)
                pop_conditions = dict(base_conditions)
                pop_conditions["age_group"] = [age]
                age_population[age] = _summary(release, pop_conditions)["population"]
            value = (
                direct_standardized_rate(age_cases, age_population, WEIGHTS)
                if all(age_population.values())
                else None
            )
        output.append(
            {
                "label": label,
                "tumors": counts["tumors"],
                "persons": counts["persons"],
                "population": denominator,
                "relative_frequency": (
                    round(count / total[unit] * 100, 2)
                    if count is not None and total[unit]
                    else None
                ),
                "crude_rate": (
                    round(count / denominator * 100000, 2)
                    if count is not None and denominator
                    else None
                ),
                "adjusted_rate": _adjusted_rate(
                    release, conditions, dimension, label, unit
                ),
                "value": round(value, 2) if value is not None else None,
            }
        )

    if dimension not in {"age_group", "period"}:
        output.sort(key=lambda row: row["value"] or 0, reverse=True)
    return output, total
