"""Password rules with project-owned, translatable user messages."""

from django.contrib.auth.password_validation import (
    CommonPasswordValidator as DjangoCommonPasswordValidator,
    MinimumLengthValidator as DjangoMinimumLengthValidator,
    NumericPasswordValidator as DjangoNumericPasswordValidator,
    UserAttributeSimilarityValidator as DjangoUserAttributeSimilarityValidator,
)
from django.utils.translation import gettext as _, gettext_lazy


class UserAttributeSimilarityValidator(DjangoUserAttributeSimilarityValidator):
    def get_error_message(self):
        return gettext_lazy("La contraseña no debe parecerse a sus datos personales.")

    def get_help_text(self):
        return str(
            _("La contraseña no debe ser muy similar a sus otros datos personales.")
        )


class MinimumLengthValidator(DjangoMinimumLengthValidator):
    def get_error_message(self):
        return gettext_lazy(
            "La contraseña es demasiado corta; debe contener al menos "
            "%(min_length)s caracteres."
        )

    def get_help_text(self):
        return str(
            _("La contraseña debe tener al menos %(min_length)s caracteres.")
            % {"min_length": self.min_length}
        )


class CommonPasswordValidator(DjangoCommonPasswordValidator):
    def get_error_message(self):
        return gettext_lazy("Elija una contraseña que no sea de uso común.")

    def get_help_text(self):
        return str(_("No utilice una contraseña de uso común."))


class NumericPasswordValidator(DjangoNumericPasswordValidator):
    def get_error_message(self):
        return gettext_lazy("La contraseña no puede contener solo números.")

    def get_help_text(self):
        return str(_("No utilice solo números como contraseña."))
