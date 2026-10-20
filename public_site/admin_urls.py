from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, re_path
from django.views.generic import RedirectView, TemplateView
from . import accounts, errors, views, portal

app_name = "public_site"
urlpatterns = [
    path("", RedirectView.as_view(url=settings.PUBLIC_SITE_URL, permanent=False), name="home"),
    path(
        "consulta/",
        RedirectView.as_view(url=settings.PUBLIC_SITE_URL.rstrip("/") + "/consulta/", permanent=False),
        name="synthetic_explorer",
    ),
    path(
        "consulta-sintetica/",
        RedirectView.as_view(url=settings.PUBLIC_SITE_URL.rstrip("/") + "/consulta/", permanent=False),
        name="legacy_explorer",
    ),
    path("admin/", RedirectView.as_view(pattern_name="public_site:users", permanent=False)),
    path("acceso/", views.RoleLoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("administracion/cortes/", portal.administration, name="intake_prototype"),
    path("administracion/cortes/ejemplo/", portal.sample, name="sample"),
    path("administracion/cortes/<uuid:pk>/", portal.delivery, name="delivery"),
    path("administracion/cortes/<uuid:pk>/estado/", portal.delivery_action, name="delivery_action"),
    path("administracion/usuarios/", accounts.users, name="users"),
    path("administracion/usuarios/nuevo/", accounts.user_edit, name="user_create"),
    path("administracion/usuarios/<int:pk>/", accounts.user_edit, name="user_edit"),
    path("cuenta/contrasena/", accounts.PasswordChange.as_view(), name="password_change"),
    path(
        "cuenta/contrasena/actualizada/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={"heading": "Contraseña actualizada", "intro": "Su contraseña se guardó correctamente."},
        ),
        name="password_change_done",
    ),
    path("cuenta/recuperar/", accounts.ResetRequest.as_view(), name="password_reset"),
    path(
        "cuenta/recuperar/solicitado/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={"heading": "Solicitud recibida", "intro": "Si existe una cuenta activa con ese correo, recibirá instrucciones."},
        ),
        name="password_reset_done",
    ),
    path("cuenta/restablecer/<uidb64>/<token>/", accounts.ResetConfirm.as_view(), name="password_reset_confirm"),
    path(
        "cuenta/restablecida/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={"heading": "Contraseña guardada", "intro": "Ya puede iniciar sesión con su nueva contraseña."},
        ),
        name="password_reset_complete",
    ),
    re_path(r"^.*$", errors.not_found, name="not_found"),
]
