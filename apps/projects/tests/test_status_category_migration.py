import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.clients.models import Client

BEFORE = [('projects', '0010_status_category')]
AFTER = [('projects', '0011_status_category_data')]


@pytest.mark.django_db(transaction=True)
def test_data_migration_maps_existing_statuses_to_categories():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    try:
        apps = executor.loader.project_state(BEFORE).apps
        Project = apps.get_model('projects', 'Project')
        Status = apps.get_model('projects', 'Status')

        # Clients are untouched by these migrations, so the real model matches the table.
        client = Client.objects.create(name='Acme')
        project = Project.objects.create(client_id=client.pk, name='P')
        expected = {}
        rows = [
            ('Backlog', False, 'backlog'),
            ('backlog', False, 'backlog'),
            ('In Progress', False, 'started'),
            ('Review', False, 'started'),
            ('Doing', False, 'started'),
            ('To Do', False, 'unstarted'),
            ('QA', False, 'unstarted'),
            ('Cancelled', False, 'canceled'),
        ('Canceled', False, 'canceled'),
        ('Done', True, 'completed'),
            ('Shipped', True, 'completed'),
            ('Backlog Done', True, 'completed'),
        ]
        for i, (name, is_done, category) in enumerate(rows):
            if Status.objects.filter(project=project, name=name).exists():
                continue
            Status.objects.create(project=project, name=name, order=i, is_done=is_done)
            expected[name] = category

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        Status = apps.get_model('projects', 'Status')
        got = dict(Status.objects.filter(project_id=project.pk).values_list('name', 'category'))
        assert got == expected

    finally:
        # Leave the database at the latest schema for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
