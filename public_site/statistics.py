"""Unique people from private records; public outputs contain only aggregates."""

from collections import defaultdict
from .services import published_records, WEIGHTS
from analytics.metrics import direct_standardized_rate

DIMENSIONS = {
    "site": "Grupo de localización ilustrativo",
    "territory": "Provincia de residencia",
    "sex": "Sexo",
    "age_group": "Edad",
    "period": "Período",
}


def select_records(params, rows=None):
    rows = published_records() if rows is None else rows
    return [
        r
        for r in rows
        if all(
            not params.get(key) or str(r[field]) == params[key]
            for key, field in [
                ("year", "period"),
                ("territory", "territory"),
                ("sex", "sex"),
                ("age", "age_group"),
                ("site", "site"),
            ]
        )
    ]


def summary(rows):
    people = {r["person_id"] for r in rows}
    denominators = {
        (r["period"], r["territory"], r["sex"], r["age_group"]): r["population"]
        for r in rows
    }
    population = sum(denominators.values())
    return {"tumors": len(rows), "persons": len(people), "population": population}


def _adjusted_rate(all_rows, params, dimension, label, unit):
    if params.get("age") or dimension == "age_group":
        return None
    cases_params = {key: params.get(key) for key in ("year", "territory", "sex", "site") if params.get(key)}
    population_params = {key: value for key, value in cases_params.items() if key != "site"}
    if dimension != "site":
        dimension_param = {
            "period": "year",
            "territory": "territory",
            "sex": "sex",
        }[dimension]
        cases_params[dimension_param] = label
        population_params[dimension_param] = label
    else:
        cases_params["site"] = label

    age_cases = {}
    age_population = {}
    for age in WEIGHTS:
        cases = summary(select_records({**cases_params, "age": age}, all_rows))[unit]
        population = summary(select_records({**population_params, "age": age}, all_rows))["population"]
        if population <= 0:
            return None
        age_cases[age] = cases
        age_population[age] = population
    return round(direct_standardized_rate(age_cases, age_population, WEIGHTS), 2)


def results(params, records=None):
    all_rows = published_records() if records is None else records
    selected = select_records(params, all_rows)
    dimension = params.get("dimension", "site")
    unit = params.get("unit", "tumors")
    measure = params.get("metric", "count")
    total = summary(selected)
    groups = defaultdict(list)
    for row in selected:
        groups[str(row[dimension])].append(row)
    coverage = select_records({**params, "site": ""}, all_rows)
    if dimension != "site":
        for row in coverage:
            groups.setdefault(str(row[dimension]), [])
    elif params.get("site") and coverage:
        groups.setdefault(params["site"], [])
    output = []
    for label, rows in groups.items():
        s = summary(rows)
        # A site filter must not remove healthy strata from the denominator.
        base = [
            r
            for r in all_rows
            if all(
                not params.get(k) or str(r[f]) == params[k]
                for k, f in [
                    ("year", "period"),
                    ("territory", "territory"),
                    ("sex", "sex"),
                    ("age", "age_group"),
                ]
            )
            and (dimension == "site" or str(r[dimension]) == label)
        ]
        denominator = summary(base)["population"]
        count = s[unit]
        value = count
        if measure == "share":
            value = count / total[unit] * 100 if total[unit] else 0
        elif measure == "rate":
            value = count / denominator * 100000 if denominator else 0
        elif measure == "asr":
            age_cases = {age: 0 for age in WEIGHTS}
            age_pop = {age: 0 for age in WEIGHTS}
            for age in WEIGHTS:
                age_cases[age] = summary([r for r in rows if r["age_group"] == age])[
                    unit
                ]
                age_pop[age] = summary([r for r in base if r["age_group"] == age])[
                    "population"
                ]
            value = (
                direct_standardized_rate(age_cases, age_pop, WEIGHTS)
                if all(age_pop.values())
                else None
            )
        output.append(
            {
                "label": label,
                "tumors": s["tumors"],
                "persons": s["persons"],
                "population": denominator,
                "relative_frequency": round(count / total[unit] * 100, 2) if total[unit] else None,
                "crude_rate": round(count / denominator * 100000, 2) if denominator else None,
                "adjusted_rate": _adjusted_rate(all_rows, params, dimension, label, unit),
                "value": round(value, 2) if value is not None else None,
            }
        )
    if dimension == "age_group":
        output.sort(key=lambda r: list(WEIGHTS).index(r["label"]))
    elif dimension == "period":
        output.sort(key=lambda r: r["label"])
    else:
        output.sort(key=lambda r: r["value"] or 0, reverse=True)
    return output, total
