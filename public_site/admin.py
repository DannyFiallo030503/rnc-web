"""Use Django's account forms with concise Spanish labels and visible roles."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext as _, gettext_lazy


class SpanishActions:
    def get_action_choices(self, request, *args, **kwargs):
        choices = super().get_action_choices(request, *args, **kwargs)
        return [(value, label if value else _("Selecciona una acción")) for value, label in choices]


class SupportUserAdmin(SpanishActions, UserAdmin):
    list_display = ("username", "email", "account_roles", "is_active", "is_staff")

    @admin.display(description=gettext_lazy("Roles"))
    def account_roles(self, account):
        if account.is_superuser:
            return _("Administrador de soporte")
        labels = {
            "reader": _("Consulta pública"),
            "operator": _("Operador de cargas"),
            "publisher": _("Responsable de publicación"),
            "superadmin": _("Administrador de soporte"),
        }
        visible_roles = ", ".join(
            labels.get(group.name, group.name) for group in account.groups.all()
        )
        return visible_roles or _("Consulta pública")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")


class SupportGroupAdmin(SpanishActions, GroupAdmin):
    pass


admin.site.unregister(get_user_model())
admin.site.unregister(Group)
admin.site.register(get_user_model(), SupportUserAdmin)
admin.site.register(Group, SupportGroupAdmin)
