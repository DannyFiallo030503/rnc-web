"""Field contracts shared with the browser; never a substitute for safe sinks."""

import re
import unicodedata
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator

RULES = {
    "username": (
        r"[A-Za-z0-9._-]+",
        "Use letras de la A a la Z, números, punto, guion o guion bajo.",
    ),
    "person-name": (
        r"[^\W\d_]+(?:[ '’-][^\W\d_]+)*",
        "Use letras, espacios, apóstrofos o guiones; por ejemplo, María José.",
    ),
    "plain-text": (
        r"[\w\s.,;:()'·’–—+/%&!?@#-]+",
        "Use texto, números y puntuación habitual; sin etiquetas HTML.",
    ),
    "search": (
        r"[\w .@+'’-]*",
        "Busque por nombre, usuario o correo; no se admiten símbolos de programación.",
    ),
}


def validate_text(value, rule):
    value = unicodedata.normalize("NFC", value).replace("\u00a0", " ").strip()
    # Only ordinary spaces/newlines: never bidi overrides, NUL or hidden controls.
    if any(
        unicodedata.category(c).startswith("C")
        and not (rule == "plain-text" and c == "\n")
        for c in value
    ) or not re.fullmatch(RULES[rule][0], value):
        raise ValidationError(RULES[rule][1], code="invalid")
    if rule == "plain-text" and not any(c.isalnum() for c in value):
        raise ValidationError("Incluya una descripción con letras o números.")
    return value


class TextField(forms.CharField):
    def __init__(self, *args, rule="plain-text", **kwargs):
        self.rule = rule
        super().__init__(*args, **kwargs)
        self.widget.attrs.update(
            {"data-rule": rule, "data-rule-message": RULES[rule][1]}
        )

    def clean(self, value):
        value = super().clean(value)
        return validate_text(value, self.rule) if value else value


class AccessibleForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.error_messages["required"] = (
                "Complete este campo."
                if not isinstance(field, forms.BooleanField)
                else "Marque esta confirmación para continuar."
            )
            attrs = field.widget.attrs
            attrs["data-label"] = field.label or name.replace("_", " ").capitalize()
            if getattr(field, "min_length", None):
                attrs["minlength"] = field.min_length
            if isinstance(field, forms.EmailField):
                attrs.update(
                    {
                        "data-rule": "email",
                        "autocomplete": "email",
                        "maxlength": 254,
                        "inputmode": "email",
                        "autocapitalize": "none",
                    }
                )
            if isinstance(field.widget, forms.PasswordInput):
                attrs.setdefault(
                    "autocomplete",
                    (
                        "new-password"
                        if name
                        in {"new_password1", "new_password2", "initial_password"}
                        else "current-password"
                    ),
                )
                # Existing credentials remain unrestricted; only new secrets have a policy limit.
                if name in {"new_password1", "new_password2", "initial_password"}:
                    field.max_length = 128
                    field.validators.append(MaxLengthValidator(128))
                    attrs.update(
                        {"minlength": 8, "maxlength": 128, "data-rule": "new-password"}
                    )
            if name in {"new_password2"}:
                attrs["data-matches"] = "new_password1"
            if name == "username":
                attrs.setdefault("autocomplete", "username")
                attrs.update({"autocapitalize":"none","spellcheck":"false"})
