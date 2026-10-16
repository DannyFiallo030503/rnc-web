from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # All account operations use the portal's role and account-safety policies.
    path(
        "admin/",
        RedirectView.as_view(pattern_name="public_site:users", permanent=False),
    ),
    path("", include("public_site.urls")),
]
