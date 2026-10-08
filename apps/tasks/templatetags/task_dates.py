from django import template
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

register = template.Library()


@register.filter
def short_date(value):
    """``Jan 05`` this year, ``Jan 05, 2027`` any other year, as Linear writes a due date."""
    if not value:
        return ''
    if value.year == timezone.localdate().year:
        return date_filter(value, 'M d')
    return date_filter(value, 'M d, Y')
