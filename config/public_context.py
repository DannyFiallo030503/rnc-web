"""Minimal navigation context for the isolated public service."""

from django.utils.translation import gettext as _
from django.utils.translation import get_language
from django.conf import settings


PUBLIC_PAGES = [
    {"name": "home", "label": _("Inicio"), "icon": "home"},
    {
        "name": "synthetic_explorer",
        "label": _("Consulta estadística"),
        "icon": "chart",
    },
    {"name": "coding_nomenclators", "label": _("Nomencladores"), "icon": "book"},
    {"name": "offline_consult", "label": _("Consulta sin conexión"), "icon": "chart"},
]


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    current_label = next(
        (page["label"] for page in PUBLIC_PAGES if page["name"] == current),
        _("Estadísticas públicas"),
    )
    return {
        "page_navigation": PUBLIC_PAGES,
        "section_navigation": [],
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
