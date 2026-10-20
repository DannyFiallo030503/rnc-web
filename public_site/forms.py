from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from .validation import AccessibleForm, TextField, validate_text


class UploadForm(AccessibleForm, forms.Form):
    title = TextField(
        label="Nombre del corte",
        max_length=120,
        min_length=3,
        help_text="Un nombre que identifique el período y la entrega.",
    )
    file = forms.FileField(
        label="Archivo CSV sintético",
        widget=forms.ClearableFileInput(
            attrs={"accept": ".csv,text/csv", "data-max-bytes": 12582912}
        ),
        help_text="CSV UTF-8, hasta 12 MB y 60 000 filas. Solo datos sintéticos.",
    )
    synthetic = forms.BooleanField(
        label="Confirmo que el archivo contiene exclusivamente datos sintéticos"
    )

    def clean_file(self):
        value = self.cleaned_data["file"]
        if not value.name.lower().endswith(".csv"):
            raise forms.ValidationError("Seleccione un archivo con extensión .csv.")
        if value.size > 12 * 1024 * 1024:
            raise forms.ValidationError("El archivo supera el límite de 12 MB.")
        return value


class DecisionForm(AccessibleForm, forms.Form):
    action = forms.ChoiceField(
        label="Operación",
        choices=[("publish", "Publicar"), ("revoke", "Revocar")],
        widget=forms.HiddenInput,
    )
    reason = TextField(
        label="Motivo de la decisión",
        min_length=10,
        max_length=250,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Entre 10 y 250 caracteres. Esta decisión queda registrada en el historial.",
    )


class SearchForm(AccessibleForm, forms.Form):
    q = TextField(
        label="Buscar usuario",
        required=False,
        max_length=100,
        rule="search",
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": "Nombre, usuario o correo"}
        ),
    )


class AccountForm(AccessibleForm, forms.ModelForm):
    username = TextField(
        label="Usuario",
        rule="username",
        max_length=150,
        min_length=3,
        help_text="Letras sin tildes, números, puntos, guiones o guion bajo. Al menos 3 caracteres.",
    )
    first_name = TextField(
        label="Nombre",
        rule="person-name",
        max_length=150,
        help_text="Se admiten tildes, espacios, apóstrofos y guiones.",
    )
    last_name = TextField(label="Apellidos", rule="person-name", max_length=150)
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        help_text="Se utilizará para invitaciones y recuperación de acceso.",
    )
    role = forms.ChoiceField(
        label="Rol",
        choices=[
            ("reader", "Consulta pública"),
            ("operator", "Operador de cargas"),
            ("publisher", "Responsable de publicación"),
            ("superadmin", "Administrador de soporte"),
        ],
    )
    initial_password = forms.CharField(
        label="Contraseña temporal",
        required=False,
        widget=forms.PasswordInput,
        help_text="Opcional. Sin ella, se enviará una invitación para elegir contraseña. Con ella, se exigirá cambiarla al entrar.",
    )
    confirm_password = forms.CharField(
        label="Su contraseña de soporte",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Confirme su identidad para guardar los cambios.",
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"is_active": "Cuenta activa"}
        help_texts = {
            "is_active": "Desactive la cuenta para retirar el acceso sin eliminar su historial."
        }

    def clean_username(self):
        value = self.cleaned_data["username"]
        q = get_user_model().objects.filter(username__iexact=value)
        if self.instance.pk:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise forms.ValidationError(
                "Ese nombre de usuario ya está en uso. Elija otro."
            )
        return value

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        q = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise forms.ValidationError("Ese correo ya está asignado a otra cuenta.")
        return email

    def clean_initial_password(self):
        password = self.cleaned_data.get("initial_password")
        if password:
            if len(password) > 128:
                raise forms.ValidationError("Use como máximo 128 caracteres.")
            candidate = get_user_model()(
                username=self.cleaned_data.get("username", ""),
                first_name=self.cleaned_data.get("first_name", ""),
                last_name=self.cleaned_data.get("last_name", ""),
                email=self.cleaned_data.get("email", ""),
            )
            validate_password(password, candidate)
        return password


class LoginForm(AccessibleForm, AuthenticationForm):
    username = TextField(label="Usuario", rule="username", max_length=150)


class ChangePasswordForm(AccessibleForm, PasswordChangeForm):
    pass


class RecoveryForm(AccessibleForm, PasswordResetForm):
    pass


class NewPasswordForm(AccessibleForm, SetPasswordForm):
    def clean_new_password1(self):
        value = self.cleaned_data["new_password1"]
        if len(value) > 128:
            raise forms.ValidationError("Use como máximo 128 caracteres.")
        return value


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
                choices=[("", "Todos")] + [(str(v), str(v)) for v in values],
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
        d = super().clean()
        chart = d.get("chart")
        metric = d.get("metric")
        dimension = d.get("dimension")
        if chart == "line" and dimension != "period":
            self.add_error("chart", "Las líneas requieren comparar por período.")
        if metric == "asr" and (d.get("age") or dimension == "age_group"):
            self.add_error(
                "metric",
                "El ajuste por edad requiere todos los grupos de edad y otra dimensión.",
            )
        if chart in {"grouped", "stacked", "percent"} and (
            d.get("sex") or dimension == "sex"
        ):
            self.add_error(
                "chart",
                "La comparación por sexo requiere ambos sexos y otra dimensión.",
            )
        if chart in {"stacked", "percent"} and metric != "count":
            self.add_error(
                "chart",
                "Las barras apiladas requieren frecuencias absolutas; no se suman tasas ni porcentajes.",
            )
        if chart in {"pie", "doughnut"} and (
            metric not in {"count", "share"}
            or (d.get("unit") == "persons" and dimension != "sex")
        ):
            self.add_error(
                "chart",
                "La composición requiere conteos o porcentajes de categorías excluyentes; para personas, compare por sexo.",
            )
        return d
