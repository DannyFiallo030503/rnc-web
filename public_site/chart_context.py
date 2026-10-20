"""Human-readable query context shared by private and public explorers."""


FILTER_LABELS = {
    "year": "Período",
    "territory": "Territorio",
    "sex": "Sexo",
    "age": "Edad",
    "site": "Grupo de localización ilustrativo",
}


def describe_query(params, options, dimensions, charts, metrics, unit_labels):
    filters = []
    for key, label in FILTER_LABELS.items():
        selected = params.get(key)
        if selected:
            value = str(selected)
        elif key == "year" and options.get(key):
            years = sorted(str(year) for year in options[key])
            value = f"Todos ({years[0]}–{years[-1]})" if len(years) > 1 else (years[0] if years else "Todos")
        else:
            value = "Todos"
        filters.append({"label": label, "value": value})

    unit = unit_labels[params["unit"]]
    metric = metrics[params["metric"]]
    axis_unit = (
        "Porcentaje (%)"
        if params["chart"] == "percent" or params["metric"] == "share"
        else unit if params["metric"] == "count"
        else metric
    )
    return {
        "filters": filters,
        "filter_summary": " · ".join(f"{item['label']}: {item['value']}" for item in filters),
        "chart_label": charts[params["chart"]],
        "dimension_label": dimensions[params["dimension"]],
        "metric_label": metric,
        "unit_label": unit,
        "axis_unit": axis_unit,
    }
