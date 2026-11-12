"""Public views backed only by the versioned aggregate release artifact."""

import hashlib
import json
import threading
from pathlib import Path

from django.core.cache import cache
from django.contrib.staticfiles import finders
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.utils.translation import get_language, gettext_lazy as _

from .aggregate_release import current_public_release
from .aggregate_statistics import DIMENSIONS, WEIGHTS, results
from .exports import export_result
from .public_forms import (
    CHART_DIMENSION_LIMITS,
    CHART_METRIC_LIMITS,
    CHART_UNIT_LIMITS,
    ExplorerForm,
)
from .chart_context import describe_query
from analytics.catalogs import TERRITORIES
from analytics.coding_nomenclators import CatalogError, load_catalog, search_concepts
from analytics.standard import AGE_STANDARD_ID, AGE_STANDARD_WEIGHTS

GRAPH_LOCK = threading.Lock()
EXPECTED_PROVINCES = frozenset(item["name"] for item in TERRITORIES.values())
CHARTS = {
    "bar": _("Barras horizontales"),
    "ranking": _("Ranking por indicador"),
    "scatter": _("Dispersión: tumores y personas por provincia/edad"),
    "strip": _("Puntos por provincia o grupo de edad"),
    "swarm": _("Distribución territorial (swarm)"),
    "column": _("Columnas"),
    "line": _("Líneas"),
    "grouped": _("Barras agrupadas por sexo"),
    "stacked": _("Barras apiladas por sexo"),
    "percent": _("Barras porcentuales por sexo"),
    "pie": _("Circular"),
    "doughnut": _("Anillo"),
}
CHART_FILTER_REQUIREMENTS = {
    "line": ["year"],
    "grouped": ["sex"],
    "stacked": ["sex"],
    "percent": ["sex"],
    "scatter": ["dimension"],
    "strip": ["dimension"],
    "swarm": ["dimension"],
}
DIMENSION_FILTER_FIELDS = {
    "period": "year",
    "territory": "territory",
    "sex": "sex",
    "age_group": "age",
    "site": "site",
}


def _chart_requirements():
    return {
        chart: {"filter_fields": CHART_FILTER_REQUIREMENTS.get(chart, [])}
        for chart in CHARTS
    }


def _chart_compatibility(dimensions, metrics):
    all_dimensions = list(dimensions)
    all_metrics = list(metrics)
    compatibility = {}
    for chart in CHARTS:
        compatibility[chart] = {
            "dimensions": list(CHART_DIMENSION_LIMITS.get(chart, all_dimensions)),
            "metrics": list(CHART_METRIC_LIMITS.get(chart, all_metrics)),
            "units": list(CHART_UNIT_LIMITS.get(chart, ("tumors", "persons"))),
        }
    return compatibility


def _required_chart_filters(chart, dimension, metric):
    fields = {
        DIMENSION_FILTER_FIELDS.get(dimension) if field == "dimension" else field
        for field in CHART_FILTER_REQUIREMENTS.get(chart, [])
    }
    fields.discard(None)
    dimension_field = DIMENSION_FILTER_FIELDS.get(dimension)
    if dimension_field:
        fields.add(dimension_field)
    if metric == "asr":
        fields.add("age")
    return sorted(fields)


def _has_national_territory_coverage(release):
    """Return true only when every published year includes all RNC territories."""
    periods = {str(period) for period in release.get("options", {}).get("period", [])}
    if not periods:
        return False
    by_period = {period: set() for period in periods}
    cells = release.get("cube", {}).get("period,territory", [])
    for cell in cells:
        period = str(cell.get("period", ""))
        if period in by_period:
            by_period[period].add(str(cell.get("territory", "")))
    return all(EXPECTED_PROVINCES.issubset(by_period[period]) for period in periods)


def _geographic_scope_label(national_coverage):
    if national_coverage:
        return _("Cuba (nacional)")
    return _("Provincias disponibles; cobertura nacional incompleta")
METRICS = {
    "count": _("Frecuencia absoluta"),
    "share": _("Frecuencia relativa (%)"),
    "rate": _("Tasa cruda / específica por 100 000"),
    "asr": _("Tasa ajustada Segi–Doll por 100 000"),
}


def _query_response(response):
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def offline_consult(request):
    """Render a data-free public shell for optional offline consultation."""
    response = render(
        request,
        "public_site/offline_consult.html",
        {"offline_mode": True},
    )
    response["Cache-Control"] = "no-store"
    return response


def offline_package(request):
    """Offer only the explicitly synthetic public aggregate package."""
    release = current_public_release()
    if not release or release.get("synthetic") is not True:
        return _query_response(HttpResponseNotFound(_("No hay paquete offline disponible.")))
    payload = {
        key: release[key]
        for key in (
            "schema_version",
            "synthetic",
            "release_id",
            "title",
            "published_at",
            "options",
            "fields",
            "standard_id",
            "standard_weights",
            "cube",
        )
        if key in release
    }
    payload.setdefault("standard_id", AGE_STANDARD_ID)
    payload.setdefault("standard_weights", AGE_STANDARD_WEIGHTS)
    if payload.get("published_at"):
        payload["published_at"] = payload["published_at"].isoformat()
    payload["query_contract"] = {
        # Send stable codes; clients localize labels with their current catalog.
        "dimensions": list(DIMENSIONS),
        "charts": list(CHARTS),
        "metrics": list(METRICS),
        "chart_dimensions": {
            key: list(value) for key, value in CHART_DIMENSION_LIMITS.items()
        },
        "chart_metrics": {
            key: list(value) for key, value in CHART_METRIC_LIMITS.items()
        },
        "chart_units": {
            key: list(value) for key, value in CHART_UNIT_LIMITS.items()
        },
    }
    response = HttpResponse(
            json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":")),
        content_type="application/json; charset=utf-8",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'attachment; filename="rnc-agregados-sinteticos.json"'
    return _query_response(response)


def service_worker(request):
    """Serve the public-origin worker; this URLconf has no admin routes."""
    from django.conf import settings

    if getattr(settings, "DEPLOYMENT_ROLE", "combined") != "public":
        return HttpResponseNotFound(_("El service worker solo está habilitado en el perfil público."))
    source = finders.find("js/service-worker.js")
    if not source:
        return HttpResponseNotFound(_("No se encontró el service worker."))
    with Path(source).open("rb") as script:
        response = HttpResponse(script.read(), content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def home(request):
    release = current_public_release()
    return render(
        request,
        "public_site/home.html",
        {
            "delivery": release,
        },
    )


def about(request):
    return render(request, "public_site/about.html")


def explorer(request):
    release = current_public_release()
    national_coverage = _has_national_territory_coverage(release) if release else False
    geographic_scope = _geographic_scope_label(national_coverage)
    options = (
        {
            "year": release["options"]["period"],
            "territory": release["options"]["territory"],
            "municipality": release.get("options", {}).get("municipality", []),
            "sex": release["options"]["sex"],
            "age": [age for age in WEIGHTS if age in release["options"]["age_group"]],
            "site": release["options"]["site"],
        }
        if release
        else {key: [] for key in ("year", "territory", "municipality", "sex", "age", "site")}
    )
    municipality_available = bool(
        release
        and "municipality" in release.get("fields", [])
        and options["municipality"]
    )
    query = request.GET.copy()
    if not release:
        query.clear()
    else:
        # Older links used single-select filters and commonly retained empty
        # query values (for example, ?year=&sex=). Empty means “all” here.
        for key in options:
            if key in query:
                query.setlist(key, [value for value in query.getlist(key) if value])
    defaults = {"dimension": "site", "unit": "tumors", "metric": "count", "chart": "bar"}
    for key, value in defaults.items():
        if key not in query:
            query[key] = value
    form = ExplorerForm(
        query,
        options=options,
        dimensions=DIMENSIONS,
        charts=CHARTS,
        metrics=METRICS,
        national_coverage=national_coverage,
        municipality_available=municipality_available,
    )
    form.is_valid()
    params = {key: form.cleaned_data.get(key, "") for key in options}
    params.update({key: form.cleaned_data.get(key, value) for key, value in defaults.items()})
    chart_requirements = _chart_requirements()
    chart_compatibility = _chart_compatibility(DIMENSIONS, METRICS)
    required_chart_filters = _required_chart_filters(
        params["chart"], params["dimension"], params["metric"]
    )
    multi_value_filters = any(len(params.get(key) or []) > 1 for key in options)
    errors = [str(error) for values in form.errors.values() for error in values]
    table, total = results(params, release) if release and not errors else ([], {"tumors": 0, "persons": 0, "population": 0})
    if params["chart"] == "ranking":
        table.sort(key=lambda row: row["value"] if row["value"] is not None else float("-inf"), reverse=True)
        for position, row in enumerate(table, start=1):
            row["rank"] = position
    for row in table:
        row["display_label"] = str(_(row["label"]))
        if params["dimension"] == "site":
            row["description"] = str(_(
                "Grupo ilustrativo sintético; no representa un código TOPO ni "
                "una equivalencia ICD-O: %(category)s."
            )) % {"category": row["display_label"]}
        elif params["dimension"] == "territory":
            row["description"] = str(_(
                "Código de provincia documentado en el Manual RNC VII, Anexo 1."
            ))
        else:
            row["description"] = ""
    if params["chart"] in {"pie", "doughnut"} and len(table) > 8:
        errors.append(_("Seleccione una dimensión con hasta ocho categorías para circular o anillo."))
    if params["chart"] in {"pie", "doughnut"} and table and not any(row["value"] for row in table):
        errors.append(_("No hay valores positivos para representar una composición."))
    if params["chart"] in {"grouped", "stacked", "percent"} and not {"Mujeres", "Hombres"}.issubset(set(options["sex"])):
        errors.append(_("La comparación por sexo requiere datos disponibles de mujeres y hombres."))
    if params["chart"] in {"line", "scatter", "strip", "swarm"} and table and len(table) < 2:
        errors.append(_("Este gráfico necesita al menos dos categorías con datos en la dimensión elegida."))
    if any(row["value"] is None for row in table):
        errors.append(_("No hay cobertura de población completa para el ajuste seleccionado."))
    for error in errors:
        if not any(error in list(values) for values in form.errors.values()):
            if "población" in error:
                error_field = "metric"
            elif "dos categorías" in error or "hasta ocho categorías" in error:
                error_field = DIMENSION_FILTER_FIELDS.get(params["dimension"], "chart")
            elif "comparación por sexo" in error:
                error_field = "sex"
            else:
                error_field = "chart"
            form.add_error(error_field, error)

    if params["chart"] == "scatter":
        datasets = [{
            "label": "Tumores y personas distintas",
            "data": [
                {"x": row["tumors"], "y": row["persons"], "category": row["display_label"]}
                for row in table
            ],
        }]
    elif params["chart"] in {"strip", "swarm"}:
        datasets = [{
            "label": METRICS[params["metric"]],
            "data": [
                {
                    "x": row["value"],
                    "y": index if params["chart"] == "strip" else index + ((index * 37) % 9 - 4) / 20,
                    "category": row["display_label"],
                }
                for index, row in enumerate(table)
                if row["value"] is not None
            ],
        }]
    else:
        datasets = [
            {"label": METRICS[params["metric"]], "data": [row["value"] for row in table]}
        ]
    if params["chart"] in {"grouped", "stacked", "percent"} and not errors:
        datasets = []
        for sex in ["Mujeres", "Hombres"]:
            items, _ignored_summary = results({**params, "sex": sex}, release)
            by_label = {row["label"]: row["value"] for row in items}
            datasets.append(
                {"label": str(_(sex)), "data": [by_label.get(row["label"], 0) for row in table]}
            )
        if params["chart"] == "percent":
            for index in range(len(table)):
                base = sum(dataset["data"][index] for dataset in datasets)
                for dataset in datasets:
                    dataset["data"][index] = round(dataset["data"][index] / base * 100, 2) if base else 0

    context = describe_query(
        params, options, DIMENSIONS, CHARTS, METRICS,
        {"tumors": "Tumores", "persons": "Personas distintas"},
        territory_default_label=geographic_scope,
    )
    filter_note = context["filter_summary"]
    payload = {
        "labels": [row["display_label"] for row in table],
        "datasets": datasets,
        "type": params["chart"],
        "title": DIMENSIONS[params["dimension"]],
        "note": (
            _("Datos sintéticos · %(title)s · Versión %(release)s") % {"title": release["title"], "release": release["release_id"]}
            if release
            else ""
        ),
        "metric": METRICS[params["metric"]],
        "unit": _("Personas distintas") if params["unit"] == "persons" else _("Tumores"),
        "label_descriptions": {
            row["display_label"]: row["description"]
            for row in table
            if row["description"]
        },
        **context,
    }
    if params["chart"] == "scatter":
        payload["metric"] = _("Tumores y personas distintas")
        payload["unit"] = _("Frecuencias absolutas")
        payload["axis_unit"] = _("Tumores (frecuencia absoluta)")
        payload["y_axis_unit"] = _("Personas distintas (frecuencia absoluta)")
    if params["chart"] == "percent":
        payload["metric"] = _("Distribución por sexo (%)")
    if len(datasets) > 1:
        for index, row in enumerate(table):
            row["series"] = [
                {"label": dataset["label"], "value": dataset["data"][index]}
                for dataset in datasets
            ]

    output_format = request.GET.get("format")
    if output_format and release and not errors and table:
        cache_key = "public-export:" + hashlib.sha256(
            json.dumps(
                {
                    "release": release["release_id"],
                    "language": get_language(),
                    "params": params,
                    "format": output_format,
                },
                sort_keys=True,
            ).encode()
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
                        _("Se alcanzó el límite temporal de exportaciones. Espere un minuto."),
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
                "chart_requirements": chart_requirements,
                "chart_compatibility": chart_compatibility,
                "required_chart_filters": required_chart_filters,
                "metrics": METRICS,
                "errors": errors,
                "table": table if not errors else [],
                "summary": total,
                "chart_payload": payload,
                "delivery": release,
                "filter_note": filter_note,
                "geographic_scope": geographic_scope,
                "multi_value_filters": multi_value_filters,
            },
        )
    )


def coding_nomenclators(request):
    error = ""
    try:
        catalog = load_catalog()
    except CatalogError as exc:
        catalog = {"concepts": [], "source": "", "version": "", "status": "invalid"}
        error = str(exc)
    concepts = search_concepts(
        catalog,
        query=request.GET.get("q", ""),
        system=request.GET.get("system", ""),
        edition=request.GET.get("edition", ""),
        axis=request.GET.get("axis", ""),
    )
    public_concepts = search_concepts(catalog)
    axis_labels = {
        "topography": _("Topografía"),
        "morphology": _("Morfología"),
        "behavior": _("Comportamiento"),
        "grade": _("Grado"),
        "stage": _("Estadio"),
        "classification": _("Grupo de clasificación"),
        "other": _("Otro"),
    }
    relationship_labels = {
        "primary": _("Código del concepto"),
        "same-concept": _("Mismo concepto"),
        "exact": _("Correspondencia exacta"),
        "broader": _("Más amplio"),
        "narrower": _("Más específico"),
        "related": _("Relacionado"),
    }
    all_codes = [code for concept in public_concepts for code in concept["codes"]]
    for concept in concepts:
        for code in concept["codes"]:
            code["axis_label"] = axis_labels[code["axis"]]
            code["relationship_label"] = relationship_labels[code["relationship"]]
            code["relationship_status_label"] = (
                _("El catálogo declara validación RNC")
                if code["relationship_status"] == "validated-rnc"
                else _("Declarado por la fuente")
            )
    return render(request, "public_site/coding_nomenclators.html", {
        "catalog": catalog,
        "concepts": concepts,
        "query": request.GET.get("q", ""),
        "systems": sorted({item["system"] for item in all_codes}),
        "editions": sorted({item["edition"] for item in all_codes}),
        "axes": sorted({item["axis"] for item in all_codes}),
        "error": error,
    })


def not_found(request, exception=None, **kwargs):
    return render(request, "public_site/public_not_found.html", status=404)
