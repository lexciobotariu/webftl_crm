import asyncio
import json
from unittest import mock

import pytest
from asgiref.sync import sync_to_async
from django.db import connections, transaction
from django.test import AsyncClient
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.live import bus
from apps.live.middleware import clean_tab
from apps.live.views import event_for, stream, visible_project_ids
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory, TimeEntryFactory
from apps.tasks.services import add_comment


def _member(**flags):
    fields = {'access_tasks': True, 'tasks_view_all': False}
    fields.update(flags)
    preset = PermissionPreset.objects.create(name=f'Live {len(flags)} {flags}', **fields)
    return UserFactory(permission_preset=preset)


# --- What is announced ---------------------------------------------------------

@pytest.mark.django_db
class TestAnnounced:
    """Every change to a task or its parts names the task and its project."""

    @pytest.fixture
    def published(self):
        with mock.patch('apps.tasks.signals.publish') as publish:
            yield publish

    def test_task_saved_and_deleted(self, published):
        task = TaskFactory()
        published.assert_any_call(task.project_id, task.pk)
        published.reset_mock()
        pk, project_id = task.pk, task.project_id
        task.delete()
        published.assert_any_call(project_id, pk)

    def test_comment_subtask_time_and_labels(self, published):
        task = TaskFactory()
        user = AdminUserFactory()
        for change in (
            lambda: add_comment(task, 'Hello', user),
            lambda: SubtaskFactory(task=task),
            lambda: TimeEntryFactory(task=task, user=user),
            lambda: task.labels.add(LabelFactory(project=task.project)),
        ):
            published.reset_mock()
            change()
            published.assert_any_call(task.project_id, task.pk)

    def test_label_changed_from_the_label_side(self, published):
        task = TaskFactory()
        label = LabelFactory(project=task.project)
        published.reset_mock()
        label.tasks.add(task)
        published.assert_any_call(task.project_id, task.pk)


@pytest.mark.django_db(transaction=True)
def test_postgres_delivers_on_commit_once_per_task():
    """One message per task and transaction, sent only when it commits, with the tab that made it."""
    task = TaskFactory()

    async def scenario():
        hub = bus.get_hub()
        queue = hub.subscribe()
        try:
            await asyncio.sleep(0.5)  # the listener connects

            def change():
                token = bus.origin_tab.set('tab-1')
                try:
                    with transaction.atomic():
                        add_comment(task, 'One', task.assignee or AdminUserFactory())
                        task.title = 'Changed'
                        task.save()
                    try:
                        with transaction.atomic():
                            task.title = 'Rolled back'
                            task.save()
                            raise RuntimeError
                    except RuntimeError:
                        pass
                finally:
                    bus.origin_tab.reset(token)
                    connections.close_all()

            await asyncio.to_thread(change)
            first = await asyncio.wait_for(queue.get(), 5)
            await asyncio.sleep(0.5)
            return first, queue.qsize()
        finally:
            hub.unsubscribe(queue)

    first, more = asyncio.run(scenario())
    assert json.loads(first) == {'p': task.project_id, 't': task.pk, 'tab': 'tab-1'}
    assert more == 0


# --- Who hears what -------------------------------------------------------------

@pytest.mark.django_db
class TestVisibleProjects:
    def test_admin_and_view_all_hear_every_project(self):
        assert visible_project_ids(AdminUserFactory()) is None
        assert visible_project_ids(_member(tasks_view_all=True)) is None

    def test_member_hears_only_projects_with_access(self):
        member = _member()
        mine, other = ProjectFactory(), ProjectFactory()
        ProjectAccessFactory(project=mine, user=member)
        assert visible_project_ids(member) == {mine.pk}
        assert visible_project_ids(member, mine.pk) == {mine.pk}
        assert visible_project_ids(member, other.pk) == set()

    def test_without_tasks_access_nothing(self):
        member = _member(access_tasks=False)
        ProjectAccessFactory(project=ProjectFactory(), user=member)
        assert visible_project_ids(member) == set()


def test_event_for_filters_project_and_own_tab():
    payload = json.dumps({'p': 3, 't': 9, 'tab': 'abc'})
    assert event_for(payload, None, 'other') == 'event: task\ndata: {"project": 3, "task": 9}\n\n'
    assert event_for(payload, {3}, '') is not None
    assert event_for(payload, {4}, '') is None
    assert event_for(payload, None, 'abc') is None
    assert event_for(bus.RESYNC, set(), 'abc') == 'event: resync\ndata: {}\n\n'
    assert event_for('not json', None, '') is None


def test_clean_tab():
    assert clean_tab('0f8c2b1e-1d2c-4a5b-9e8f-0123456789ab') == '0f8c2b1e-1d2c-4a5b-9e8f-0123456789ab'
    assert clean_tab('bad tab\n') == ''
    assert clean_tab(None) == ''


def test_stream_sends_ready_heartbeat_and_matching_events():
    async def scenario():
        hub = bus.get_hub()
        with mock.patch.object(bus.Hub, '_listen', new=lambda self: asyncio.sleep(3600)):
            chunks = stream({1}, 'mine', heartbeat=0.05, lifetime=1)
            out = [await anext(chunks)]
            hub.deliver(json.dumps({'p': 2, 't': 5, 'tab': ''}))
            hub.deliver(json.dumps({'p': 1, 't': 6, 'tab': 'mine'}))
            hub.deliver(json.dumps({'p': 1, 't': 7, 'tab': 'theirs'}))
            out.append(await anext(chunks))
            out.append(await anext(chunks))
            await chunks.aclose()
            return out, len(hub.queues), hub.listener

    out, open_queues, listener = asyncio.run(scenario())
    assert out[0].startswith('retry: 5000\nevent: ready')
    assert out[1] == 'event: task\ndata: {"project": 1, "task": 7}\n\n'
    assert out[2] == ': ping\n\n'
    # The page left: nothing is held open for it.
    assert open_queues == 0 and listener is None


# --- The endpoint ---------------------------------------------------------------

@pytest.mark.django_db
class TestEndpoint:
    def test_plain_wsgi_answers_no_content(self, client):
        client.force_login(AdminUserFactory())
        assert client.get(reverse('live_task_events')).status_code == 204

    @pytest.mark.django_db(transaction=True)
    def test_asgi(self):
        member = _member()
        mine, other = ProjectFactory(), ProjectFactory()
        ProjectAccessFactory(project=mine, user=member)
        url = reverse('live_task_events')

        async def scenario():
            anonymous = await AsyncClient().get(url)
            client = AsyncClient()
            await client.aforce_login(member)
            refused = await client.get(f'{url}?project={other.pk}')
            with mock.patch.object(bus.Hub, '_listen', new=lambda self: asyncio.sleep(3600)):
                response = await client.get(f'{url}?project={mine.pk}&tab=t1')
                first = await anext(aiter(response.streaming_content))
                await response.streaming_content.aclose()
            # The test client leaves request_finished's connection cleanup off.
            await sync_to_async(connections.close_all)()
            return anonymous.status_code, refused.status_code, response, first

        anonymous, refused, response, first = asyncio.run(scenario())
        assert anonymous == 401
        assert refused == 403
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/event-stream'
        assert response['Cache-Control'] == 'no-cache'
        assert first.startswith(b'retry: 5000')


# --- Redis carrier (only where a Redis server is running) ------------------------

def _redis_up():
    try:
        import redis
        return redis.Redis(socket_connect_timeout=0.2).ping()
    except Exception:
        return False


@pytest.mark.skipif(not _redis_up(), reason='no local Redis')
@pytest.mark.django_db(transaction=True)
def test_redis_carrier(settings):
    settings.REDIS_URL = 'redis://localhost:6379/15'
    bus._redis = None
    task = TaskFactory()

    async def scenario():
        hub = bus.get_hub()
        queue = hub.subscribe()
        try:
            await asyncio.sleep(0.5)

            def change():
                task.title = 'Through Redis'
                task.save()
                connections.close_all()

            await asyncio.to_thread(change)
            return await asyncio.wait_for(queue.get(), 5)
        finally:
            hub.unsubscribe(queue)

    try:
        message = asyncio.run(scenario())
    finally:
        bus._redis = None
    assert json.loads(message)['t'] == task.pk


def test_hub_is_per_event_loop():
    async def hub():
        return bus.get_hub()

    assert asyncio.run(hub()) is not asyncio.run(hub())
