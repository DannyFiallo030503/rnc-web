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
from .forms import UploadForm
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
    params = {
        k: request.GET.get(k, "") if request.GET.get(k, "") in opts else ""
        for k, opts in options.items()
    }
    for key, allowed, default in [
        ("dimension", DIMENSIONS, "site"),
        ("unit", {"tumors": 1, "persons": 1}, "tumors"),
        ("metric", METRICS, "count"),
        ("chart", CHARTS, "bar"),
    ]:
        params[key] = request.GET.get(key, default)
        if params[key] not in allowed:
            params[key] = default
    errors = []
    if params["chart"] == "line" and params["dimension"] != "period":
        errors.append("Las líneas requieren la dimensión período.")
    if params["metric"] == "asr" and (
        params["age"] or params["dimension"] == "age_group"
    ):
        errors.append("El ajuste por edad requiere todos los grupos de edad.")
    if params["chart"] in {"grouped", "stacked", "percent"} and (
        params["sex"] or params["dimension"] == "sex"
    ):
        errors.append("La comparación por sexo requiere ambos sexos y otra dimensión.")
    if params["chart"] in {"stacked", "percent"} and params["metric"] != "count":
        errors.append(
            "Las barras apiladas requieren frecuencias absolutas; no se suman tasas ni porcentajes."
        )
    if params["chart"] in {"pie", "doughnut"} and (
        params["metric"] not in {"count", "share"}
        or (params["unit"] == "persons" and params["dimension"] != "sex")
    ):
        errors.append(
            "La composición requiere conteos o porcentajes de categorías excluyentes; una persona puede aparecer en varias categorías."
        )
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
    filter_labels = {
        "year": "Período",
        "territory": "Territorio",
        "sex": "Sexo",
        "age": "Edad",
        "site": "Localización",
    }
    filter_note = " · ".join(
        f"{filter_labels[k]}: {v}" for k, v in params.items() if v and k in options
    )
    payload = {
        "labels": [r["label"] for r in table],
        "datasets": datasets,
        "type": params["chart"],
        "title": DIMENSIONS[params["dimension"]],
        "note": f"Datos sintéticos · {delivery.title if delivery else ''} · Versión {delivery.pk if delivery else ''} · {filter_note}",
        "metric": METRICS[params["metric"]],
        "unit": ("Personas distintas" if params["unit"] == "persons" else "Tumores"),
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
            response["Cache-Control"] = "no-store"
            return response
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
                    return response
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
        return response
    return render(
        request,
        "public_site/explorer.html",
        {
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


@require("operate_deliveries")
def administration(request):
    form = UploadForm(request.POST or None, request.FILES or None)
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
                None,
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
        },
    )


@require_POST
@require("publish_deliveries")
def delivery_action(request, pk):
    get_object_or_404(Delivery, pk=pk)
    reason = request.POST.get("reason", "").strip()
    if not 10 <= len(reason) <= 250:
        messages.error(request, "Indique un motivo de entre 10 y 250 caracteres.")
    else:
        try:
            transition(pk, request.POST.get("action"), request.user, reason)
            messages.success(
                request, "Estado actualizado. El portal público ya refleja este cambio."
            )
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("public_site:delivery", pk=pk)


@require("operate_deliveries")
def sample(request):
    """A complete synthetic update, ready to exercise the upload/release flow."""
    import csv
    import io
    import uuid
    from .services import HEADER

    active = current_delivery()
    path = (
        (private_root() / active.storage_key).with_suffix(".csv")
        if active
        else private_root() / "ejemplo_sintetico.csv"
    )
    if not path.exists():
        return HttpResponse(
            "Ejecute seed_demo para generar el ejemplo local.", status=404
        )
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) >= 60000:
        return HttpResponse(
            "El ejemplo ya alcanzó el límite de filas del entorno local.", status=400
        )
    latest = max(r["period"] for r in rows)
    source = next(
        (r for r in rows if r["period"] == latest and r["age_group"] == "45-49"),
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
