from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.clients.models import Client
from apps.tasks.factories import TaskFactory, TimeEntryFactory

BEFORE = [('projects', '0016_project_key_unique'), ('tasks', '0019_remove_task_time_estimate')]
AFTER = [('projects', '0016_project_key_unique'), ('tasks', '0022_timeentry_created_at_required')]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_existing_entries_are_dated_by_their_end_or_else_their_start():
    try:
        apps = _migrate(BEFORE)
        Project = apps.get_model('projects', 'Project')
        Status = apps.get_model('projects', 'Status')
        Task = apps.get_model('tasks', 'Task')
        TimeEntry = apps.get_model('tasks', 'TimeEntry')
        User = apps.get_model('accounts', 'User')
        client = Client.objects.create(name='Acme')
        project = Project.objects.create(client_id=client.pk, name='Custom CRM')
        status = Status.objects.create(project=project, name='To Do')
        task = Task.objects.create(project=project, status=status, title='t', number=1)
        user = User.objects.create(email='a@example.com', name='A')
        other = User.objects.create(email='b@example.com', name='B')
        start = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
        closed = TimeEntry.objects.create(task=task, user=user, started_at=start, ended_at=start + timedelta(hours=2))
        running = TimeEntry.objects.create(task=task, user=other, started_at=start + timedelta(days=1))

        apps = _migrate(AFTER)
        TimeEntry = apps.get_model('tasks', 'TimeEntry')
        stamps = dict(TimeEntry.objects.values_list('pk', 'created_at'))
        assert stamps[closed.pk] == start + timedelta(hours=2)
        assert stamps[running.pk] == start + timedelta(days=1)

        # And back and forth again.
        _migrate(BEFORE)
        apps = _migrate(AFTER)
        assert apps.get_model('tasks', 'TimeEntry').objects.count() == 2
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
def test_a_new_entry_is_dated_when_it_is_logged_not_by_the_day_it_is_for():
    yesterday = timezone.now() - timedelta(days=1)
    entry = TimeEntryFactory(
        task=TaskFactory(), user=UserFactory(),
        started_at=yesterday, ended_at=yesterday + timedelta(hours=1),
    )
    assert timezone.now() - entry.created_at < timedelta(minutes=1)
