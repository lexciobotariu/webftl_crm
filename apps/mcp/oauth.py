"""Signing Claude in: OAuth 2.1 with this app as the authorization server.

django-oauth-toolkit does the protocol (authorization code + PKCE, refresh
token rotation, hashed tokens, RFC 8414 / 9728 metadata, RFC 7591 dynamic
client registration). This module holds what is ours: who may register a
client, the consent page, and checking a bearer token on the MCP endpoint.
"""
import json
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse
from oauth2_provider.models import get_access_token_model
from oauth2_provider.oauth2_backends import get_oauthlib_core
from oauth2_provider.views import AuthorizationView
from oauth2_provider.views.metadata import OAuthProtectedResourceMetadataView

# Where claude.ai and the Claude apps send the browser back after "Allow".
CLAUDE_REDIRECT_URIS = (
    'https://claude.ai/api/mcp/auth_callback',
    'https://claude.com/api/mcp/auth_callback',
)
# Claude Code (and other desktop clients) listen on a port of this computer.
LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '[::1]')
REGISTRATIONS_PER_HOUR = 20

MCP_PERMISSION = 'tasks_mcp'
REQUIRED_SCOPE = 'tasks:read'


def can_use_mcp(user):
    """Whether ``user`` may connect Claude: the preset flag, or an admin."""
    return user.is_active and user.has_app_permission(MCP_PERMISSION)


def redirect_uri_allowed(uri):
    """Claude's own callbacks, a loopback address (Claude Code), or one listed in MCP_EXTRA_REDIRECT_URIS."""
    if uri in CLAUDE_REDIRECT_URIS or uri in settings.MCP_EXTRA_REDIRECT_URIS:
        return True
    try:
        parts = urlsplit(uri)
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError:
        return False
    host = parts.netloc.rsplit('@', 1)[-1]
    host = re.sub(r':\d+$', '', host)
    return parts.scheme == 'http' and host in LOOPBACK_HOSTS and not parts.username


class AllowListedRedirectsDCRPermission:
    """Anyone may register a client, but only one that sends people back to Claude.

    Registering grants nothing: the person still signs in (with two-factor),
    must have the permission, and has to press Allow. Limiting the redirect
    addresses means a client registered by someone else can never receive a
    code. Registrations are rate limited per IP address.
    """

    def has_permission(self, request):
        try:
            data = json.loads(request.body)
        except (TypeError, ValueError):
            return True  # the view answers "invalid_client_metadata"
        uris = data.get('redirect_uris') if isinstance(data, dict) else None
        if not isinstance(uris, list) or not uris:
            return False
        if not all(isinstance(uri, str) and redirect_uri_allowed(uri) for uri in uris):
            return False
        key = f'mcp-dcr:{request.META.get("REMOTE_ADDR", "")}'
        cache.add(key, 0, timeout=3600)
        try:
            count = cache.incr(key)
        except ValueError:
            count = 1
        return count <= REGISTRATIONS_PER_HOUR


def mcp_url(request):
    return request.build_absolute_uri(reverse('mcp'))


def resource_metadata_url(request):
    return request.build_absolute_uri(reverse('mcp_resource_metadata'))


class ResourceMetadataView(OAuthProtectedResourceMetadataView):
    """RFC 9728: the MCP endpoint is the protected resource, at both well-known paths."""

    def get_resource(self, request):
        return mcp_url(request)

    def get_resource_name(self):
        return 'WebFTL CRM'


class ConsentView(AuthorizationView):
    """The "Allow Claude to …" page, in the app's look.

    Signing in goes through allauth, so two-factor applies; an admin who has
    not set it up is sent to do that first by the 2FA middleware. Someone
    without the permission sees why instead of the form.
    """

    template_name = 'mcp/authorize.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_use_mcp(request.user):
            return render(request, 'mcp/not_allowed.html', status=403)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requested = kwargs.get('scopes') or self.oauth2_data.get('scopes', [])
        context['scope_choices'] = [
            {'name': name, 'description': description, 'required': name == REQUIRED_SCOPE}
            for name, description in settings.OAUTH2_PROVIDER['SCOPES'].items()
            if name in requested
        ]
        return context

    def form_valid(self, form):
        # The person may untick what the client asked for; reading tasks always stays.
        requested = form.cleaned_data.get('scope', '').split()
        ticked = set(self.request.POST.getlist('scope_choice')) | {REQUIRED_SCOPE}
        form.cleaned_data['scope'] = ' '.join(scope for scope in requested if scope in ticked)
        return super().form_valid(form)


def authenticate(request):
    """The valid access token on ``request``, or None.

    The token must be in the Authorization header, unexpired, unrevoked, and
    issued for this endpoint when the client named one (RFC 8707). Its person
    must be active and allowed to use Claude.
    """
    valid, oauth_request = get_oauthlib_core().verify_request(request, scopes=[])
    if not valid:
        return None
    token = oauth_request.access_token
    if not isinstance(token, get_access_token_model()):
        return None
    if not token.allows_audience(mcp_url(request)):
        return None
    if token.user is None or not token.user.is_active:
        return None
    return token
