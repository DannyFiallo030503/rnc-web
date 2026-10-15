import csv
from io import StringIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from analytics.demo import choices, load_rows, query_data
from .access import has_admin_access


class RoleLoginView(LoginView):
    template_name = "public_site/login.html"

    def get_default_redirect_url(self):
        destination = "public_site:intake_prototype" if has_admin_access(self.request.user) else "public_site:home"
        return reverse(destination)


def home(request):
    return render(request, "public_site/home.html")


def synthetic_explorer(request):
    if not settings.DEBUG:
        raise Http404

    rows = load_rows()
    options = {field: choices(rows, column) for field, column in (
        ("year", "period"), ("territory", "territory"), ("sex", "sex"),
        ("age", "age_group"), ("site", "site"),
    )}
    raw = {key: request.GET.get(key, "") for key in options}
    filters = {
        key: raw[key] if raw[key] in {str(value) for value in options[key]} else ""
        for key in options
    }
    filters["unit"] = request.GET.get("unit", "tumors")
    if filters["unit"] not in {"tumors", "persons"}:
        filters["unit"] = "tumors"
    filters["measure"] = request.GET.get("measure", "crude")
    if filters["measure"] not in {"crude", "asr"}:
        filters["measure"] = "crude"

    data = query_data(filters)
    if data:
        age_max = max((row["tumor_rate"] if filters["unit"] == "tumors" else row["person_rate"])
                      for row in data["age_rows"]) or 1
        for row in data["age_rows"]:
            rate = row["tumor_rate"] if filters["unit"] == "tumors" else row["person_rate"]
            row["bar_width"] = max(1, round(rate / age_max * 100))
        summary = data["summary"]
        data["selected_rate"] = (
            summary["person_asr"] if filters["unit"] == "persons" else summary["tumor_asr"]
        ) if filters["measure"] == "asr" else (
            summary["person_rate"] if filters["unit"] == "persons" else summary["tumor_rate"]
        )
        data["other_rate"] = (
            summary["person_rate"] if filters["unit"] == "persons" else summary["tumor_rate"]
        ) if filters["measure"] == "asr" else (
            summary["person_asr"] if filters["unit"] == "persons" else summary["tumor_asr"]
        )
        data["other_measure_label"] = "Tasa cruda" if filters["measure"] == "asr" else "Tasa ajustada por edad (Segi–Doll)"
        trend_max = max(item["count"] for item in data["trend"]) or 1
        for item in data["trend"]:
            item["bar_width"] = max(1, round(item["count"] / trend_max * 100))
        site_max = max((item["value"] for item in data["site_summary"]), default=0) or 1
        for item in data["site_summary"]:
            item["bar_width"] = max(1, round(item["value"] / site_max * 100))
        if request.GET.get("format") == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Aviso", "Datos agregados sintéticos; no representan resultados del RNC ni de Cuba."])
            writer.writerow([])
            writer.writerow(["Grupo de edad", "Tumores", "Personas distintas", "Frecuencia relativa de tumores (%)", "Frecuencia relativa de personas (%)", "Tasa específica de tumores por 100 000", "Tasa específica de personas por 100 000"])
            for row in data["age_rows"]:
                writer.writerow([row["age"], row["tumors"], row["persons"], f"{row['tumor_share']:.2f}", f"{row['person_share']:.2f}", f"{row['tumor_rate']:.2f}", f"{row['person_rate']:.2f}"])
            response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="consulta_sintetica_por_edad.csv"'
            return response

    return render(request, "public_site/synthetic_explorer.html", {
        "filters": filters,
        "options": options,
        "data": data,
        "asr_selected": filters["measure"] == "asr",
        "age_selected": bool(filters["age"]),
    })


@login_required
def intake_prototype(request):
    if not has_admin_access(request.user):
        raise PermissionDenied
    return render(request, "public_site/intake_prototype.html")
