"""Minimal navigation context for the isolated public service."""

from config.i18n import language_return_path
from django.utils.translation import gettext_lazy as _
from django.utils.translation import get_language
from django.conf import settings


PUBLIC_PAGES = [
    {"name": "home", "label": _("Inicio"), "icon": "home"},
    {"name": "about", "label": _("Acerca de"), "icon": "book"},
    {
        "name": "synthetic_explorer",
        "label": _("Consulta estadística"),
        "icon": "chart",
    },
    {"name": "coding_nomenclators", "label": _("Nomencladores"), "icon": "book"},
]


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    current_label = next(
        (page["label"] for page in PUBLIC_PAGES if page["name"] == current),
        _("Estadísticas públicas"),
    )
    return {
        "language_next_url": language_return_path(request),
        "page_navigation": PUBLIC_PAGES,
        "section_navigation": [{"anchor": key, "label": _(label)} for key,label in [("que-hacemos","Qué hacemos"),("donde-trabajamos","Dónde trabajamos"),("como-trabajamos","Cómo trabajamos"),("oficina-central","Oficina central"),("registros-provinciales","Registros provinciales"),("contactos","Contactos"),("metodos","Métodos y cálculos"),("fuentes-limites","Fuentes y límites")]] if current == "about" else [],
        "admin_login_url": (
            settings.ADMIN_SITE_URL.rstrip("/") + "/"
            if settings.ADMIN_SITE_URL.rstrip("/").endswith("/acceso")
            else settings.ADMIN_SITE_URL.rstrip("/") + "/acceso/"
        ) if settings.ADMIN_SITE_URL else "",
        "current_page_label": current_label,
        "session_identity": "anonymous",
        "portal_login_available": False,
        "public_pwa_enabled": True,
        "translation_preview": (
            getattr(settings, "TRANSLATION_PREVIEW_ENABLED", False)
            and (get_language() or "")
            in getattr(settings, "DRAFT_TRANSLATION_LOCALES", ())
        ),
        "draft_translation_locales": getattr(
            settings, "DRAFT_TRANSLATION_LOCALES", ()
        ),
        "has_admin_access": False,
        "can_manage_users": False,
    }
