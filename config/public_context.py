"""Minimal navigation context for the isolated public service."""


PUBLIC_PAGES = [
    {"name": "home", "label": "Inicio", "icon": "home"},
    {
        "name": "synthetic_explorer",
        "label": "Consulta estadística",
        "icon": "chart",
    },
]


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    current_label = next(
        (page["label"] for page in PUBLIC_PAGES if page["name"] == current),
        "Estadísticas públicas",
    )
    return {
        "page_navigation": PUBLIC_PAGES,
        "section_navigation": [],
        "current_page_label": current_label,
        "session_identity": "anonymous",
        "portal_login_available": False,
        "has_admin_access": False,
        "can_manage_users": False,
    }
