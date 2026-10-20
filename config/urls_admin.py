from django.urls import include, path, re_path
from public_site import errors

urlpatterns = [
    path("", include(("public_site.admin_urls", "public_site"), namespace="public_site")),
    re_path(r"^.*$", errors.not_found, name="not_found"),
]
