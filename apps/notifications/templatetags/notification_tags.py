from django import template
from django.utils import timezone
from django.utils.dateformat import format as format_date

register = template.Library()


@register.filter
def short_age(value, now=None):
    """How long ago, in a few characters: "now", "5m", "3h", "2d", "Sep 12", "Sep 12, 2025".

    A week or more shows the date, and the year only when it is not this year.
    """
    if not value:
        return ''
    now = now or timezone.now()
    seconds = (now - value).total_seconds()
    if seconds < 60:
        return 'now'
    if seconds < 3600:
        return f'{int(seconds // 60)}m'
    if seconds < 86400:
        return f'{int(seconds // 3600)}h'
    if seconds < 7 * 86400:
        return f'{int(seconds // 86400)}d'
    local = timezone.localtime(value)
    same_year = local.year == timezone.localtime(now).year
    return format_date(local, 'M j' if same_year else 'M j, Y')
