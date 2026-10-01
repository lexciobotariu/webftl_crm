import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.clients.models import Client

BEFORE = [('projects', '0016_project_key_unique'), ('tasks', '0016_task_closed_at_data')]
AFTER = [('projects', '0016_project_key_unique'), ('tasks', '0019_remove_task_time_estimate')]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def _project(apps):
    Project = apps.get_model('projects', 'Project')
    Status = apps.get_model('projects', 'Status')
    client = Client.objects.create(name='Acme')
    project = Project.objects.create(client_id=client.pk, name='Custom CRM')
    return project, Status.objects.create(project=project, name='To Do')


def _make(apps, project, status, number, **fields):
    Task = apps.get_model('tasks', 'Task')
    return Task.objects.create(project=project, status=status, title=f't{number}', number=number, **fields).pk


@pytest.mark.django_db(transaction=True)
def test_estimate_hours_become_minutes_and_back():
    try:
        apps = _migrate(BEFORE)
        project, status = _project(apps)
        four = _make(apps, project, status, 1, time_estimate=4)
        zero = _make(apps, project, status, 2, time_estimate=0)
        none = _make(apps, project, status, 3)
        absurd = _make(apps, project, status, 4, time_estimate=2_000_000_000)

        apps = _migrate(AFTER)
        Task = apps.get_model('tasks', 'Task')
        minutes = dict(Task.objects.values_list('pk', 'estimate_minutes'))
        assert minutes[four] == 240
        assert minutes[zero] is None
        assert minutes[none] is None
        assert minutes[absurd] == 1000 * 60

        # An estimate with minutes rounds up to a whole hour on the way back.
        Task.objects.filter(pk=four).update(estimate_minutes=90)
        apps = _migrate(BEFORE)
        Task = apps.get_model('tasks', 'Task')
        hours = dict(Task.objects.values_list('pk', 'time_estimate'))
        assert hours[four] == 2
        assert hours[zero] is None
        assert hours[none] is None
        assert hours[absurd] == 1000

        # Forward again keeps what the round trip left.
        apps = _migrate(AFTER)
        Task = apps.get_model('tasks', 'Task')
        assert Task.objects.get(pk=four).estimate_minutes == 120
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_estimate_migrations_run_both_ways_on_an_empty_table():
    try:
        _migrate(BEFORE)
        _migrate(AFTER)
        _migrate(BEFORE)
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
