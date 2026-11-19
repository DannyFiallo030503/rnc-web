from django.urls import include, path, re_path
from config.i18n import javascript_catalog
from public_site import errors

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", javascript_catalog, name="javascript-catalog"),
    path("", include(("public_site.admin_urls", "public_site"), namespace="public_site")),
    re_path(r"^.*$", errors.not_found, name="not_found"),
]
