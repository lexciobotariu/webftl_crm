from django import template

from apps.tasks.listview import row_keys as _row_keys

register = template.Library()


@register.simple_tag
def row_keys(task, spec):
    """Where the row sits for ``spec``; see :func:`apps.tasks.listview.row_keys`."""
    return _row_keys(task, spec) if spec else ''
