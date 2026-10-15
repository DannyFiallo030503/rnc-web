"""Administrative role checks shared by views and navigation."""


SUPERADMIN_GROUP = "superadmin"


def has_admin_access(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=SUPERADMIN_GROUP).exists()
