import json
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.cache import cache
import hashlib
import threading

GRAPH_LOCK = threading.Lock()
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .access import require, can
from .forms import UploadForm, DecisionForm, ExplorerForm
from .exports import export_result
from .models import Delivery, AuditEvent
from .services import (
    current_delivery,
    published_records,
    delivery_records,
    ingest,
    transition,
    private_root,
)
from .statistics import results, DIMENSIONS, summary
from .chart_context import describe_query

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
    """Keep detailed query URLs out of browser caches and referrer headers."""
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def home(request):
    delivery = current_delivery()
    rows = delivery_records(delivery.storage_key) if delivery else []
    latest = max((r["period"] for r in rows), default=None)
    params = {
        "year": str(latest),
        "dimension": "site",
        "unit": "tumors",
        "metric": "count",
    }
    table, total = results(params, rows) if rows else ([], {})
    return render(
        request,
        "public_site/home.html",
        {
            "delivery": delivery,
            "latest": latest,
            "summary": total,
            "territories": len({r["territory"] for r in rows}),
            "top": table[:6],
            "chart_payload": {
                "labels": [r["label"] for r in table[:6]],
                "datasets": [
                    {"label": "Tumores", "data": [r["value"] for r in table[:6]]}
                ],
                "type": "bar",
                "title": "Localizaciones más frecuentes",
                "note": f"Datos sintéticos · {latest}",
            },
        },
    )


def explorer(request):
    delivery = current_delivery()
    rows = delivery_records(delivery.storage_key) if delivery else []
    options = {
        k: sorted({str(r[f]) for r in rows})
        for k, f in [
            ("year", "period"),
            ("territory", "territory"),
            ("sex", "sex"),
            ("age", "age_group"),
            ("site", "site"),
        ]
    }
    from .services import WEIGHTS

    options["age"] = [a for a in WEIGHTS if a in options["age"]]
    query = request.GET.copy()
    if not delivery:
        query.clear()
    defaults = {
        "dimension": "site",
        "unit": "tumors",
        "metric": "count",
        "chart": "bar",
    }
    for key, value in defaults.items():
        if key not in query:
            query[key] = value
    form = ExplorerForm(
        query, options=options, dimensions=DIMENSIONS, charts=CHARTS, metrics=METRICS
    )
    valid = form.is_valid()
    params = {key: form.cleaned_data.get(key, "") for key in options}
    params.update(
        {key: form.cleaned_data.get(key, value) for key, value in defaults.items()}
    )
    errors = [str(e) for values in form.errors.values() for e in values]
    table, total = results(params, rows) if rows and not errors else ([], summary([]))
    if params["chart"] in {"pie", "doughnut"} and len(table) > 8:
        errors.append(
            "Seleccione una dimensión con hasta ocho categorías para circular o anillo."
        )
    if (
        params["chart"] in {"pie", "doughnut"}
        and table
        and not any(r["value"] for r in table)
    ):
        errors.append("No hay valores positivos para representar una composición.")
    if any(r["value"] is None for r in table):
        errors.append(
            "No hay cobertura de población completa para el ajuste seleccionado."
        )
    for error in errors:
        if not any(error in list(values) for values in form.errors.values()):
            form.add_error("metric" if "población" in error else "chart", error)
    datasets = [
        {"label": METRICS[params["metric"]], "data": [r["value"] for r in table]}
    ]
    if params["chart"] in {"grouped", "stacked", "percent"} and not errors:
        datasets = []
        for sex in ["Mujeres", "Hombres"]:
            items, _ = results({**params, "sex": sex}, rows)
            by_label = {r["label"]: r["value"] for r in items}
            datasets.append(
                {"label": sex, "data": [by_label.get(r["label"], 0) for r in table]}
            )
        if params["chart"] == "percent":
            for i in range(len(table)):
                base = sum(d["data"][i] for d in datasets)
                for d in datasets:
                    d["data"][i] = round(d["data"][i] / base * 100, 2) if base else 0
    context = describe_query(
        params, options, DIMENSIONS, CHARTS, METRICS,
        {"tumors": "Tumores", "persons": "Personas distintas"},
    )
    filter_note = context["filter_summary"]
    payload = {
        "labels": [r["label"] for r in table],
        "datasets": datasets,
        "type": params["chart"],
        "title": DIMENSIONS[params["dimension"]],
        "note": f"Datos sintéticos · {delivery.title if delivery else ''} · Versión {delivery.pk if delivery else ''}",
        "metric": METRICS[params["metric"]],
        "unit": ("Personas distintas" if params["unit"] == "persons" else "Tumores"),
        **context,
    }
    if params["chart"] == "percent":
        payload["metric"] = "Distribución por sexo (%)"
    if len(datasets) > 1:
        for index, row in enumerate(table):
            row["series"] = [
                {"label": d["label"], "value": d["data"][index]} for d in datasets
            ]
    output_format = request.GET.get("format")
    if output_format and not errors and table:
        cache_key = (
            "export:"
            + hashlib.sha256(
                (
                    str(delivery.pk)
                    + json.dumps(params, sort_keys=True)
                    + output_format
                ).encode()
            ).hexdigest()
        )
        cached = cache.get(cache_key)
        if cached:
            response = HttpResponse(cached[0], content_type=cached[1])
            response["Content-Disposition"] = cached[2]
            return _query_response(response)
        if output_format in {"png", "svg", "pdf"}:
            key = (
                "render-limit:"
                + hashlib.sha256(
                    request.META.get("REMOTE_ADDR", "").encode()
                ).hexdigest()
            )
            if not cache.add(key, 1, 60):
                try:
                    count = cache.incr(key)
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
                (
                    response.content,
                    response["Content-Type"],
                    response["Content-Disposition"],
                ),
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
                "delivery": delivery,
                "filter_note": filter_note,
            },
        )
    )


@require("operate_deliveries")
def administration(request):
    form = UploadForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        try:
            delivery = ingest(
                form.cleaned_data["file"], form.cleaned_data["title"], request.user
            )
            messages.success(
                request,
                "Archivo validado y registrado. Revise el corte antes de publicarlo.",
            )
            return redirect("public_site:delivery", pk=delivery.pk)
        except (ValueError, OverflowError) as exc:
            form.add_error(
                "file",
                (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Valor numérico fuera de rango."
                ),
            )
    deliveries = Delivery.objects.all()
    return render(
        request,
        "public_site/administration.html",
        {
            "form": form,
            "page": Paginator(deliveries, 10).get_page(request.GET.get("page")),
            "delivery_count": deliveries.count(),
            "published": current_delivery(),
            "events": AuditEvent.objects.all()[:12],
        },
    )


@require("operate_deliveries")
def delivery(request, pk):
    obj = get_object_or_404(Delivery, pk=pk)
    obj.report.setdefault("received_rows", obj.row_count)
    obj.report.setdefault("accepted_rows", obj.row_count)
    obj.report.setdefault("rejected_rows", 0)
    return render(
        request,
        "public_site/delivery.html",
        {
            "delivery": obj,
            "may_publish": can(request.user, "publish_deliveries"),
            "events": AuditEvent.objects.filter(target=str(pk)),
            "decision_form": DecisionForm(
                initial={"action": "revoke" if obj.status == "published" else "publish"}
            ),
        },
    )


@require_POST
@require("publish_deliveries")
def delivery_action(request, pk):
    obj = get_object_or_404(Delivery, pk=pk)
    form = DecisionForm(request.POST)
    if form.is_valid():
        try:
            transition(
                pk,
                form.cleaned_data["action"],
                request.user,
                form.cleaned_data["reason"],
            )
            messages.success(
                request, "Estado actualizado. El portal público ya refleja este cambio."
            )
            return redirect("public_site:delivery", pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(
        request,
        "public_site/delivery.html",
        {
            "delivery": obj,
            "may_publish": True,
            "events": AuditEvent.objects.filter(target=str(pk)),
            "decision_form": form,
        },
        status=400,
    )


@require("operate_deliveries")
def sample(request):
    """A complete synthetic update, ready to exercise the upload/release flow."""
    import csv
    import io
    import uuid
    from .services import HEADER

    active = current_delivery()
    if active:
        rows = delivery_records(active.storage_key)
    else:
        path = private_root() / "ejemplo_sintetico.csv"
        if not path.exists():
            return HttpResponse(
                "Ejecute seed_demo para generar el ejemplo local.", status=404
            )
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
    rows = [{key: row[key] for key in HEADER} for row in rows]
    if len(rows) >= 60000:
        return HttpResponse(
            "El ejemplo ya alcanzó el límite de filas del entorno local.", status=400
        )
    latest = max(r["period"] for r in rows)
    from analytics.catalogs import id_for

    source = next(
        (
            r for r in rows
            if r["period"] == latest
            and r["age_group_id"] == id_for("age_group_id", "45-49")
        ),
        rows[-1],
    )
    additional = {**source, "tumor_id": "SYN-T-" + uuid.uuid4().hex}
    rows.append(additional)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="actualizacion_sintetica.csv"'
    )
    response["Cache-Control"] = "no-store"
    return response
