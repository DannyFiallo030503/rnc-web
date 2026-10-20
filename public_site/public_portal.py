"""Public views backed only by the versioned aggregate release artifact."""

import hashlib
import json
import threading

from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render

from .aggregate_release import current_public_release
from .aggregate_statistics import DIMENSIONS, WEIGHTS, results
from .exports import export_result
from .public_forms import ExplorerForm
from .chart_context import describe_query

GRAPH_LOCK = threading.Lock()
CHARTS = {
    "bar": "Barras horizontales",
    "column": "Columnas",
    "line": "Líneas",
    "grouped": "Barras agrupadas por sexo",
    "stacked": "Barras apiladas por sexo",
    "percent": "Barras porcentuales por sexo",
    "pie": "Circular",
    "doughnut": "Anillo",
}
METRICS = {
    "count": "Frecuencia absoluta",
    "share": "Frecuencia relativa (%)",
    "rate": "Tasa cruda / específica por 100 000",
    "asr": "Tasa ajustada Segi–Doll por 100 000",
}


def _query_response(response):
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def home(request):
    release = current_public_release()
    years = release["options"]["period"] if release else []
    latest = max(years, default=None)
    params = {
        "year": str(latest or ""),
        "dimension": "site",
        "unit": "tumors",
        "metric": "count",
    }
    table, total = results(params, release) if release else ([], {})
    return render(
        request,
        "public_site/home.html",
        {
            "delivery": release,
            "latest": latest,
            "summary": total,
            "territories": len(release["options"]["territory"]) if release else 0,
            "top": table[:6],
            "chart_payload": {
                "labels": [row["label"] for row in table[:6]],
                "datasets": [
                    {"label": "Tumores", "data": [row["value"] for row in table[:6]]}
                ],
                "type": "bar",
                "title": "Localizaciones más frecuentes",
                "note": f"Datos sintéticos · {latest}" if latest else "",
            },
        },
    )


def explorer(request):
    release = current_public_release()
    options = (
        {
            "year": release["options"]["period"],
            "territory": release["options"]["territory"],
            "sex": release["options"]["sex"],
            "age": [age for age in WEIGHTS if age in release["options"]["age_group"]],
            "site": release["options"]["site"],
        }
        if release
        else {key: [] for key in ("year", "territory", "sex", "age", "site")}
    )
    query = request.GET.copy()
    if not release:
        query.clear()
    defaults = {"dimension": "site", "unit": "tumors", "metric": "count", "chart": "bar"}
    for key, value in defaults.items():
        if key not in query:
            query[key] = value
    form = ExplorerForm(
        query, options=options, dimensions=DIMENSIONS, charts=CHARTS, metrics=METRICS
    )
    form.is_valid()
    params = {key: form.cleaned_data.get(key, "") for key in options}
    params.update({key: form.cleaned_data.get(key, value) for key, value in defaults.items()})
    errors = [str(error) for values in form.errors.values() for error in values]
    table, total = results(params, release) if release and not errors else ([], {"tumors": 0, "persons": 0, "population": 0})
    if params["chart"] in {"pie", "doughnut"} and len(table) > 8:
        errors.append("Seleccione una dimensión con hasta ocho categorías para circular o anillo.")
    if params["chart"] in {"pie", "doughnut"} and table and not any(row["value"] for row in table):
        errors.append("No hay valores positivos para representar una composición.")
    if any(row["value"] is None for row in table):
        errors.append("No hay cobertura de población completa para el ajuste seleccionado.")
    for error in errors:
        if not any(error in list(values) for values in form.errors.values()):
            form.add_error("metric" if "población" in error else "chart", error)

    datasets = [
        {"label": METRICS[params["metric"]], "data": [row["value"] for row in table]}
    ]
    if params["chart"] in {"grouped", "stacked", "percent"} and not errors:
        datasets = []
        for sex in ["Mujeres", "Hombres"]:
            items, _ = results({**params, "sex": sex}, release)
            by_label = {row["label"]: row["value"] for row in items}
            datasets.append(
                {"label": sex, "data": [by_label.get(row["label"], 0) for row in table]}
            )
        if params["chart"] == "percent":
            for index in range(len(table)):
                base = sum(dataset["data"][index] for dataset in datasets)
                for dataset in datasets:
                    dataset["data"][index] = round(dataset["data"][index] / base * 100, 2) if base else 0

    context = describe_query(
        params, options, DIMENSIONS, CHARTS, METRICS,
        {"tumors": "Tumores", "persons": "Personas distintas"},
    )
    filter_note = context["filter_summary"]
    payload = {
        "labels": [row["label"] for row in table],
        "datasets": datasets,
        "type": params["chart"],
        "title": DIMENSIONS[params["dimension"]],
        "note": (
            f"Datos sintéticos · {release['title']} · Versión {release['release_id']}"
            if release
            else ""
        ),
        "metric": METRICS[params["metric"]],
        "unit": "Personas distintas" if params["unit"] == "persons" else "Tumores",
        **context,
    }
    if params["chart"] == "percent":
        payload["metric"] = "Distribución por sexo (%)"
    if len(datasets) > 1:
        for index, row in enumerate(table):
            row["series"] = [
                {"label": dataset["label"], "value": dataset["data"][index]}
                for dataset in datasets
            ]

    output_format = request.GET.get("format")
    if output_format and release and not errors and table:
        cache_key = "public-export:" + hashlib.sha256(
            (release["release_id"] + json.dumps(params, sort_keys=True) + output_format).encode()
        ).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            response = HttpResponse(cached[0], content_type=cached[1])
            response["Content-Disposition"] = cached[2]
            return _query_response(response)
        if output_format in {"png", "svg", "pdf"}:
            limit_key = "render-limit:" + hashlib.sha256(
                request.META.get("REMOTE_ADDR", "").encode()
            ).hexdigest()
            if not cache.add(limit_key, 1, 60):
                try:
                    count = cache.incr(limit_key)
                except ValueError:
                    count = 1
                if count > 20:
                    response = HttpResponse(
                        "Se alcanzó el límite temporal de exportaciones. Espere un minuto.",
                        status=429,
                    )
                    response["Retry-After"] = "60"
                    return _query_response(response)
            with GRAPH_LOCK:
                response = export_result(output_format, table, payload, params)
        else:
            response = export_result(output_format, table, payload, params)
        if response.status_code == 200:
            cache.set(
                cache_key,
                (response.content, response["Content-Type"], response["Content-Disposition"]),
                900,
            )
        return _query_response(response)

    return _query_response(
        render(
            request,
            "public_site/explorer.html",
            {
                "form": form,
                "filters": params,
                "options": options,
                "dimensions": DIMENSIONS,
                "charts": CHARTS,
                "metrics": METRICS,
                "errors": errors,
                "table": table if not errors else [],
                "summary": total,
                "chart_payload": payload,
                "delivery": release,
                "filter_note": filter_note,
            },
        )
    )


def not_found(request, exception=None, **kwargs):
    return render(request, "public_site/public_not_found.html", status=404)
