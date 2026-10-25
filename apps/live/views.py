import asyncio
import json

from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIRequest
from django.http import HttpResponse, HttpResponseForbidden, StreamingHttpResponse

from apps.projects.models import ProjectAccess

from .bus import get_hub
from .middleware import clean_tab

HEARTBEAT = 25  # seconds; keeps proxies from closing a quiet connection
LIFETIME = 3600  # seconds; the browser reconnects and permissions are read again


def visible_project_ids(user, project_id=None):
    """Projects whose task changes ``user`` may hear about: ``None`` for every project.

    The same rule as ``visible_tasks`` (apps/tasks/models.py), narrowed to
    ``project_id`` when the page shows a single project.
    """
    if user.is_admin or user.has_app_permission('tasks_view_all'):
        ids = None
    elif user.has_app_permission('access_tasks'):
        ids = set(ProjectAccess.objects.filter(user=user).values_list('project_id', flat=True))
    else:
        ids = set()
    if project_id is not None:
        ids = {project_id} if ids is None or project_id in ids else set()
    return ids


def event_for(payload, project_ids, tab):
    """The text sent to one page for one message, or ``None`` when it is not for that page."""
    try:
        message = json.loads(payload)
    except ValueError:
        return None
    if message.get('resync'):
        return 'event: resync\ndata: {}\n\n'
    if project_ids is not None and message.get('p') not in project_ids:
        return None
    # The tab that made the change already shows it.
    if tab and message.get('tab') == tab:
        return None
    data = json.dumps({'project': message.get('p'), 'task': message.get('t')})
    return f'event: task\ndata: {data}\n\n'


async def stream(project_ids, tab, heartbeat=HEARTBEAT, lifetime=LIFETIME):
    hub = get_hub()
    queue = hub.subscribe()
    loop = asyncio.get_running_loop()
    try:
        # Sent at once so the browser knows it is connected; retry is its reconnect delay.
        yield 'retry: 5000\nevent: ready\ndata: {}\n\n'
        deadline = loop.time() + lifetime
        while loop.time() < deadline:
            try:
                payload = await asyncio.wait_for(queue.get(), heartbeat)
            except TimeoutError:
                yield ': ping\n\n'
                continue
            event = event_for(payload, project_ids, tab)
            if event:
                yield event
    finally:
        hub.unsubscribe(queue)


async def task_events(request):
    """Server-sent events for the task pages: one ``task`` event per changed task.

    ``?project=<id>`` limits it to one project; ``?tab=<id>`` is the page's own
    tab, whose changes are left out. Needs the ASGI server (uvicorn): under
    plain WSGI (``runserver``) it answers 204 and the page stays as it is.
    """
    if not isinstance(request, ASGIRequest):
        return HttpResponse(status=204)
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=401)
    try:
        project_id = int(request.GET['project']) if request.GET.get('project') else None
    except ValueError:
        project_id = None
    project_ids = await sync_to_async(visible_project_ids)(user, project_id)
    if project_ids is not None and not project_ids:
        return HttpResponseForbidden("You don't have access to tasks")
    response = StreamingHttpResponse(
        stream(project_ids, clean_tab(request.GET.get('tab', ''))),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
