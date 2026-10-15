from __future__ import annotations

from django import template

from interactive_templates.text import count_label

register = template.Library()


@register.filter
def ru_count(value, forms: str) -> str:
    """{{ points|ru_count:"балл,балла,баллов" }} → «10 баллов»."""
    one, few, many = (form.strip() for form in forms.split(","))
    try:
        number = int(value)
    except (TypeError, ValueError):
        return f"{value} {many}"
    return count_label(number, one, few, many)
