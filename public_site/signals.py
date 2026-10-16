"""Initialize the product's first administrative role after migrations."""

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .access import SUPERADMIN_GROUP


@receiver(post_migrate)
def ensure_superadmin_group(sender, using, **kwargs):
    # Auth has database models and emits post_migrate even while public_site
    # contains only views. Its default permissions have been created by now.
    if sender.label != "auth":
        return
    group, _ = Group.objects.using(using).get_or_create(name=SUPERADMIN_GROUP)
    permissions = Permission.objects.using(using).filter(
        content_type__app_label="auth"
    )
    group.permissions.set(permissions)
