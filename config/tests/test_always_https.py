"""ALWAYS_HTTPS: absolute links use https even when the proxy forwards http."""
import pytest

pytestmark = pytest.mark.django_db


def test_links_follow_the_request_scheme_by_default(client):
    data = client.get('/.well-known/oauth-protected-resource').json()
    assert data['resource'] == 'http://testserver/mcp'


def test_always_https_builds_https_links(client, settings):
    settings.ALWAYS_HTTPS = True
    data = client.get('/.well-known/oauth-protected-resource').json()
    assert data['resource'] == 'https://testserver/mcp'
    assert data['authorization_servers'] == ['https://testserver']
    issuer = client.get('/.well-known/oauth-authorization-server').json()['issuer']
    assert issuer == 'https://testserver'


def test_always_https_wins_over_a_forwarded_http(client, settings):
    settings.ALWAYS_HTTPS = True
    settings.SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    data = client.get('/.well-known/oauth-protected-resource', HTTP_X_FORWARDED_PROTO='http').json()
    assert data['resource'] == 'https://testserver/mcp'
