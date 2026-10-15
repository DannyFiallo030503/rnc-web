from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = "public_site"

urlpatterns = [
    path("", views.home, name="home"),
    path("acceso/", views.RoleLoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("consulta-sintetica/", views.synthetic_explorer, name="synthetic_explorer"),
    path("administracion/cortes/", views.intake_prototype, name="intake_prototype"),
]
