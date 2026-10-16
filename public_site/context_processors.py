"""Navegación compartida por todas las pantallas."""

from django.conf import settings
from .access import has_admin_access


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    admin_access = has_admin_access(request.user)
    pages = [{"name": "home", "label": "Inicio", "icon": "home", "description": "Portal de estadísticas"}]
    if settings.DEBUG:
        pages.append({"name": "synthetic_explorer", "label": "Consulta estadística", "icon": "chart", "description": "Exploración con datos sintéticos"})
    if admin_access:
        pages.append({"name": "intake_prototype", "label": "Administración", "icon": "folder", "description": "Gestión de cortes"})
    available_pages = {page["name"] for page in pages}
    sections = {
        "home": [("inicio", "Presentación"), ("explorador", "Estadísticas"), ("criterios", "Criterios de lectura")],
        "synthetic_explorer": [("consulta", "Filtros de consulta"), ("indicadores", "Indicadores"), ("graficos", "Gráficos"), ("detalle", "Tabla de resultados")],
        "intake_prototype": [("resumen", "Resumen de cortes"), ("cortes", "Cortes recientes"), ("proceso", "Incorporación y publicación")],
    }
    active_sections = sections.get(current, []) if current in available_pages else []
    fallback_labels = {"login": "Iniciar sesión", "intake_prototype": "Acceso restringido"}
    return {
        "page_navigation": pages,
        "section_navigation": [{"anchor": anchor, "label": label} for anchor, label in active_sections],
        "current_page_label": next((page["label"] for page in pages if page["name"] == current), fallback_labels.get(current, "Página")),
        "local_navigation": settings.DEBUG,
        "has_admin_access": admin_access,
        "can_manage_users": admin_access and request.user.is_staff,
    }
