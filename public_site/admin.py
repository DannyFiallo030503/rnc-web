"""Use Django's account forms with concise Spanish labels and visible roles."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group


class SpanishActions:
    def get_action_choices(self, request, *args, **kwargs):
        choices = super().get_action_choices(request, *args, **kwargs)
        return [(value, label if value else "Selecciona una acción") for value, label in choices]


class SupportUserAdmin(SpanishActions, UserAdmin):
    list_display = ("username", "email", "account_roles", "is_active", "is_staff")

    @admin.display(description="Roles")
    def account_roles(self, account):
        if account.is_superuser:
            return "Superadmin"
        return ", ".join(group.name for group in account.groups.all()) or "Consulta pública"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")


class SupportGroupAdmin(SpanishActions, GroupAdmin):
    pass


admin.site.unregister(get_user_model())
admin.site.unregister(Group)
admin.site.register(get_user_model(), SupportUserAdmin)
admin.site.register(Group, SupportGroupAdmin)
