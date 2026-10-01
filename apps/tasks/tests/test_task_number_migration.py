from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.clients.models import Client

BEFORE = [('projects', '0013_project_task_view'), ('tasks', '0010_my_tasks_view')]
AFTER = [('projects', '0016_project_key_unique'), ('tasks', '0013_task_number_unique')]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def _seed(apps):
    Project = apps.get_model('projects', 'Project')
    Status = apps.get_model('projects', 'Status')
    Task = apps.get_model('tasks', 'Task')
    # Clients are untouched by these migrations, so the real model matches the table.
    client = Client.objects.create(name='Acme')
    crm = Project.objects.create(client_id=client.pk, name='Custom CRM')
    twin = Project.objects.create(client_id=client.pk, name='Custom Site')
    empty = Project.objects.create(client_id=client.pk, name='2024')
    status = Status.objects.create(project=crm, name='To Do')
    twin_status = Status.objects.create(project=twin, name='To Do')

    now = timezone.now()
    # Created out of pk order, and two with the same timestamp, so the order is
    # (created_at, pk) and not just pk.
    late = Task.objects.create(project=crm, status=status, title='late')
    early = Task.objects.create(project=crm, status=status, title='early')
    tie_a = Task.objects.create(project=crm, status=status, title='tie a')
    tie_b = Task.objects.create(project=crm, status=status, title='tie b')
    other = Task.objects.create(project=twin, status=twin_status, title='other')
    stamps = {
        late.pk: now,
        early.pk: now - timedelta(days=3),
        tie_a.pk: now - timedelta(days=1),
        tie_b.pk: now - timedelta(days=1),
        other.pk: now,
    }
    for pk, stamp in stamps.items():
        Task.objects.filter(pk=pk).update(created_at=stamp, updated_at=stamp - timedelta(hours=1))
    Project.objects.filter(pk=crm.pk).update(updated_at=now - timedelta(days=9))
    return {
        'crm': crm.pk, 'twin': twin.pk, 'empty': empty.pk,
        'late': late.pk, 'early': early.pk, 'tie_a': tie_a.pk, 'tie_b': tie_b.pk, 'other': other.pk,
    }


def _check_forward(apps, ids):
    Project = apps.get_model('projects', 'Project')
    Task = apps.get_model('tasks', 'Task')
    keys = dict(Project.objects.values_list('pk', 'key'))
    assert keys[ids['crm']] == 'CUST'
    assert keys[ids['twin']] == 'CUST2'
    assert keys[ids['empty']] == f"P{ids['empty']}"

    numbers = dict(Task.objects.values_list('pk', 'number'))
    assert numbers[ids['early']] == 1
    assert numbers[ids['tie_a']] == 2
    assert numbers[ids['tie_b']] == 3
    assert numbers[ids['late']] == 4
    assert numbers[ids['other']] == 1

    counters = dict(Project.objects.values_list('pk', 'task_counter'))
    assert counters == {ids['crm']: 4, ids['twin']: 1, ids['empty']: 0}

    # Numbering does not touch either timestamp.
    early = Task.objects.get(pk=ids['early'])
    assert early.updated_at == early.created_at - timedelta(hours=1)
    crm = Project.objects.get(pk=ids['crm'])
    assert crm.updated_at < timezone.now() - timedelta(days=8)


@pytest.mark.django_db(transaction=True)
def test_the_migrations_give_keys_and_numbers_and_can_go_back_and_forth():
    try:
        ids = _seed(_migrate(BEFORE))

        _check_forward(_migrate(AFTER), ids)

        apps = _migrate(BEFORE)
        Task = apps.get_model('tasks', 'Task')
        assert Task.objects.count() == 5

        _check_forward(_migrate(AFTER), ids)
    finally:
        # Leave the database at the latest schema for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
