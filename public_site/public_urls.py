from django.urls import path
from . import public_portal
from config.i18n import localized

app_name = "public_site"
urlpatterns = [
    path("", localized(public_portal.home), name="home"),
    path("el-rnc/", localized(public_portal.about), name="about"),
    path("consulta/", localized(public_portal.explorer), name="synthetic_explorer"),
    path("nomencladores/", localized(public_portal.coding_nomenclators), name="coding_nomenclators"),
    path("consulta-sintetica/", localized(public_portal.explorer), name="legacy_explorer"),
    path("consulta-offline/", public_portal.offline_consult, name="offline_consult"),
    path("conexion.json", public_portal.connection_status, name="connection_status"),
    path("paquete-offline.json", public_portal.offline_package, name="offline_package"),
    path("<path:unused>/", public_portal.not_found, name="not_found"),
]
