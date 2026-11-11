"""Human-readable query context shared by private and public explorers."""

from django.utils.translation import gettext_lazy as _


FILTER_LABELS = {
    "year": _("Año de incidencia"),
    "territory": _("Provincia de residencia"),
    "municipality": _("Municipio de residencia"),
    "sex": _("Sexo"),
    "age": _("Edad"),
    "site": _("Grupo de localización"),
}


def describe_query(
    params,
    options,
    dimensions,
    charts,
    metrics,
    unit_labels,
    territory_default_label=_("Todas las provincias"),
):
    filters = []
    for key, label in FILTER_LABELS.items():
        selected = params.get(key) or []
        if not isinstance(selected, (list, tuple, set)):
            selected = [selected]
        if selected:
            option_labels = {}
            for option in options.get(key, []):
                if isinstance(option, (tuple, list)) and len(option) == 2:
                    option_labels[str(option[0])] = str(_(str(option[1])))
                else:
                    option_labels[str(option)] = str(_(str(option)))
            value = ", ".join(option_labels.get(str(item), str(item)) for item in selected)
        elif key == "territory":
            value = territory_default_label
        elif key == "municipality":
            value = _("Todos los municipios") if options.get(key) else _("No disponible en este corte")
        elif key == "year" and options.get(key):
            years = sorted(str(year) for year in options[key])
            value = _("Todos (%(first)s–%(last)s)") % {"first": years[0], "last": years[-1]} if len(years) > 1 else (years[0] if years else _("Todos"))
        else:
            value = _("Todos")
        filters.append({"key": key, "label": label, "value": value})

    unit = unit_labels[params["unit"]]
    metric = metrics[params["metric"]]
    axis_unit = (
        _("Porcentaje (%)")
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
