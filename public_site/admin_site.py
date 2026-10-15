"""Restrict the user management backend to the support role."""

from django.contrib.admin import AdminSite

from .access import has_admin_access


class SupportAdminSite(AdminSite):
    site_header = "RNC Cuba · Administración"
    site_title = "Administración RNC"
    index_title = "Usuarios y permisos"

    def has_permission(self, request):
        return request.user.is_staff and has_admin_access(request.user)
