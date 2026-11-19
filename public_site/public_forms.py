"""Forms shared by the public-only service; no account models are imported."""

from django import forms
from django.utils.translation import gettext as _

from .validation import AccessibleForm


CHART_DIMENSION_LIMITS = {
    "line": ("period",),
    "trend": ("period",),
    "curve": ("age_group",),
    "map": ("territory",),
    "grouped": ("period", "territory", "age_group", "site", "site_group", "morphology"),
    "stacked": ("period", "territory", "age_group", "site", "site_group", "morphology"),
    "percent": ("period", "territory", "age_group", "site", "site_group", "morphology"),
    "scatter": ("territory", "age_group"),
    "strip": ("territory", "age_group"),
    "swarm": ("territory", "age_group"),
}
CHART_METRIC_LIMITS = {
    "stacked": ("count",),
    "percent": ("count",),
    "pie": ("count", "share"),
    "doughnut": ("count", "share"),
    "scatter": ("count",),
}
CHART_UNIT_LIMITS = {"scatter": ("tumors",)}


class ExplorerForm(AccessibleForm, forms.Form):
    def __init__(
        self,
        *args,
        options,
        dimensions,
        charts,
        metrics,
        national_coverage=False,
        municipality_available=False,
        person_identity_verified=False,
        persons_disjoint=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.persons_disjoint = persons_disjoint
        self.fields["cohort"] = forms.ChoiceField(label=_("Población analizada"), choices=[("all", _("Todas las edades")), ("adult", _("20 años o más · CIE-10")), ("child", _("Menores de 20 años · CICN"))])
        options = {**options, "municipality": options.get("municipality", [])}
        labels = {
            "year": _("Año de incidencia"),
            "territory": _("Provincia de residencia"),
            "municipality": _("Municipio de residencia"),
            "sex": _("Sexo"),
            "age": _("Edad"),
            "site": _("Grupo de localización"),
        }
        for key, values in options.items():
            choices = [
                (str(value[0]), str(_(str(value[1]))))
                if isinstance(value, (tuple, list)) and len(value) == 2
                else (str(value), str(_(str(value))))
                for value in values
            ]
            self.fields[key] = forms.MultipleChoiceField(
                label=labels[key],
                required=False,
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
            )
        self.fields["territory"].help_text = (
            _("Provincia donde reside la persona.")
            if national_coverage
            else _("Provincia donde reside la persona. Esta publicación no cubre todas las provincias.")
        )
        self.fields["municipality"].disabled = not municipality_available
        self.fields["municipality"].help_text = (
            ""
            if municipality_available
            else _("Esta publicación no incluye datos por municipio.")
        )
        self.fields["site"].help_text = _("Agrupa los tumores según su localización anatómica.")
        self.fields["unit"] = forms.ChoiceField(
            label=_("Unidad de conteo"),
            choices=[("tumors", _("Tumores"))] + ([("persons", _("Personas distintas"))] if person_identity_verified else []),
        )
        self.fields["metric"] = forms.ChoiceField(
            label=_("Indicador"),
            choices=list(metrics.items()),
            help_text=_("La tasa ajustada por edad requiere incluir todos los grupos de edad."),
        )
        self.fields["dimension"] = forms.ChoiceField(
            label=_("Comparar por"),
            choices=[
                (value, _("Grupo de localización") if value == "site" else label)
                for value, label in dimensions.items()
            ],
        )
        self.fields["chart"] = forms.ChoiceField(
            label=_("Tipo de gráfico"),
            choices=list(charts.items()),
        )
        for key, field in self.fields.items():
            field.widget.attrs["data-label"] = field.label

    def clean(self):
        data = super().clean()
        chart = data.get("chart")
        metric = data.get("metric")
        dimension = data.get("dimension")
        unit = data.get("unit")
        cohort = data.get("cohort", "all")
        if dimension == "stage" and (cohort != "adult" or metric not in {"count", "share"}):
            self.add_error("dimension", _("La etapa clínica se consulta en adultos, mediante frecuencias o porcentajes."))
        if (dimension in {"site", "site_group"} or data.get("site")) and cohort == "all" and metric in {"rate", "asr"}:
            self.add_error("metric", _("Seleccione población adulta o infantil para calcular tasas por grupo tumoral."))
        if chart in CHART_DIMENSION_LIMITS and dimension not in CHART_DIMENSION_LIMITS[chart]:
            self.add_error("dimension", _("Esta dimensión no está disponible para el gráfico seleccionado."))
        if chart in CHART_METRIC_LIMITS and metric not in CHART_METRIC_LIMITS[chart]:
            self.add_error("metric", _("Este indicador no está disponible para el gráfico seleccionado."))
        if chart in CHART_UNIT_LIMITS and unit not in CHART_UNIT_LIMITS[chart]:
            self.add_error("unit", _("Este gráfico requiere la unidad Tumores."))
        if chart in {"pie", "doughnut"} and unit == "persons" and dimension != "sex":
            self.add_error("unit", _("Para personas distintas, la composición solo se puede comparar por sexo."))
        if chart == "scatter" and not self.persons_disjoint:
            if any(len(data.get(key) or []) > 1 for key in ("year", "territory", "municipality", "sex", "age", "site")):
                self.add_error(
                    "chart",
                    _("La dispersión necesita una selección que permita contar personas distintas sin solapamientos."),
                )
        if metric == "asr" and (data.get("age") or dimension == "age_group"):
            self.add_error(
                "metric",
                _("El ajuste por edad requiere todos los grupos de edad y otra dimensión."),
            )
        if unit == "persons" and not self.persons_disjoint and any(
            len(data.get(key) or []) > 1
            for key in ("year", "territory", "municipality", "sex", "age", "site")
        ):
            self.add_error(
                "unit",
                _("El corte agregado no permite deduplicar personas distintas al combinar varios valores. Use Tumores o seleccione un solo valor por filtro."),
            )
        if chart in {"grouped", "stacked", "percent"} and (
            data.get("sex") or dimension == "sex"
        ):
            self.add_error(
                "chart", _("La comparación por sexo requiere ambos sexos y otra dimensión.")
            )
        return data
