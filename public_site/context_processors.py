from .access import has_admin_access, can
from django.conf import settings
from django.utils.translation import get_language, gettext as _


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    pages = [
        {"name": "home", "label": _("Inicio"), "icon": "home"},
        {"name": "about", "label": _("El RNC"), "icon": "book"},
        {
            "name": "synthetic_explorer",
            "label": _("Consulta estadística"),
            "icon": "chart",
        },
        {"name": "coding_nomenclators", "label": _("Nomencladores"), "icon": "book"},
    ]
    if can(request.user, "operate_deliveries"):
        pages.append(
            {"name": "intake_prototype", "label": _("Administración"), "icon": "folder"}
        )
    labels = {
        "users": _("Usuarios y permisos"),
        "user_create": _("Crear usuario"),
        "user_edit": _("Editar usuario"),
        "delivery": _("Detalle del corte"),
        "login": _("Iniciar sesión"),
        "password_change": _("Cambiar contraseña"),
        "password_reset": _("Recuperar acceso"),
    }
    display_name = (
        request.user.get_short_name() or request.user.get_username()
        if request.user.is_authenticated
        else ""
    )
    if has_admin_access(request.user):
        role_label = _("Administrador de soporte")
    elif can(request.user, "publish_deliveries"):
        role_label = _("Responsable de publicación")
    elif can(request.user, "operate_deliveries"):
        role_label = _("Operador de cargas")
    else:
        role_label = _("Consulta pública")
    session_identity = "anonymous"
    if request.user.is_authenticated:
        session_identity = ":".join(
            [
                str(request.user.pk),
                str(int(request.user.is_active)),
                str(int(has_admin_access(request.user))),
                str(int(can(request.user, "operate_deliveries"))),
                str(int(can(request.user, "publish_deliveries"))),
            ]
        )
    return {
        "account_display_name": display_name,
        "account_role_label": role_label,
        "session_identity": session_identity,
        "page_navigation": pages,
        "section_navigation": [],
        "current_page_label": next(
            (p["label"] for p in pages if p["name"] == current),
            labels.get(current, _("Cuenta")),
        ),
        "has_admin_access": can(request.user, "operate_deliveries"),
        "can_manage_users": has_admin_access(request.user),
        "local_navigation": True,
        "portal_login_available": True,
        "public_pwa_enabled": False,
        "translation_preview": (
            getattr(settings, "TRANSLATION_PREVIEW_ENABLED", False)
            and (get_language() or "")
            in getattr(settings, "DRAFT_TRANSLATION_LOCALES", ())
        ),
        "draft_translation_locales": getattr(
            settings, "DRAFT_TRANSLATION_LOCALES", ()
        ),
    }
