"""Administration of optional public visualizations."""

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from .access import require
from .chart_availability import availability, save_availability
from .models import AuditEvent
from .validation import AccessibleForm


class ChartAvailabilityForm(AccessibleForm, forms.Form):
    trend = forms.BooleanField(label=_("Gráfico de tendencia"), required=False)
    map = forms.BooleanField(label=_("Mapa provincial de Cuba"), required=False)


@require("publish_deliveries")
@require_http_methods(["GET", "POST"])
def visualizations(request):
    form = ChartAvailabilityForm(request.POST if request.method == "POST" else None, initial=availability())
    if request.method == "POST" and form.is_valid():
        save_availability(form.cleaned_data)
        AuditEvent.objects.create(
            actor=request.user,
            action="configure_visualizations",
            target="public_visualizations",
            reason="; ".join(f"{key}={int(value)}" for key, value in form.cleaned_data.items()),
        )
        messages.success(request, _("Disponibilidad de visualizaciones actualizada."))
        return redirect("public_site:visualizations")
    return render(request, "public_site/visualizations.html", {"form": form})
