from django.urls import include, path, re_path
from django.views.i18n import JavaScriptCatalog
from public_site import public_portal

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(domain="djangojs"), name="javascript-catalog"),
    path("service-worker.js", public_portal.service_worker, name="service_worker"),
    path("", include(("public_site.public_urls", "public_site"), namespace="public_site")),
    re_path(r"^.*$", public_portal.not_found, name="not_found"),
]
