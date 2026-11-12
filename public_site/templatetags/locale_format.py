"""Number formatting filters for user-facing, locale-aware tables."""

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def localized_number(value, decimal_places=0):
    """Format a number with the active locale and grouped thousands."""
    if value is None:
        return "—"
    try:
        places = int(decimal_places)
        return number_format(
            value,
            decimal_pos=places,
            use_l10n=True,
            force_grouping=True,
        )
    except (TypeError, ValueError):
        return value
