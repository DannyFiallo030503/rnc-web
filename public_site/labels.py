"""Translate presentation labels without changing source codes or catalogs."""
from django.utils.translation import gettext

def category_label(value):
    value = str(value)
    if value.startswith("Etapa · código "):
        return gettext("Etapa") + " · " + gettext("código") + " " + value.removeprefix("Etapa · código ")
    if " · " in value:
        code, text = value.split(" · ", 1)
        return code + " · " + gettext(text)
    return gettext(value)
