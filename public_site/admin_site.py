"""Restrict the user management backend to the support role."""

from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

from .access import has_admin_access


class SupportAdminSite(AdminSite):
    site_header = _("RNC Cuba · Administración")
    site_title = _("Administración RNC")
    index_title = _("Usuarios y permisos")

    def has_permission(self, request):
        return request.user.is_staff and has_admin_access(request.user)
