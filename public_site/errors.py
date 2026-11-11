from django.shortcuts import render
from django.utils.translation import gettext_lazy as _


def csrf_failure(request, reason=""):
    return render(
        request,
        "public_site/account_notice.html",
        {
            "heading": _("No se pudo enviar el formulario"),
            "intro": _("La sesión del formulario ha caducado o no se pudo verificar. Vuelva a abrir la página e inténtelo otra vez. No se guardó este envío."),
        },
        status=403,
    )


def not_found(request,exception=None):
    return render(
        request,
        "public_site/account_notice.html",
        {
            "heading": _("No encontramos esa página"),
            "intro": _(
                "La dirección no existe o el recurso ya no está disponible. "
                "Puede continuar desde la navegación del portal."
            ),
        },
        status=404,
    )
