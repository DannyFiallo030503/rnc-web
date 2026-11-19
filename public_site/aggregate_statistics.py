"""Query the public aggregate cube; this module never reads private rows."""

from analytics.metrics import direct_standardized_rate
from analytics.standard import AGE_STANDARD_WEIGHTS as WEIGHTS
from django.utils.translation import gettext_lazy as _
from itertools import product
from analytics.rnc_classification import code_set

DIMENSIONS = {
    "site": _("Grupo de localización"),
    "site_group": _("Grupo tumoral principal"),
    "morphology": _("Tipo histológico (MORF)"),
    "stage": _("Etapa clínica (código recibido)"),
    "territory": _("Provincia de residencia"),
    "municipality": _("Municipio de residencia"),
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
COHORT_AGES = {
    "all": list(WEIGHTS),
    "adult": list(WEIGHTS)[4:],
    "child": list(WEIGHTS)[:4],
}
QUALITY_FIELDS = ("vh", "vh_known", "scd", "scd_known")
DOCUMENT_TOTALS = {"DOCX:C00-97": "C00-97", "ANUARIO:C00-96": "C00-96"}


def _expanded_site_filters(params, release):
    sites = _values(params.get("site"))
    selected_totals = set(sites) & DOCUMENT_TOTALS.keys()
    if not selected_totals:
        return params
    categories = frozenset().union(*(code_set(DOCUMENT_TOTALS[key]) for key in selected_totals))
    members = [site for site in release["options"]["site"] if site.startswith("C10:") and code_set(site[4:]) <= categories]
    return {**params, "site": list(dict.fromkeys([site for site in sites if site not in DOCUMENT_TOTALS] + members))}


def _values(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return list(dict.fromkeys(str(item) for item in value if item not in (None, "")))
    return [str(value)]


def _cells(release, conditions):
    fields = tuple(
        field
        for field in release["fields"]
        if field in conditions and _values(conditions[field])
    )
    if any(
        _values(values) and field not in release["fields"]
        for field, values in conditions.items()
    ):
        return []
    key = ",".join(fields)
    indexes = release.setdefault("_cube_indexes", {})
    index = indexes.get(key)
    if index is None:
        index = {
            tuple(str(cell.get(field, "")) for field in fields): cell
            for cell in release["cube"].get(key, [])
        }
        indexes[key] = index
    selections = [_values(conditions[field]) for field in fields]
    selected_keys = product(*selections) if selections else [()]
    return [
        index[tuple(values)]
        for values in selected_keys
        if tuple(values) in index
    ]


def rate_scale(cohort):
    return 1000000 if cohort == "child" else 100000


def _summary(release, conditions):
    cells = _cells(release, conditions)
    if not cells:
        return {
            "tumors": 0,
            "persons": 0 if release.get("person_identity_verified") else None,
            "population": _population(release, conditions),
            **dict.fromkeys(QUALITY_FIELDS, 0),
        }
    persons = (
        None
        if not release.get("person_identity_verified") or (_has_multiple_values(conditions) and not release.get("persons_disjoint"))
        else sum(cell["persons"] for cell in cells)
    )
    return {
        "tumors": sum(cell["tumors"] for cell in cells),
        "persons": persons,
        "population": _population(release, conditions)
        if "population_cube" in release
        else sum(cell["population"] for cell in cells),
        **{field: sum(cell.get(field, 0) for cell in cells) for field in QUALITY_FIELDS},
    }


def _population(release, conditions):
    """Sum each resident population stratum once, including zero-case strata."""
    population_cube = release.get("population_cube")
    if population_cube is None:
        return 0
    fields = tuple(
        field
        for field in release.get("population_fields", ())
        if field in conditions
    )
    key = ",".join(fields)
    cells = population_cube.get(key, [])
    indexes = release.setdefault("_population_indexes", {})
    index = indexes.get(key)
    if index is None:
        grouped = {}
        for cell in cells:
            cell_key = tuple(str(cell.get(field, "")) for field in fields)
            grouped[cell_key] = grouped.get(cell_key, 0) + cell["population"]
        index = indexes[key] = grouped

    selections = [_values(conditions[field]) for field in fields]
    combinations_count = 1
    for selection in selections:
        combinations_count *= len(selection)
    if combinations_count <= max(1, len(cells)):
        combinations = product(*selections) if selections else [()]
        return sum(index.get(tuple(values), 0) for values in combinations)
    return sum(
        cell["population"]
        for cell in cells
        if all(str(cell.get(field)) in _values(conditions[field]) for field in fields)
    )


def _has_multiple_values(conditions):
    return any(len(_values(value)) > 1 for value in conditions.values())


def _matches(cell, conditions):
    return all(
        not _values(values) or str(cell.get(field)) in _values(values)
        for field, values in conditions.items()
    )


def _number(summary, unit):
    return summary["persons"] if unit == "persons" else summary["tumors"]


def _adjusted_rate(release, conditions, dimension, label, unit, cohort="all"):
    ages = COHORT_AGES[cohort]
    if dimension in {"age_group", "stage"} or ("age_group" in conditions and set(conditions["age_group"]) != set(ages)):
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
        cases_base["site"] = _values(label)

    age_cases = {}
    age_population = {}
    for age in ages:
        case_conditions = {**cases_base, "age_group": [age]}
        pop_conditions = {**population_base, "age_group": [age]}
        case_count = _number(_summary(release, case_conditions), unit)
        population = _summary(release, pop_conditions)["population"]
        if case_count is None or population <= 0:
            return None
        age_cases[age] = case_count
        age_population[age] = population

    return round(direct_standardized_rate(age_cases, age_population, {age: WEIGHTS[age] for age in ages}, scale=rate_scale(cohort)), 2)


def results(params, release):
    params = _expanded_site_filters(params, release)
    if params.get("dimension") == "site_group":
        return _grouped_sites(params, release)
    conditions = {
        field: _values(params[key])
        for key, field in FILTER_FIELDS.items()
        if _values(params.get(key))
    }
    dimension = params.get("dimension", "site")
    cohort = params.get("cohort", "all")
    if cohort not in COHORT_AGES:
        raise ValueError("Población de análisis no reconocida.")
    if cohort != "all":
        allowed = set(COHORT_AGES[cohort])
        selected = conditions.get("age_group", COHORT_AGES[cohort])
        conditions["age_group"] = [age for age in selected if age in allowed]
        if not conditions["age_group"]:
            return [], {"tumors": 0, "persons": None, "population": 0}
    unit = params.get("unit", "tumors")
    measure = params.get("metric", "count")
    total = _summary(release, conditions)

    group_conditions = dict(conditions)
    group_fields = set(group_conditions)
    if dimension not in group_fields:
        group_fields.add(dimension)
    case_cells = release["cube"].get(",".join(f for f in release["fields"] if f in group_fields), [])
    multiple_values = not release.get("person_identity_verified") or (_has_multiple_values(conditions) and not release.get("persons_disjoint"))
    grouped = {}
    for cell in case_cells:
        if dimension not in cell or not _matches(cell, conditions):
            continue
        label = str(cell[dimension])
        row = grouped.setdefault(
            label,
            {"tumors": 0, "persons": None if multiple_values else 0, **dict.fromkeys(QUALITY_FIELDS, 0)},
        )
        row["tumors"] += cell["tumors"]
        for field in QUALITY_FIELDS:
            row[field] += cell.get(field, 0)
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
                    {"tumors": 0, "persons": None if multiple_values else 0, **dict.fromkeys(QUALITY_FIELDS, 0)},
                )
    elif conditions.get("site"):
        coverage_conditions = {
            field: value for field, value in conditions.items() if field != "site"
        }
        if _cells(release, coverage_conditions):
            for site in conditions["site"]:
                grouped.setdefault(
                    str(site),
                    {"tumors": 0, "persons": None if multiple_values else 0, **dict.fromkeys(QUALITY_FIELDS, 0)},
                )

    labels = list(grouped)
    if dimension == "stage":
        total["tumors"] = sum(row["tumors"] for row in grouped.values())
        total["persons"] = _summary(release, {**conditions, "stage": list(grouped)})["persons"]
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
        rates_available = dimension != "stage" and not (cohort == "all" and (dimension == "site" or conditions.get("site")))
        if not rates_available:
            denominator = None
        count = counts[unit]
        value = count
        if measure == "share":
            value = count / total[unit] * 100 if count is not None and total[unit] else None
        elif measure == "rate":
            value = count / denominator * rate_scale(cohort) if count is not None and denominator else None
        elif measure == "asr":
            value = _adjusted_rate(release, conditions, dimension, label, unit, cohort) if rates_available else None
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
                    round(count / denominator * rate_scale(cohort), 2)
                    if count is not None and denominator
                    else None
                ),
                "adjusted_rate": _adjusted_rate(
                    release, conditions, dimension, label, unit, cohort
                ) if rates_available else None,
                **{field: counts[field] for field in QUALITY_FIELDS},
                "vh_percent": round(counts["vh"] / counts["tumors"] * 100, 2) if counts["tumors"] and counts["vh_known"] == counts["tumors"] else None,
                "scd_percent": round(counts["scd"] / counts["tumors"] * 100, 2) if counts["tumors"] and counts["scd_known"] == counts["tumors"] else None,
                "value": round(value, 2) if value is not None else None,
            }
        )

    if dimension not in {"age_group", "period"}:
        output.sort(key=lambda row: row["value"] or 0, reverse=True)
    return output, total


def _grouped_sites(params, release):
    params = _expanded_site_filters(params, release)
    leaves, total = results({**params, "dimension": "site", "metric": "count"}, release)
    grouped = {}
    for row in leaves:
        group = release["site_groups"][row["label"]]
        target = grouped.setdefault(group, {"label": group, "members": [], "tumors": 0, "persons": None, "population": row["population"], **dict.fromkeys(QUALITY_FIELDS, 0)})
        target["members"].append(row["label"])
        target["tumors"] += row["tumors"]
        for field in QUALITY_FIELDS:
            target[field] += row[field]
    cohort = params.get("cohort", "all")
    conditions = {field: _values(params[key]) for key, field in FILTER_FIELDS.items() if _values(params.get(key))}
    if cohort != "all":
        conditions["age_group"] = conditions.get("age_group", COHORT_AGES[cohort])
    for row in grouped.values():
        row["persons"] = _summary(release, {**conditions, "site": row["members"]})["persons"]
        unit = params.get("unit", "tumors")
        count = row[unit]
        row["relative_frequency"] = round(count / total[unit] * 100, 2) if count is not None and total[unit] else None
        row["crude_rate"] = round(count / row["population"] * rate_scale(cohort), 2) if count is not None and row["population"] else None
        row["adjusted_rate"] = _adjusted_rate(release, conditions, "site", row["members"], unit, cohort) if cohort != "all" else None
        row["vh_percent"] = round(row["vh"] / row["tumors"] * 100, 2) if row["tumors"] and row["vh_known"] == row["tumors"] else None
        row["scd_percent"] = round(row["scd"] / row["tumors"] * 100, 2) if row["tumors"] and row["scd_known"] == row["tumors"] else None
        row["value"] = {"count": count, "share": row["relative_frequency"], "rate": row["crude_rate"], "asr": row["adjusted_rate"]}[params.get("metric", "count")]
        del row["members"]
    return sorted(grouped.values(), key=lambda row: row["value"] or 0, reverse=True), total
