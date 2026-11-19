from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from .access import require, can
from .forms import UploadForm, DecisionForm
from .models import Delivery, AuditEvent
from .services import ingest, transition, current_delivery


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
            if delivery.status == "rejected":
                messages.error(request, "La carga se rechazó. Revise el informe técnico.")
            else:
                messages.success(
                    request,
                    "Archivo real limpiado y guardado en almacenamiento privado. "
                    "La vista previa agregada queda limitada al personal autorizado.",
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
            "no_published_label": _("Sin corte publicado"),
            "preview_available": bool(
                settings.DEBUG and settings.RNC_REAL_PREVIEW_ENABLED
            ),
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
            "no_value_label": _("No determinado"),
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
            messages.success(request, "Publicación actualizada y registrada en el historial.")
            return redirect("public_site:delivery", pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(
        request,
        "public_site/delivery.html",
        {
            "delivery": obj,
            "no_value_label": _("No determinado"),
            "may_publish": True,
            "events": AuditEvent.objects.filter(target=str(pk)),
            "decision_form": form,
        },
        status=400,
    )
