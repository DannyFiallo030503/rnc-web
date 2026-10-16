from .access import has_admin_access, can


def navigation(request):
    current = request.resolver_match.url_name if request.resolver_match else ""
    pages = [
        {"name": "home", "label": "Inicio", "icon": "home"},
        {
            "name": "synthetic_explorer",
            "label": "Consulta estadística",
            "icon": "chart",
        },
    ]
    if can(request.user, "operate_deliveries"):
        pages.append(
            {"name": "intake_prototype", "label": "Administración", "icon": "folder"}
        )
    labels = {
        "users": "Usuarios y permisos",
        "user_create": "Crear usuario",
        "user_edit": "Editar usuario",
        "delivery": "Detalle del corte",
        "login": "Iniciar sesión",
        "password_change": "Cambiar contraseña",
        "password_reset": "Recuperar acceso",
    }
    return {
        "page_navigation": pages,
        "section_navigation": [],
        "current_page_label": next(
            (p["label"] for p in pages if p["name"] == current),
            labels.get(current, "Cuenta"),
        ),
        "has_admin_access": can(request.user, "operate_deliveries"),
        "can_manage_users": has_admin_access(request.user),
        "local_navigation": True,
    }
