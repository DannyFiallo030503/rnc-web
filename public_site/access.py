"""Server-side capabilities; ordinary roles remain proposed, not RNC-approved."""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

SUPERADMIN_GROUP = "superadmin"


def has_admin_access(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.groups.filter(name=SUPERADMIN_GROUP).exists())
    )


def can(user, capability):
    return bool(
        user.is_authenticated
        and user.is_active
        and (has_admin_access(user) or user.has_perm("public_site." + capability))
    )


def require(capability):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not can(request.user, capability):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
