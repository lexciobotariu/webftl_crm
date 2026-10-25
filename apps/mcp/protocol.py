"""The MCP protocol over Streamable HTTP, in its stateless form.

Every request is one JSON-RPC message in a POST; the answer is one JSON body
(no event stream, no ``Mcp-Session-Id``). That is all the tools need, and it
runs on the app's ordinary sync workers. Spec: modelcontextprotocol.io.
"""
import json
import logging

from config.context_processors import version

from . import tools

logger = logging.getLogger(__name__)

# Newest first. A client asking for one of these gets it back; any other gets the newest.
PROTOCOL_VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26')

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

INSTRUCTIONS = (
    'WebFTL CRM: the agency\'s projects and tasks. Tasks have ids like CUST-12 (project key + '
    'number). Call get_project for a project\'s statuses, labels and people before creating or '
    'moving tasks. start_work / finish_work take a task from start to done with the timer.\n\n'
    'You act as the signed-in person: everything you write is shown under their name, marked '
    '"via Claude", and read by their colleagues. So:\n'
    '- Write tasks, descriptions and comments in the first person, as that person would. Never '
    'mention them in the third person or retell your conversation with them ("X asked", '
    '"after X\'s OK", "as the user requested").\n'
    '- When the person changes what a task is about, update the description, fields and '
    'subtasks directly. Do not comment on the change and do not keep a history of requests in '
    'the description; the activity log already records changes.\n'
    '- Comment only when a colleague needs to know something: the result (what was delivered, '
    'a link to it, anything others must do), a blocker, or a decision that affects others. '
    'Usually one comment when the work is done. No progress notes ("waiting for CI", "tests '
    'pass locally"), no echo of a field you just changed.\n'
    '- Write in the language the task is written in.'
)


def error(message_id, code, message):
    return {'jsonrpc': '2.0', 'id': message_id, 'error': {'code': code, 'message': message}}


def result(message_id, value):
    return {'jsonrpc': '2.0', 'id': message_id, 'result': value}


def handle(message, request, user, scopes):
    """Answer one JSON-RPC message. Returns the response dict, or None for a notification."""
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
        return error(message.get('id') if isinstance(message, dict) else None, INVALID_REQUEST, 'Invalid request')
    method = message['method']
    if 'id' not in message:
        # notifications/initialized, notifications/cancelled, ...: nothing to answer.
        return None
    message_id = message['id']
    params = message.get('params') or {}
    if not isinstance(params, dict):
        return error(message_id, INVALID_PARAMS, 'params must be an object')

    if method == 'initialize':
        return result(message_id, _initialize(params))
    if method == 'ping':
        return result(message_id, {})
    if method == 'tools/list':
        return result(message_id, {'tools': [tool.definition() for tool in tools.tools_for(scopes)]})
    if method == 'tools/call':
        return _call(message_id, params, request, user, scopes)
    return error(message_id, METHOD_NOT_FOUND, f'Method not found: {method}')


def _initialize(params):
    asked = params.get('protocolVersion')
    return {
        'protocolVersion': asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': {'name': 'webftl-crm', 'title': 'WebFTL CRM', 'version': version(None)['app_version']},
        'instructions': INSTRUCTIONS,
    }


def _call(message_id, params, request, user, scopes):
    name = params.get('name')
    tool = tools.TOOLS_BY_NAME.get(name) if isinstance(name, str) else None
    if tool is None:
        return error(message_id, INVALID_PARAMS, f'Unknown tool: {name}')
    if not set(tool.scopes) <= set(scopes):
        return result(message_id, _tool_error(
            f'This connection was not given access for {name}. Reconnect and allow it.'
        ))
    try:
        value = tools.call(tool, request, user, params.get('arguments'))
    except tools.ToolError as refusal:
        return result(message_id, _tool_error(str(refusal)))
    except Exception:
        logger.exception('MCP tool %s failed', name)
        return result(message_id, _tool_error('Something went wrong on the CRM side; nothing more is known.'))
    return result(message_id, {
        'content': [{'type': 'text', 'text': _as_text(value)}],
        'structuredContent': value,
        'isError': False,
    })


def _tool_error(message):
    return {'content': [{'type': 'text', 'text': message}], 'isError': True}


def _as_text(value):
    return json.dumps(value, ensure_ascii=False, indent=1, default=str)
