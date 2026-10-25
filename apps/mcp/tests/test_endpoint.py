"""The /mcp endpoint: who gets in, and the JSON-RPC conversation."""
import pytest

from apps.accounts.factories import UserFactory
from apps.mcp import protocol

from .conftest import McpClient, make_token

pytestmark = pytest.mark.django_db


class TestAccess:
    def test_no_token_is_401_pointing_to_the_metadata(self, client):
        response = McpClient(client, None).post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        assert response.status_code == 401
        assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in response['WWW-Authenticate']

    def test_unknown_token_is_401_invalid_token(self, client, member):
        response = McpClient(client, 'nope').post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        assert response.status_code == 401
        assert 'invalid_token' in response['WWW-Authenticate']

    def test_expired_token_is_refused(self, client, member):
        token = make_token(member, expires_in=-10)
        assert McpClient(client, token).post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).status_code == 401

    def test_token_for_another_resource_is_refused(self, client, member):
        token = make_token(member, resource=['https://elsewhere.example/mcp'])
        assert McpClient(client, token).post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).status_code == 401

    def test_token_for_this_endpoint_is_accepted(self, client, member):
        token = make_token(member, resource=['http://testserver/mcp'])
        assert McpClient(client, token).rpc('ping')['result'] == {}

    def test_token_in_the_query_string_is_not_read(self, client, bearer):
        response = client.post(f'/mcp?access_token={bearer}', data={}, content_type='application/json')
        assert response.status_code == 401

    def test_deactivated_person_is_refused(self, client, member, bearer):
        member.is_active = False
        member.save()
        assert McpClient(client, bearer).post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).status_code == 401

    def test_preset_without_the_flag_is_403(self, client):
        token = make_token(UserFactory())
        assert McpClient(client, token).post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).status_code == 403

    def test_foreign_origin_is_refused(self, mcp):
        response = mcp.post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, HTTP_ORIGIN='https://evil.example')
        assert response.status_code == 403

    def test_own_origin_is_fine(self, mcp):
        response = mcp.post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, HTTP_ORIGIN='http://testserver')
        assert response.status_code == 200

    def test_get_is_405(self, client, bearer):
        response = client.get('/mcp', HTTP_AUTHORIZATION=f'Bearer {bearer}')
        assert response.status_code == 405
        assert response['Allow'] == 'POST'

    def test_rate_limit(self, mcp, monkeypatch):
        from apps.mcp import views

        monkeypatch.setattr(views, 'REQUESTS_PER_MINUTE', 2)
        mcp.rpc('ping')
        mcp.rpc('ping')
        response = mcp.post({'jsonrpc': '2.0', 'id': 9, 'method': 'ping'})
        assert response.status_code == 429


class TestProtocol:
    def test_initialize_negotiates_the_version(self, mcp):
        body = mcp.rpc('initialize', {
            'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'},
        })
        assert body['result']['protocolVersion'] == '2025-06-18'
        assert body['result']['capabilities'] == {'tools': {'listChanged': False}}
        assert body['result']['serverInfo']['name'] == 'webftl-crm'

    def test_instructions_tell_claude_to_write_as_the_person(self, mcp):
        instructions = mcp.rpc('initialize', {'protocolVersion': '2025-06-18'})['result']['instructions']
        assert 'first person' in instructions
        assert 'progress notes' in instructions

    def test_unknown_version_gets_the_newest(self, mcp):
        body = mcp.rpc('initialize', {'protocolVersion': '1999-01-01'})
        assert body['result']['protocolVersion'] == protocol.PROTOCOL_VERSIONS[0]

    def test_notification_is_202_without_body(self, mcp):
        response = mcp.post({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        assert response.status_code == 202
        assert response.content == b''

    def test_unsupported_protocol_header_is_400(self, mcp):
        response = mcp.post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, HTTP_MCP_PROTOCOL_VERSION='1999-01-01')
        assert response.status_code == 400

    def test_bad_json_is_a_parse_error(self, client, bearer):
        response = client.post('/mcp', data='{', content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {bearer}')
        assert response.status_code == 400
        assert response.json()['error']['code'] == protocol.PARSE_ERROR

    def test_batch_is_refused(self, mcp):
        response = mcp.post([{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}])
        assert response.status_code == 400

    def test_unknown_method(self, mcp):
        assert mcp.rpc('resources/list')['error']['code'] == protocol.METHOD_NOT_FOUND

    def test_tools_list_follows_the_scopes(self, client, member):
        everything = McpClient(client, make_token(member)).rpc('tools/list')['result']['tools']
        read_only = McpClient(client, make_token(member, scope='tasks:read')).rpc('tools/list')['result']['tools']
        assert {'create_task', 'start_work', 'log_time'} <= {tool['name'] for tool in everything}
        names = {tool['name'] for tool in read_only}
        assert 'get_task' in names and 'create_task' not in names and 'start_timer' not in names
        assert all(tool['annotations']['readOnlyHint'] for tool in read_only)
        assert all(tool['inputSchema']['type'] == 'object' for tool in everything)

    def test_calling_a_tool_outside_the_scopes_is_a_tool_error(self, client, member, project):
        mcp = McpClient(client, make_token(member, scope='tasks:read'))
        result = mcp.call('create_task', project=project.key, title='x')
        assert result['isError'] is True

    def test_unknown_tool_is_invalid_params(self, mcp):
        body = mcp.rpc('tools/call', {'name': 'drop_tables', 'arguments': {}})
        assert body['error']['code'] == protocol.INVALID_PARAMS

    def test_last_used_is_recorded(self, mcp, member):
        from datetime import timedelta

        from django.utils import timezone
        from oauth2_provider.models import get_access_token_model

        AccessToken = get_access_token_model()
        AccessToken.objects.filter(user=member).update(updated=timezone.now() - timedelta(hours=1))
        mcp.rpc('ping')
        assert AccessToken.objects.get(user=member).updated > timezone.now() - timedelta(minutes=1)
