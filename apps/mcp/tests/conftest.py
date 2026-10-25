import secrets
from datetime import timedelta

import pytest
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model, set_token_value

from apps.accounts.factories import UserFactory, member_preset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory

ALL_SCOPES = 'tasks:read tasks:write time'


@pytest.fixture
def mcp_preset(db):
    preset = member_preset()
    preset.tasks_mcp = True
    preset.save()
    return preset


@pytest.fixture
def member(mcp_preset):
    return UserFactory(permission_preset=mcp_preset)


@pytest.fixture
def project(member):
    project = ProjectFactory()
    ProjectAccessFactory(project=project, user=member)
    return project


def make_application(name='Claude', redirect_uri='https://claude.ai/api/mcp/auth_callback'):
    Application = get_application_model()
    return Application.objects.create(
        name=name,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=redirect_uri,
        registration_source=Application.RegistrationSource.DCR,
    )


def make_token(user, scope=ALL_SCOPES, application=None, expires_in=3600, resource=None):
    """A raw bearer token for ``user``, stored the way the token endpoint stores it."""
    AccessToken = get_access_token_model()
    raw = secrets.token_urlsafe(30)
    token = AccessToken(
        user=user,
        application=application or make_application(),
        expires=timezone.now() + timedelta(seconds=expires_in),
        scope=scope,
        resource=resource or [],
    )
    set_token_value(token, raw)
    token.save()
    return raw


@pytest.fixture
def bearer(member):
    return make_token(member)


class McpClient:
    """Posts JSON-RPC messages to /mcp with a bearer token."""

    def __init__(self, client, token):
        self.client = client
        self.token = token
        self.next_id = 0

    def post(self, message, **headers):
        if self.token:
            headers.setdefault('HTTP_AUTHORIZATION', f'Bearer {self.token}')
        return self.client.post('/mcp', data=message, content_type='application/json', **headers)

    def rpc(self, method, params=None):
        self.next_id += 1
        response = self.post({'jsonrpc': '2.0', 'id': self.next_id, 'method': method, 'params': params or {}})
        assert response.status_code == 200, response.content
        return response.json()

    def call(self, tool, /, **arguments):
        body = self.rpc('tools/call', {'name': tool, 'arguments': arguments})
        return body['result']


@pytest.fixture
def mcp(client, bearer):
    return McpClient(client, bearer)
