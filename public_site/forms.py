from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .validation import AccessibleForm, TextField, validate_text


class UploadForm(AccessibleForm, forms.Form):
    title = TextField(
        label=_("Nombre del corte"),
        max_length=120,
        min_length=3,
        help_text=_("Un nombre que identifique el período y la entrega."),
    )
    file = forms.FileField(
        label=_("Archivo CSV sintético"),
        widget=forms.ClearableFileInput(
            attrs={"accept": ".csv,text/csv", "data-max-bytes": 12582912}
        ),
        help_text=_("CSV UTF-8, hasta 12 MB y 60 000 filas. Solo datos sintéticos."),
    )
    synthetic = forms.BooleanField(
        label=_("Confirmo que el archivo contiene exclusivamente datos sintéticos")
    )

    def clean_file(self):
        value = self.cleaned_data["file"]
        if not value.name.lower().endswith(".csv"):
            raise forms.ValidationError(_("Seleccione un archivo con extensión .csv."))
        if value.size > 12 * 1024 * 1024:
            raise forms.ValidationError(_("El archivo supera el límite de 12 MB."))
        return value


class DecisionForm(AccessibleForm, forms.Form):
    action = forms.ChoiceField(
        label=_("Operación"),
        choices=[("publish", _("Publicar")), ("revoke", _("Revocar"))],
        widget=forms.HiddenInput,
    )
    reason = TextField(
        label=_("Motivo de la decisión"),
        min_length=10,
        max_length=250,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Entre 10 y 250 caracteres. Esta decisión queda registrada en el historial."),
    )


class SearchForm(AccessibleForm, forms.Form):
    q = TextField(
        label=_("Buscar usuario"),
        required=False,
        max_length=100,
        rule="search",
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Nombre, usuario o correo")}
        ),
    )


class AccountForm(AccessibleForm, forms.ModelForm):
    username = TextField(
        label=_("Usuario"),
        rule="username",
        max_length=150,
        min_length=3,
        help_text=_("Letras sin tildes, números, puntos, guiones o guion bajo. Al menos 3 caracteres."),
    )
    first_name = TextField(
        label=_("Nombre"),
        rule="person-name",
        max_length=150,
        help_text=_("Se admiten tildes, espacios, apóstrofos y guiones."),
    )
    last_name = TextField(label=_("Apellidos"), rule="person-name", max_length=150)
    email = forms.EmailField(
        label=_("Correo electrónico"),
        max_length=254,
        help_text=_("Se utilizará para invitaciones y recuperación de acceso."),
    )
    role = forms.ChoiceField(
        label=_("Rol"),
        choices=[
            ("reader", _("Consulta pública")),
            ("operator", _("Operador de cargas")),
            ("publisher", _("Responsable de publicación")),
            ("superadmin", _("Administrador de soporte")),
        ],
    )
    initial_password = forms.CharField(
        label=_("Contraseña temporal"),
        required=False,
        widget=forms.PasswordInput,
        help_text=_("Opcional. Sin ella, se enviará una invitación para elegir contraseña. Con ella, se exigirá cambiarla al entrar."),
    )
    confirm_password = forms.CharField(
        label=_("Su contraseña de soporte"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text=_("Confirme su identidad para guardar los cambios."),
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"is_active": _("Cuenta activa")}
        help_texts = {
            "is_active": _("Desactive la cuenta para retirar el acceso sin eliminar su historial.")
        }

    def clean_username(self):
        value = self.cleaned_data["username"]
        q = get_user_model().objects.filter(username__iexact=value)
        if self.instance.pk:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise forms.ValidationError(
                _("Ese nombre de usuario ya está en uso. Elija otro.")
            )
        return value

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        q = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise forms.ValidationError(_("Ese correo ya está asignado a otra cuenta."))
        return email

    def clean_initial_password(self):
        password = self.cleaned_data.get("initial_password")
        if password:
            if len(password) > 128:
                raise forms.ValidationError(_("Use como máximo 128 caracteres."))
            candidate = get_user_model()(
                username=self.cleaned_data.get("username", ""),
                first_name=self.cleaned_data.get("first_name", ""),
                last_name=self.cleaned_data.get("last_name", ""),
                email=self.cleaned_data.get("email", ""),
            )
            validate_password(password, candidate)
        return password


class LoginForm(AccessibleForm, AuthenticationForm):
    username = TextField(label=_("Usuario"), rule="username", max_length=150)

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("El usuario o la contraseña no son válidos."),
        "inactive": _("La cuenta no está activa."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].label = _("Contraseña")


class ChangePasswordForm(AccessibleForm, PasswordChangeForm):
    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_mismatch": _("Las contraseñas nuevas no coinciden."),
        "password_incorrect": _("La contraseña actual no es correcta."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Contraseña actual")
        self.fields["new_password1"].label = _("Nueva contraseña")
        self.fields["new_password2"].label = _("Confirmar nueva contraseña")
        self.fields["new_password2"].help_text = _("Repita la misma contraseña para confirmar.")


class RecoveryForm(AccessibleForm, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = _("Correo electrónico")


class NewPasswordForm(AccessibleForm, SetPasswordForm):
    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": _("Las contraseñas nuevas no coinciden."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = _("Nueva contraseña")
        self.fields["new_password2"].label = _("Confirmar nueva contraseña")
        self.fields["new_password2"].help_text = _("Repita la misma contraseña para confirmar.")

    def clean_new_password1(self):
        value = self.cleaned_data["new_password1"]
        if len(value) > 128:
            raise forms.ValidationError(_("Use como máximo 128 caracteres."))
        return value


class ExplorerForm(AccessibleForm, forms.Form):
    def __init__(self, *args, options, dimensions, charts, metrics, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "year": _("Período"),
            "territory": _("Territorio"),
            "sex": _("Sexo"),
            "age": _("Edad"),
            "site": _("Grupo de localización ilustrativo"),
        }
        for key, values in options.items():
            self.fields[key] = forms.ChoiceField(
                label=labels[key],
                required=False,
                choices=[("", _("Todos"))] + [(str(v), str(v)) for v in values],
            )
        self.fields["unit"] = forms.ChoiceField(
            label=_("Unidad de conteo"),
            choices=[("tumors", _("Tumores")), ("persons", _("Personas distintas"))],
        )
        self.fields["metric"] = forms.ChoiceField(
            label=_("Indicador"),
            choices=list(metrics.items()),
            help_text=_("El ajuste por edad necesita todos los grupos de edad."),
        )
        self.fields["dimension"] = forms.ChoiceField(
            label=_("Comparar por"), choices=list(dimensions.items())
        )
        self.fields["chart"] = forms.ChoiceField(
            label=_("Tipo de gráfico"),
            choices=list(charts.items()),
            help_text=_("Solo se ofrecen tipos compatibles con la selección. Circular y anillo: hasta 8 categorías excluyentes."),
        )
        for key, field in self.fields.items():
            field.widget.attrs["data-label"] = field.label

    def clean(self):
        d = super().clean()
        chart = d.get("chart")
        metric = d.get("metric")
        dimension = d.get("dimension")
        if chart == "line" and dimension != "period":
            self.add_error("chart", _("Las líneas requieren comparar por período."))
        if metric == "asr" and (d.get("age") or dimension == "age_group"):
            self.add_error(
                "metric",
                _("El ajuste por edad requiere todos los grupos de edad y otra dimensión."),
            )
        if chart in {"grouped", "stacked", "percent"} and (
            d.get("sex") or dimension == "sex"
        ):
            self.add_error(
                "chart",
                _("La comparación por sexo requiere ambos sexos y otra dimensión."),
            )
        if chart in {"stacked", "percent"} and metric != "count":
            self.add_error(
                "chart",
                _("Las barras apiladas requieren frecuencias absolutas; no se suman tasas ni porcentajes."),
            )
        if chart in {"pie", "doughnut"} and (
            metric not in {"count", "share"}
            or (d.get("unit") == "persons" and dimension != "sex")
        ):
            self.add_error(
                "chart",
                _("La composición requiere conteos o porcentajes de categorías excluyentes; para personas, compare por sexo."),
            )
        return d
