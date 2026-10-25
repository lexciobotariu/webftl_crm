from django import template

from ..oauth import can_use_mcp, mcp_url
from ..views import connected_apps

register = template.Library()


@register.inclusion_tag('mcp/connected_apps.html', takes_context=True)
def connected_apps_section(context):
    request = context['request']
    return {
        'request': request,
        'csrf_token': context.get('csrf_token'),
        'allowed': can_use_mcp(request.user),
        'rows': connected_apps(request.user),
        'mcp_url': mcp_url(request),
    }
