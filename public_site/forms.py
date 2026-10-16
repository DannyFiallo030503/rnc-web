from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group
from .services import ingest


class UploadForm(forms.Form):
    title = forms.CharField(label="Nombre del corte", max_length=120)
    file = forms.FileField(label="Archivo CSV sintético")
    synthetic = forms.BooleanField(
        label="Confirmo que el archivo contiene exclusivamente datos sintéticos"
    )


class AccountForm(forms.ModelForm):
    confirm_password = forms.CharField(
        label="Su contraseña de soporte para confirmar la operación",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
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
        label="Contraseña temporal (opcional; sin ella se envía invitación)",
        required=False,
        widget=forms.PasswordInput,
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {
            "username": "Usuario",
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
            "is_active": "Cuenta activa",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not email:
            raise forms.ValidationError(
                "Indique un correo para invitaciones y recuperación."
            )
        q = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise forms.ValidationError("Ese correo ya está asignado a otra cuenta.")
        return email

    def clean_initial_password(self):
        password = self.cleaned_data.get("initial_password")
        if password:
            validate_password(password, self.instance)
        return password
