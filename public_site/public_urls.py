from django.urls import path
from . import public_portal

app_name = "public_site"
urlpatterns = [
    path("", public_portal.home, name="home"),
    path("consulta/", public_portal.explorer, name="synthetic_explorer"),
    path("consulta-sintetica/", public_portal.explorer, name="legacy_explorer"),
    path("<path:unused>/", public_portal.not_found, name="not_found"),
]
