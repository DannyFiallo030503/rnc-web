"""Query the public aggregate cube; this module never reads private rows."""

from analytics.metrics import direct_standardized_rate

WEIGHTS = dict(
    zip(
        [f"{n}-{n+4}" for n in range(0, 85, 5)] + ["85+"],
        [
            12000,
            10000,
            9000,
            9000,
            8000,
            8000,
            6000,
            6000,
            6000,
            6000,
            5000,
            4000,
            4000,
            3000,
            2000,
            1000,
            500,
            500,
        ],
    )
)

DIMENSIONS = {
    "site": "Grupo de localización ilustrativo",
    "territory": "Territorio",
    "sex": "Sexo",
    "age_group": "Edad",
    "period": "Período",
}
FILTER_FIELDS = {
    "year": "period",
    "territory": "territory",
    "sex": "sex",
    "age": "age_group",
    "site": "site",
}


def _cell(release, conditions):
    fields = tuple(field for field in release["fields"] if field in conditions)
    cells = release["cube"].get(",".join(fields), [])
    for cell in cells:
        if all(str(cell.get(field)) == str(value) for field, value in conditions.items()):
            return cell
    return None


def _summary(release, conditions):
    cell = _cell(release, conditions)
    if not cell:
        return {"tumors": 0, "persons": 0, "population": 0}
    return {key: cell[key] for key in ("tumors", "persons", "population")}


def _number(summary, unit):
    return summary["persons"] if unit == "persons" else summary["tumors"]


def results(params, release):
    conditions = {
        field: str(params[key])
        for key, field in FILTER_FIELDS.items()
        if params.get(key)
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
    grouped = {
        str(cell[dimension]): cell
        for cell in case_cells
        if dimension in cell
        and all(
            str(cell.get(field)) == str(value)
            for field, value in conditions.items()
        )
    }

    if dimension != "site":
        coverage_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        coverage_fields = set(coverage_conditions) | {dimension}
        coverage_cells = release["cube"].get(",".join(f for f in release["fields"] if f in coverage_fields), [])
        for cell in coverage_cells:
            if all(
                str(cell.get(field)) == str(value)
                for field, value in coverage_conditions.items()
            ):
                grouped.setdefault(str(cell[dimension]), None)
    elif params.get("site"):
        coverage_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        if _cell(release, coverage_conditions):
            grouped.setdefault(str(params["site"]), None)

    labels = list(grouped)
    if dimension == "age_group":
        labels.sort(key=lambda age: list(WEIGHTS).index(age))
    elif dimension == "period":
        labels.sort()

    output = []
    for label in labels:
        cell = grouped[label]
        counts = {
            "tumors": cell["tumors"] if cell else 0,
            "persons": cell["persons"] if cell else 0,
        }
        base_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        if dimension != "site":
            base_conditions[dimension] = label
        denominator = _summary(release, base_conditions)["population"]
        count = counts[unit]
        value = count
        if measure == "share":
            value = count / total[unit] * 100 if total[unit] else 0
        elif measure == "rate":
            value = count / denominator * 100000 if denominator else 0
        elif measure == "asr":
            age_cases = {age: 0 for age in WEIGHTS}
            age_population = {age: 0 for age in WEIGHTS}
            for age in WEIGHTS:
                case_conditions = dict(conditions)
                case_conditions["age_group"] = age
                if dimension != "site":
                    case_conditions[dimension] = label
                age_cases[age] = _number(_summary(release, case_conditions), unit)
                pop_conditions = dict(base_conditions)
                pop_conditions["age_group"] = age
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
                "value": round(value, 2) if value is not None else None,
            }
        )

    if dimension not in {"age_group", "period"}:
        output.sort(key=lambda row: row["value"] or 0, reverse=True)
    return output, total
