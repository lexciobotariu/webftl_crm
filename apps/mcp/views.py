import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_grant_model,
    get_refresh_token_model,
)

from apps.tasks.sources import CLAUDE, acting_via

from . import protocol
from .oauth import authenticate, can_use_mcp, resource_metadata_url

REQUESTS_PER_MINUTE = 120
MAX_BODY_BYTES = 1024 * 1024
# How often "last used" is written for one token.
LAST_USED_EVERY = timedelta(minutes=1)


def _unauthorized(request, error=None):
    challenge = f'Bearer resource_metadata="{resource_metadata_url(request)}"'
    if error:
        challenge += f', error="{error}"'
    response = JsonResponse({'error': error or 'unauthorized'}, status=401)
    response['WWW-Authenticate'] = challenge
    return response


def _origin_allowed(request):
    """A browser page may only call us from this app itself (MCP spec: guard against DNS rebinding).

    Claude's servers and Claude Code send no Origin at all.
    """
    origin = request.headers.get('Origin')
    if not origin:
        return True
    return origin.rstrip('/') == request.build_absolute_uri('/').rstrip('/')


def _over_limit(token):
    key = f'mcp-rate:{token.pk}:{int(timezone.now().timestamp() // 60)}'
    cache.add(key, 0, timeout=90)
    try:
        return cache.incr(key) > REQUESTS_PER_MINUTE
    except ValueError:
        return False


def _touch(token):
    if timezone.now() - token.updated > LAST_USED_EVERY:
        type(token).objects.filter(pk=token.pk).update(updated=timezone.now())


@csrf_exempt
def mcp_endpoint(request):
    """Streamable HTTP endpoint, stateless: one JSON-RPC message per POST, one JSON answer."""
    if request.method != 'POST':
        # No server-initiated stream (GET) and no sessions to end (DELETE).
        response = HttpResponse(status=405)
        response['Allow'] = 'POST'
        return response
    if not _origin_allowed(request):
        return JsonResponse({'error': 'origin not allowed'}, status=403)
    if 'HTTP_AUTHORIZATION' not in request.META:
        return _unauthorized(request)
    token = authenticate(request)
    if token is None:
        return _unauthorized(request, 'invalid_token')
    user = token.user
    if not can_use_mcp(user):
        return JsonResponse(
            {'error': 'Your permission preset does not allow using the CRM from Claude.'}, status=403,
        )
    if _over_limit(token):
        response = JsonResponse({'error': 'Too many requests, wait a minute.'}, status=429)
        response['Retry-After'] = '60'
        return response
    version = request.headers.get('MCP-Protocol-Version')
    if version and version not in protocol.PROTOCOL_VERSIONS:
        return JsonResponse({'error': f'Unsupported MCP-Protocol-Version {version}'}, status=400)
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse(protocol.error(None, protocol.INVALID_REQUEST, 'Request too large'), status=413)
    try:
        message = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse(protocol.error(None, protocol.PARSE_ERROR, 'Parse error'), status=400)
    if isinstance(message, list):
        return JsonResponse(protocol.error(None, protocol.INVALID_REQUEST, 'Batches are not supported'), status=400)

    _touch(token)
    request.user = user
    with acting_via(CLAUDE):
        answer = protocol.handle(message, request, user, token.scope.split())
    if answer is None:
        return HttpResponse(status=202)
    return JsonResponse(answer)


def connected_apps(user):
    """Applications that hold a live token for ``user``: name, since, last used, scopes."""
    AccessToken = get_access_token_model()
    RefreshToken = get_refresh_token_model()
    now = timezone.now()
    apps = {}
    for token in AccessToken.objects.filter(user=user, expires__gt=now).select_related('application'):
        apps.setdefault(token.application_id, {'application': token.application, 'tokens': []})['tokens'].append(token)
    for refresh in RefreshToken.objects.filter(user=user, revoked__isnull=True).select_related('application', 'access_token'):
        apps.setdefault(refresh.application_id, {'application': refresh.application, 'tokens': []})
        if refresh.access_token:
            apps[refresh.application_id]['tokens'].append(refresh.access_token)
    rows = []
    for entry in apps.values():
        tokens = entry['tokens']
        rows.append({
            'application': entry['application'],
            'since': min((t.created for t in tokens), default=entry['application'].created),
            'last_used': max((t.updated for t in tokens), default=None),
            'scopes': sorted({scope for t in tokens for scope in t.scope.split()}),
        })
    return sorted(rows, key=lambda row: row['since'])


@login_required
@require_POST
@transaction.atomic
def disconnect(request, client_id):
    """Revoke everything ``client_id`` holds for this person: tokens and pending codes."""
    application = get_application_model().objects.filter(client_id=client_id).first()
    if application is not None:
        get_refresh_token_model().objects.filter(user=request.user, application=application).delete()
        get_access_token_model().objects.filter(user=request.user, application=application).delete()
        get_grant_model().objects.filter(user=request.user, application=application).delete()
        messages.success(request, f'Disconnected {application.name or "the app"}.')
    return redirect('mfa_index')

