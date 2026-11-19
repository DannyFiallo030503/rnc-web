from django.urls import include, path, re_path
from config.i18n import javascript_catalog
from django.views.generic import RedirectView
from public_site import errors, public_portal
from django.conf import settings

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", javascript_catalog, name="javascript-catalog"),
    # All account operations use the portal's role and account-safety policies.
    path(
        "admin/",
        RedirectView.as_view(pattern_name="public_site:users", permanent=False),
    ),
    path("", include("public_site.urls")),
    re_path(r"^.*$", errors.not_found, name="not_found"),
]

if settings.PUBLIC_PWA_ENABLED:
    urlpatterns.insert(0, path("service-worker.js", public_portal.service_worker, name="service_worker"))
