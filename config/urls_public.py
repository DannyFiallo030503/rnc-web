from django.urls import include, path, re_path
from public_site import public_portal

urlpatterns = [
    path("", include(("public_site.public_urls", "public_site"), namespace="public_site")),
    re_path(r"^.*$", public_portal.not_found, name="not_found"),
]
