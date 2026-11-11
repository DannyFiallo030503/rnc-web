from django.urls import path
from . import public_portal

app_name = "public_site"
urlpatterns = [
    path("", public_portal.home, name="home"),
    path("el-rnc/", public_portal.about, name="about"),
    path("consulta/", public_portal.explorer, name="synthetic_explorer"),
    path("nomencladores/", public_portal.coding_nomenclators, name="coding_nomenclators"),
    path("consulta-sintetica/", public_portal.explorer, name="legacy_explorer"),
    path("consulta-offline/", public_portal.offline_consult, name="offline_consult"),
    path("paquete-offline.json", public_portal.offline_package, name="offline_package"),
    path("<path:unused>/", public_portal.not_found, name="not_found"),
]
