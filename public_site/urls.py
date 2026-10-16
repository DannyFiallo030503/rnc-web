from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from . import views, portal, accounts

app_name = "public_site"
urlpatterns = [
    path("", portal.home, name="home"),
    path("acceso/", views.RoleLoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("consulta/", portal.explorer, name="synthetic_explorer"),
    path("consulta-sintetica/", portal.explorer, name="legacy_explorer"),
    path("administracion/cortes/", portal.administration, name="intake_prototype"),
    path("administracion/cortes/ejemplo/", portal.sample, name="sample"),
    path("administracion/cortes/<uuid:pk>/", portal.delivery, name="delivery"),
    path(
        "administracion/cortes/<uuid:pk>/estado/",
        portal.delivery_action,
        name="delivery_action",
    ),
    path("administracion/usuarios/", accounts.users, name="users"),
    path("administracion/usuarios/nuevo/", accounts.user_edit, name="user_create"),
    path("administracion/usuarios/<int:pk>/", accounts.user_edit, name="user_edit"),
    path(
        "cuenta/contrasena/", accounts.PasswordChange.as_view(), name="password_change"
    ),
    path(
        "cuenta/contrasena/actualizada/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={
                "heading": "Contraseña actualizada",
                "intro": "Su contraseña se guardó correctamente.",
            },
        ),
        name="password_change_done",
    ),
    path("cuenta/recuperar/", accounts.ResetRequest.as_view(), name="password_reset"),
    path(
        "cuenta/recuperar/solicitado/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={
                "heading": "Solicitud recibida",
                "intro": "Si existe una cuenta activa con ese correo, recibirá un enlace para establecer su contraseña. Revise también la carpeta de correo no deseado.",
            },
        ),
        name="password_reset_done",
    ),
    path(
        "cuenta/restablecer/<uidb64>/<token>/",
        accounts.ResetConfirm.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "cuenta/restablecida/",
        TemplateView.as_view(
            template_name="public_site/account_notice.html",
            extra_context={
                "heading": "Contraseña guardada",
                "intro": "Ya puede iniciar sesión con su nueva contraseña.",
            },
        ),
        name="password_reset_complete",
    ),
]
