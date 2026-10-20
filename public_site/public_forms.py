"""Forms shared by the public-only service; no account models are imported."""

from django import forms

from .validation import AccessibleForm


class ExplorerForm(AccessibleForm, forms.Form):
    def __init__(self, *args, options, dimensions, charts, metrics, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "year": "Período",
            "territory": "Territorio",
            "sex": "Sexo",
            "age": "Edad",
            "site": "Grupo de localización ilustrativo",
        }
        for key, values in options.items():
            self.fields[key] = forms.ChoiceField(
                label=labels[key],
                required=False,
                choices=[("", "Todos")] + [(str(value), str(value)) for value in values],
            )
        self.fields["unit"] = forms.ChoiceField(
            label="Unidad de conteo",
            choices=[("tumors", "Tumores"), ("persons", "Personas distintas")],
        )
        self.fields["metric"] = forms.ChoiceField(
            label="Indicador",
            choices=list(metrics.items()),
            help_text="El ajuste por edad necesita todos los grupos de edad.",
        )
        self.fields["dimension"] = forms.ChoiceField(
            label="Comparar por", choices=list(dimensions.items())
        )
        self.fields["chart"] = forms.ChoiceField(
            label="Tipo de gráfico",
            choices=list(charts.items()),
            help_text="Solo se ofrecen tipos compatibles con la selección. Circular y anillo: hasta 8 categorías excluyentes.",
        )
        for key, field in self.fields.items():
            field.widget.attrs["data-label"] = field.label

    def clean(self):
        data = super().clean()
        chart = data.get("chart")
        metric = data.get("metric")
        dimension = data.get("dimension")
        if chart == "line" and dimension != "period":
            self.add_error("chart", "Las líneas requieren comparar por período.")
        if metric == "asr" and (data.get("age") or dimension == "age_group"):
            self.add_error(
                "metric",
                "El ajuste por edad requiere todos los grupos de edad y otra dimensión.",
            )
        if chart in {"grouped", "stacked", "percent"} and (
            data.get("sex") or dimension == "sex"
        ):
            self.add_error(
                "chart", "La comparación por sexo requiere ambos sexos y otra dimensión."
            )
        if chart in {"stacked", "percent"} and metric != "count":
            self.add_error(
                "chart",
                "Las barras apiladas requieren frecuencias absolutas; no se suman tasas ni porcentajes.",
            )
        if chart in {"pie", "doughnut"} and (
            metric not in {"count", "share"}
            or (data.get("unit") == "persons" and dimension != "sex")
        ):
            self.add_error(
                "chart",
                "La composición requiere conteos o porcentajes de categorías excluyentes; para personas, compare por sexo.",
            )
        return data
