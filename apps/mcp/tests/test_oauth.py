"""Connecting Claude: discovery, client registration, consent, tokens, disconnecting."""
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_refresh_token_model,
)

from apps.accounts.factories import UserFactory
from apps.mcp.oauth import redirect_uri_allowed

from .conftest import McpClient, make_application, make_token

pytestmark = pytest.mark.django_db

CLAUDE_CALLBACK = 'https://claude.ai/api/mcp/auth_callback'


class TestDiscovery:
    def test_protected_resource_metadata(self, client):
        for path in ('/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/mcp'):
            data = client.get(path).json()
            assert data['resource'] == 'http://testserver/mcp'
            assert data['authorization_servers'] == ['http://testserver']
            assert set(data['scopes_supported']) == {'tasks:read', 'tasks:write', 'time'}

    def test_authorization_server_metadata(self, client):
        data = client.get('/.well-known/oauth-authorization-server').json()
        assert data['issuer'] == 'http://testserver'
        assert data['authorization_endpoint'] == 'http://testserver/oauth/authorize/'
        assert data['token_endpoint'] == 'http://testserver/oauth/token/'
        assert data['registration_endpoint'] == 'http://testserver/oauth/register/'
        assert data['code_challenge_methods_supported'] == ['S256']
        assert data['response_types_supported'] == ['code']
        assert 'none' in data['token_endpoint_auth_methods_supported']


class TestRedirectAllowList:
    @pytest.mark.parametrize('uri', [
        CLAUDE_CALLBACK,
        'https://claude.com/api/mcp/auth_callback',
        'http://localhost:33418/callback',
        'http://127.0.0.1:5000/cb',
        'http://localhost/callback',
    ])
    def test_allowed(self, uri):
        assert redirect_uri_allowed(uri)

    @pytest.mark.parametrize('uri', [
        'https://evil.example/callback',
        'https://claude.ai.evil.example/api/mcp/auth_callback',
        'https://localhost:3000/callback',
        'http://localhost.evil.example/cb',
        'http://user@localhost:80@evil.example/cb',
        'http://localhost:abc/cb',
        'javascript:alert(1)',
    ])
    def test_refused(self, uri):
        assert not redirect_uri_allowed(uri)


def register(client, redirect_uris, **extra):
    return client.post('/oauth/register/', data={
        'client_name': 'Claude', 'redirect_uris': redirect_uris,
        'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
        'token_endpoint_auth_method': 'none', **extra,
    }, content_type='application/json')


class TestRegistration:
    def test_claude_can_register(self, client):
        response = register(client, [CLAUDE_CALLBACK])
        assert response.status_code == 201, response.content
        data = response.json()
        app = get_application_model().objects.get(client_id=data['client_id'])
        assert app.client_type == 'public' and app.name == 'Claude'

    def test_other_redirects_cannot(self, client):
        assert register(client, ['https://evil.example/cb']).status_code == 401
        assert register(client, [CLAUDE_CALLBACK, 'https://evil.example/cb']).status_code == 401
        assert register(client, []).status_code in (400, 401)
        assert not get_application_model().objects.exists()

    def test_registrations_are_rate_limited(self, client, monkeypatch):
        from django.core.cache import cache

        from apps.mcp import oauth

        cache.clear()
        monkeypatch.setattr(oauth, 'REGISTRATIONS_PER_HOUR', 2)
        assert register(client, [CLAUDE_CALLBACK]).status_code == 201
        assert register(client, [CLAUDE_CALLBACK]).status_code == 201
        assert register(client, [CLAUDE_CALLBACK]).status_code == 401


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


def authorize_params(client_id, challenge, scope='tasks:read tasks:write time'):
    return {
        'response_type': 'code', 'client_id': client_id, 'redirect_uri': CLAUDE_CALLBACK,
        'scope': scope, 'state': 'xyz', 'code_challenge': challenge, 'code_challenge_method': 'S256',
        'resource': 'http://testserver/mcp',
    }


class TestConsentAndTokens:
    def test_signed_out_person_is_sent_to_sign_in(self, client):
        app = make_application()
        _, challenge = pkce()
        response = client.get('/oauth/authorize/', authorize_params(app.client_id, challenge))
        assert response.status_code == 302
        assert response['Location'].startswith('/accounts/login/')

    def test_sign_in_form_returns_to_the_consent_page(self, client):
        page = client.get('/accounts/login/', {'next': '/oauth/authorize/?client_id=x'})
        assert b'name="next" value="/oauth/authorize/?client_id=x"' in page.content

    def test_full_flow(self, client, member, project):
        client_id = register(client, [CLAUDE_CALLBACK]).json()['client_id']
        verifier, challenge = pkce()
        client.force_login(member)
        params = authorize_params(client_id, challenge)

        page = client.get('/oauth/authorize/', params)
        assert page.status_code == 200
        assert b'Connect Claude to WebFTL CRM?' in page.content
        assert page.context['scope_choices'][0]['name'] == 'tasks:read'

        form = {**page.context['form'].initial, 'allow': 'Authorize', 'scope_choice': ['tasks:write', 'time']}
        form = {key: value for key, value in form.items() if value is not None}
        response = client.post('/oauth/authorize/', form)
        assert response.status_code == 302
        location = urlsplit(response['Location'])
        assert f'{location.scheme}://{location.netloc}{location.path}' == CLAUDE_CALLBACK
        query = parse_qs(location.query)
        assert query['state'] == ['xyz']

        client.logout()
        tokens = client.post('/oauth/token/', {
            'grant_type': 'authorization_code', 'code': query['code'][0], 'redirect_uri': CLAUDE_CALLBACK,
            'client_id': client_id, 'code_verifier': verifier, 'resource': 'http://testserver/mcp',
        })
        assert tokens.status_code == 200, tokens.content
        tokens = tokens.json()
        assert tokens['expires_in'] == 3600
        assert set(tokens['scope'].split()) == {'tasks:read', 'tasks:write', 'time'}

        mcp = McpClient(client, tokens['access_token'])
        created = mcp.call('create_task', project=project.key, title='From Claude')
        assert created['isError'] is False

        refreshed = client.post('/oauth/token/', {
            'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token'], 'client_id': client_id,
        })
        assert refreshed.status_code == 200, refreshed.content
        assert refreshed.json()['refresh_token'] != tokens['refresh_token']
        # The old access token died with the rotation; reusing the old refresh token fails.
        assert client.post('/oauth/token/', {
            'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token'], 'client_id': client_id,
        }).status_code == 400

    def test_unticked_scopes_are_not_granted(self, client, member):
        app = make_application()
        verifier, challenge = pkce()
        client.force_login(member)
        page = client.get('/oauth/authorize/', authorize_params(app.client_id, challenge))
        form = {k: v for k, v in page.context['form'].initial.items() if v is not None}
        response = client.post('/oauth/authorize/', {**form, 'allow': 'Authorize'})  # nothing ticked
        code = parse_qs(urlsplit(response['Location']).query)['code'][0]
        tokens = client.post('/oauth/token/', {
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CALLBACK,
            'client_id': app.client_id, 'code_verifier': verifier,
        }).json()
        assert tokens['scope'] == 'tasks:read'

    def test_without_pkce_is_refused(self, client, member):
        app = make_application()
        client.force_login(member)
        params = authorize_params(app.client_id, 'x')
        del params['code_challenge'], params['code_challenge_method']
        response = client.get('/oauth/authorize/', params)
        assert response.status_code in (302, 400)
        if response.status_code == 302:
            assert 'error=' in response['Location']

    def test_unregistered_redirect_is_refused(self, client, member):
        app = make_application()
        _, challenge = pkce()
        client.force_login(member)
        params = {**authorize_params(app.client_id, challenge), 'redirect_uri': 'https://evil.example/cb'}
        response = client.get('/oauth/authorize/', params)
        assert response.status_code == 400

    def test_person_without_the_flag_sees_why(self, client):
        app = make_application()
        _, challenge = pkce()
        client.force_login(UserFactory())
        response = client.get('/oauth/authorize/', authorize_params(app.client_id, challenge))
        assert response.status_code == 403
        assert b'Use from Claude' in response.content


class TestConnectedApps:
    def test_security_page_lists_and_disconnects(self, client, member):
        make_token(member)
        client.force_login(member)
        page = client.get('/accounts/2fa/')
        assert b'Connected apps' in page.content and b'Claude' in page.content
        assert b'http://testserver/mcp' in page.content

        app = get_application_model().objects.get()
        response = client.post(f'/security/connected-apps/{app.client_id}/disconnect/')
        assert response.status_code == 302
        assert not get_access_token_model().objects.filter(user=member).exists()
        assert not get_refresh_token_model().objects.filter(user=member).exists()

    def test_disconnect_touches_only_my_tokens(self, client, member):
        other = UserFactory()
        app = make_application()
        make_token(member, application=app)
        make_token(other, application=app)
        client.force_login(member)
        client.post(f'/security/connected-apps/{app.client_id}/disconnect/')
        assert get_access_token_model().objects.filter(user=other).exists()

    def test_security_page_without_the_flag(self, client):
        client.force_login(UserFactory())
        assert b'Use from Claude' in client.get('/accounts/2fa/').content
