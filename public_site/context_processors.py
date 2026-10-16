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
    display_name = (
        request.user.get_short_name() or request.user.get_username()
        if request.user.is_authenticated
        else ""
    )
    if has_admin_access(request.user):
        role_label = "Administrador de soporte"
    elif can(request.user, "publish_deliveries"):
        role_label = "Responsable de publicación"
    elif can(request.user, "operate_deliveries"):
        role_label = "Operador de cargas"
    else:
        role_label = "Consulta pública"
    return {
        "account_display_name": display_name,
        "account_role_label": role_label,
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
