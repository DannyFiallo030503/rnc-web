"""Public views backed only by the versioned aggregate release artifact."""

import hashlib
import json
import threading
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.contrib.staticfiles import finders
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.utils.translation import get_language, gettext_lazy as _

from .labels import category_label
from .aggregate_release import current_public_release
from .aggregate_statistics import DIMENSIONS, WEIGHTS, COHORT_AGES, results
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
from .chart_availability import availability
from .province_map import map_context, NAMES as MAP_PROVINCES

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
    "trend": _("Tendencia temporal"),
    "curve": _("Curva por edad"),
    "map": _("Mapa provincial de Cuba"),
    "table": _("Tabla de datos"),
    "grouped": _("Barras agrupadas por sexo"),
    "stacked": _("Barras apiladas por sexo"),
    "percent": _("Barras porcentuales por sexo"),
    "pie": _("Circular"),
    "doughnut": _("Anillo"),
}
CHART_FILTER_REQUIREMENTS = {
    "line": ["year"],
    "trend": ["year"],
    "curve": ["age"],
    "map": ["territory"],
    "grouped": ["sex"],
    "stacked": ["sex"],
    "percent": ["sex"],
    "scatter": ["dimension"],
    "strip": ["dimension"],
    "swarm": ["dimension"],
}
DIMENSION_FILTER_FIELDS = {
    "site_group": "site",
    "municipality": "municipality",
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
            code = str(cell.get("territory", ""))
            by_period[period].add(TERRITORIES.get(code, {}).get("name", code))
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
    """Keep old bookmarks on the single statistical explorer."""
    from django.shortcuts import redirect
    return redirect("public_site:synthetic_explorer")


def connection_status(request):
    try:
        pointer = json.loads((Path(settings.PUBLIC_RELEASE_ROOT) / "current.json").read_text())
    except (OSError, ValueError):
        pointer = {}
    return _query_response(HttpResponse(json.dumps({"online": True, "publication": pointer.get("sha256", "") + "-i18n-v1" if pointer.get("release_id") else None}), content_type="application/json"))


def offline_package(request):
    """Offer the same real, versioned aggregate used by the online service."""
    release = current_public_release()
    if not release or release.get("synthetic") is not False or release.get("schema_version") != 3:
        return _query_response(HttpResponseNotFound(_("No hay paquete offline disponible.")))
    payload = {
        key: release[key]
        for key in (
            "schema_version",
            "synthetic",
            "publication_approved",
            "provenance",
            "person_identity_verified",
            "persons_disjoint",
            "population_fields",
            "population_cube",
            "option_labels",
            "option_descriptions",
            "site_groups",
            "site_group_labels",
            "site_systems",
            "rate_reference",
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
        "unified": True,
        "dimensions": list(DIMENSIONS),
        "charts": [key for key in CHARTS if availability().get(key, True) and (key not in {"line", "trend"} or len(payload["options"]["period"]) > 1)],
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
    if payload.get("persons_disjoint"):
        base_fields = [field for field in payload["fields"] if field not in {"morphology", "stage"}]
        keys = {",".join(base_fields), ",".join([*base_fields, "morphology"]), ",".join([*base_fields, "stage"])}
        payload["cube"] = {key: cells for key, cells in payload["cube"].items() if key in keys}
        population_key = ",".join(payload["population_fields"])
        payload["population_cube"] = {population_key: payload["population_cube"][population_key]}
    geometry = map_context([])
    payload["map_geometry"] = {"viewbox": geometry["viewbox"], "regions": [{"name": region["name"], "path": region["path"]} for region in geometry["regions"]]}
    try:
        payload["publication_fingerprint"] = json.loads((Path(settings.PUBLIC_RELEASE_ROOT) / "current.json").read_text()).get("sha256", "") + "-i18n-v1"
    except (OSError, ValueError):
        payload["publication_fingerprint"] = None
    from django.utils.translation import override
    with override("es"):
        payload["display_labels"] = {key: {name: str(label) for name, label in options.items()} for key, options in {"dimensions": DIMENSIONS, "charts": CHARTS, "metrics": METRICS}.items()}
    response = HttpResponse(
            json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":")),
        content_type="application/json; charset=utf-8",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'attachment; filename="rnc-agregados-2022.json"'
    return _query_response(response)


def service_worker(request):
    """Serve the public worker only when its deployment profile enables it."""
    from django.conf import settings

    if getattr(settings, "DEPLOYMENT_ROLE", "combined") != "public" and not getattr(settings, "PUBLIC_PWA_ENABLED", False):
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
    flags = availability()
    charts = {key: label for key, label in CHARTS.items() if flags.get(key, True)}
    release = current_public_release()
    national_coverage = _has_national_territory_coverage(release) if release else False
    if not release or not release.get("person_identity_verified"):
        charts.pop("scatter", None)
    cohort = request.GET.get("cohort", "all")
    allowed_ages = COHORT_AGES.get(cohort, COHORT_AGES["all"])
    def labeled(field, values):
        labels = release.get("option_labels", {}).get(field, {}) if release else {}
        return [(value, category_label(labels.get(str(value), value))) for value in values]
    geographic_scope = _geographic_scope_label(national_coverage)
    options = (
        {
            "year": release["options"]["period"],
            "territory": labeled("territory", release["options"]["territory"]),
            "municipality": labeled("municipality", release.get("options", {}).get("municipality", [])),
            "sex": release["options"]["sex"],
            "age": [age for age in allowed_ages if age in release["options"]["age_group"]],
            "site": labeled("site", [site for site in release["options"]["site"] if cohort == "all" or release.get("site_systems", {}).get(site) == ("C10" if cohort == "adult" else "CICN")]),
        }
        if release
        else {key: [] for key in ("year", "territory", "municipality", "sex", "age", "site")}
    )
    municipality_available = bool(
        release
        and "municipality" in release.get("fields", [])
        and options["municipality"]
    )
    selected_provinces = [value for value in request.GET.getlist("territory") if value]
    if selected_provinces:
        options["municipality"] = [(code, label) for code, label in options["municipality"] if str(code)[:2] in selected_provinces]
    if cohort == "adult":
        options["site"].insert(0, ("DOCX:C00-97", _("Total C00–97 · diccionario RNC")))
        options["site"].insert(1, ("ANUARIO:C00-96", _("Total C00–96 · Anuario 2022")))
    query = request.GET.copy()
    if not release:
        query.clear()
    else:
        # Older links used single-select filters and commonly retained empty
        # query values (for example, ?year=&sex=). Empty means “all” here.
        for key in options:
            if key in query:
                query.setlist(key, [value for value in query.getlist(key) if value])
    defaults = {"dimension": "site", "unit": "tumors", "metric": "count", "chart": "bar", "cohort": "all"}
    for key, value in defaults.items():
        if key not in query:
            query[key] = value
    metrics = dict(METRICS)
    if cohort != "all":
        metrics["asr"] = _("Tasa ajustada truncada Segi–Doll (%(ages)s)") % {"ages": "20+" if cohort == "adult" else "0–19"}
    scale_label = "1 000 000" if cohort == "child" else "100 000"
    metrics["rate"] = _("Tasa cruda / específica por %(scale)s") % {"scale": scale_label}
    metrics["asr"] = str(metrics["asr"]) + " · " + str(_("por %(scale)s") % {"scale": scale_label}) if cohort != "all" else metrics["asr"]
    form = ExplorerForm(
        query,
        options=options,
        dimensions=DIMENSIONS,
        charts=charts,
        metrics=metrics,
        national_coverage=national_coverage,
        municipality_available=municipality_available,
        person_identity_verified=bool(release and release.get("person_identity_verified")),
        persons_disjoint=bool(release and release.get("persons_disjoint")),
    )
    form.is_valid()
    if query.get("chart") in flags and not flags[query["chart"]]:
        form.add_error("chart", _("Esta visualización está desactivada por administración."))
    params = {key: form.cleaned_data.get(key, "") for key in options}
    params.update({key: form.cleaned_data.get(key, value) for key, value in defaults.items()})
    chart_requirements = _chart_requirements()
    chart_compatibility = _chart_compatibility(DIMENSIONS, metrics)
    required_chart_filters = _required_chart_filters(
        params["chart"], params["dimension"], params["metric"]
    )
    multi_value_filters = any(len(params.get(key) or []) > 1 for key in options)
    errors = [str(error) for values in form.errors.values() for error in values]
    table, total = results(params, release) if release and not errors else ([], {"tumors": 0, "persons": None, "population": 0})
    if params["chart"] == "ranking":
        table.sort(key=lambda row: row["value"] if row["value"] is not None else float("-inf"), reverse=True)
        for position, row in enumerate(table, start=1):
            row["rank"] = position
    for row in table:
        labels = release.get("site_group_labels", {}) if params["dimension"] == "site_group" else release.get("option_labels", {}).get(params["dimension"], {})
        row["display_label"] = category_label(labels.get(str(row["label"]), row["label"]))
        if params["dimension"] == "site":
            row["description"] = str(_(
                "Agrupación del diccionario suministrado: %(category)s."
            )) % {"category": row["display_label"]}
        elif params["dimension"] == "territory":
            row["description"] = str(_(
                "Código de provincia documentado en el Manual RNC VII, Anexo 1."
            ))
        else:
            row["description"] = release.get("option_descriptions", {}).get(params["dimension"], {}).get(str(row["label"]), "")
    if params["chart"] == "map" and any(row["display_label"] not in MAP_PROVINCES.values() for row in table):
        errors.append(_("La cartografía no permite identificar todas las provincias de esta selección."))
    if params["chart"] in {"pie", "doughnut"} and table and not any(row["value"] for row in table):
        errors.append(_("No hay valores positivos para representar una composición."))
    if params["chart"] in {"grouped", "stacked", "percent"} and not {"Mujeres", "Hombres"}.issubset(set(options["sex"])):
        errors.append(_("La comparación por sexo requiere datos disponibles de mujeres y hombres."))
    if params["chart"] in {"line", "trend", "curve", "scatter", "strip", "swarm"} and table and len(table) < 2:
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
            "label": _("Tumores y personas distintas"),
            "data": [
                {"x": row["tumors"], "y": row["persons"], "category": row["display_label"]}
                for row in table
            ],
        }]
    elif params["chart"] in {"strip", "swarm"}:
        datasets = [{
            "label": metrics[params["metric"]],
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
            {"label": metrics[params["metric"]], "data": [row["value"] for row in table]}
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
        params, options, DIMENSIONS, CHARTS, metrics,
        {"tumors": _("Tumores"), "persons": _("Personas distintas")},
        territory_default_label=geographic_scope,
    )
    filter_note = context["filter_summary"]
    payload = {
        "labels": [row["display_label"] for row in table],
        "datasets": datasets,
        "type": params["chart"],
        "title": DIMENSIONS[params["dimension"]],
        "note": (
            _("%(title)s · Versión %(release)s") % {"title": release["title"], "release": release["release_id"]}
            if release
            else ""
        ),
        "metric": metrics[params["metric"]],
        "adjusted_rate_label": metrics["asr"],
        "rate_scale_label": scale_label,
        "cohort": params["cohort"],
        "person_identity_verified": bool(release and release.get("person_identity_verified")),
        "persons_disjoint": bool(release and release.get("persons_disjoint")),
        "provenance": release.get("provenance", {}) if release else {},
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

    if params["chart"] in {"pie", "doughnut"} and len(table) > 8:
        order = sorted(range(len(table)), key=lambda index: datasets[0]["data"][index], reverse=True)
        payload["labels"] = [table[index]["display_label"] for index in order[:7]] + [str(_("Otras categorías"))]
        payload["datasets"] = [{**dataset, "data": [dataset["data"][index] for index in order[:7]] + [sum(dataset["data"][index] for index in order[7:])]} for dataset in datasets]
        payload["display_note"] = _("El gráfico muestra las siete categorías mayores y agrupa el resto en Otras categorías. La tabla conserva todas las categorías.")

    output_format = request.GET.get("format")
    if output_format and release and not errors and table:
        cache_key = "public-export:" + hashlib.sha256(
            json.dumps(
                {
                    "release": release["release_id"],
                    "published_at": str(release.get("published_at")),
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
                "charts": charts,
                "province_map": map_context(table) if params["chart"] == "map" and not errors else None,
                "chart_requirements": chart_requirements,
                "chart_compatibility": chart_compatibility,
                "required_chart_filters": required_chart_filters,
                "metrics": metrics,
                "errors": errors,
                "table": table if not errors else [],
                "table_page": Paginator(table if not errors else [], 10).get_page(request.GET.get("page")),
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
