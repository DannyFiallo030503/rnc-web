"""Unique people from private records; public outputs contain only aggregates."""

from collections import defaultdict
from .services import published_records, WEIGHTS
from analytics.metrics import direct_standardized_rate

DIMENSIONS = {
    "site": "Grupo de localización ilustrativo",
    "territory": "Territorio",
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
