from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class RNCAdminConfig(AdminConfig):
    default_site = "public_site.admin_site.SupportAdminSite"


class PublicSiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "public_site"

    def ready(self):
        from . import signals
