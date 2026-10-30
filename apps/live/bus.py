"""Tells open task pages that a task changed, whoever changed it.

``publish`` is called from the task signals (apps/tasks/signals.py), so a change
made in the app, through Claude (MCP), by the GitHub webhook or by a management
command all go the same way. The message only names the project and the task;
the page then re-fetches what it shows through the normal views and their
permission checks.

Two carriers, chosen by ``settings.REDIS_URL``:

- Postgres (default): ``pg_notify`` inside the saving transaction. Postgres
  delivers it only if the transaction commits, and once per transaction even
  when a task and its activity rows change together.
- Redis: pub/sub after the commit. Used when REDIS_URL is set, nothing else changes.

Each server process keeps one listening connection while at least one page is
connected (``Hub``) and hands every message to the streams open in that process
(apps/live/views.py).
"""
import asyncio
import json
import logging
from contextvars import ContextVar

from django.conf import settings
from django.db import connections, transaction

logger = logging.getLogger(__name__)

CHANNEL = 'task_events'
# Sent to the pages after the listening connection was lost and came back:
# whatever changed in between was missed, so they reload what they show.
RESYNC = '{"resync":1}'

# The browser tab that sent the current request (apps/live/middleware.py).
origin_tab = ContextVar('live_origin_tab', default='')


def publish(project_id, task_id, whole=False):
    """Announce that ``task_id`` on ``project_id`` changed. Never raises.

    ``whole``: the change can move the task or change counts elsewhere on the page
    (created, deleted, new status), so pages reload the whole view rather than the
    one row. The pages then also hear the same task without it, which is harmless.
    """
    if not project_id:
        return
    message = {'p': project_id, 't': task_id, 'tab': origin_tab.get()}
    if whole:
        message['w'] = 1
    payload = json.dumps(message, separators=(',', ':'))
    if getattr(settings, 'REDIS_URL', ''):
        transaction.on_commit(lambda: _redis_publish(payload))
        return
    connection = connections['default']
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_notify(%s, %s)', [CHANNEL, payload])


def _redis_publish(payload):
    try:
        _redis_client().publish(CHANNEL, payload)
    except Exception:
        logger.exception('Could not publish a live update to Redis')


_redis = None


def _redis_client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    return _redis


# --- Listening ---------------------------------------------------------------

CONNECTED = object()


def _postgres_params():
    db = connections['default'].settings_dict
    params = {
        'dbname': db['NAME'],
        'user': db.get('USER') or None,
        'password': db.get('PASSWORD') or None,
        'host': db.get('HOST') or None,
        'port': db.get('PORT') or None,
    }
    # Connection options such as sslmode; Django's own keys are not libpq's.
    django_only = {'pool', 'server_side_binding', 'isolation_level', 'assume_role', 'cursor_factory', 'context'}
    params.update({k: v for k, v in (db.get('OPTIONS') or {}).items() if k not in django_only})
    return {k: v for k, v in params.items() if v is not None}


async def _postgres_messages(check_every=60):
    import psycopg
    conn = await psycopg.AsyncConnection.connect(autocommit=True, **_postgres_params())
    async with conn:
        await conn.execute(f'LISTEN {CHANNEL}')
        yield CONNECTED
        while True:
            async for notify in conn.notifies(timeout=check_every):
                yield notify.payload
            # Quiet for a while: make sure the connection is still alive, so a
            # silently dropped one is noticed and replaced.
            await conn.execute('SELECT 1')


async def _redis_messages(check_every=60):
    from redis import asyncio as aioredis
    client = aioredis.Redis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        yield CONNECTED
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=check_every)
            if message is None:
                await pubsub.ping()
            elif message['type'] == 'message':
                data = message['data']
                yield data.decode() if isinstance(data, bytes) else data
    finally:
        await pubsub.aclose()
        await client.aclose()


def _messages():
    return _redis_messages() if getattr(settings, 'REDIS_URL', '') else _postgres_messages()


class Hub:
    """The streams open in this process and the one connection feeding them."""

    def __init__(self):
        self.queues = set()
        self.listener = None

    def subscribe(self):
        queue = asyncio.Queue(maxsize=100)
        self.queues.add(queue)
        if self.listener is None or self.listener.done():
            self.listener = asyncio.get_running_loop().create_task(self._listen())
        return queue

    def unsubscribe(self, queue):
        self.queues.discard(queue)
        # Nobody is looking: close the connection instead of holding it open.
        if not self.queues and self.listener is not None:
            self.listener.cancel()
            self.listener = None

    def deliver(self, payload):
        for queue in list(self.queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A page this far behind reloads anyway once it catches up.
                pass

    async def _listen(self):
        delay = 1
        connected_before = False
        while True:
            try:
                async for message in _messages():
                    if message is CONNECTED:
                        if connected_before:
                            self.deliver(RESYNC)
                        connected_before = True
                        delay = 1
                    else:
                        self.deliver(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Live updates: lost the listening connection, retrying in %ss', delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


_hubs = {}


def get_hub():
    """The hub of the running event loop (one per server process)."""
    loop = asyncio.get_running_loop()
    hub = _hubs.get(loop)
    if hub is None:
        # Forget hubs of loops that are gone (tests start a loop per test).
        for old in [old for old in _hubs if old.is_closed()]:
            del _hubs[old]
        hub = _hubs[loop] = Hub()
    return hub
