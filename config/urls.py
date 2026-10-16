from django.urls import include, path, re_path
from django.views.generic import RedirectView
from public_site import errors

urlpatterns = [
    # All account operations use the portal's role and account-safety policies.
    path(
        "admin/",
        RedirectView.as_view(pattern_name="public_site:users", permanent=False),
    ),
    path("", include("public_site.urls")),
    re_path(r"^.*$", errors.not_found, name="not_found"),
]
