from django import template

register = template.Library()


@register.simple_tag
def field_control(field):
    ids = []
    if field.help_text:
        ids.append(field.auto_id + "_help")
    ids.append(field.auto_id + "_error")
    attrs = {
        "aria-describedby": " ".join(ids),
        "data-label": field.label,
        "aria-invalid": "true" if field.errors else "false",
    }
    return field.as_widget(attrs=attrs)
