"""0.48.0 moves Services' sites and logins into the Vault and turns recurring rules into Repeat."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.clients.models import Client

BEFORE = [
    ('accounts', '0017_access_services'), ('tasks', '0029_recurring_tasks'),
    ('maintenance', '0004_remove_checks'), ('vault', None),
]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state([target for target in targets if target[1]]).apps


def _latest():
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    executor.migrate(targets)


@pytest.mark.django_db(transaction=True)
def test_sites_logins_and_rules_survive_the_move():
    try:
        apps = _migrate(BEFORE)
        Project = apps.get_model('projects', 'Project')
        Status = apps.get_model('projects', 'Status')
        Task = apps.get_model('tasks', 'Task')
        Label = apps.get_model('tasks', 'Label')
        RecurringTask = apps.get_model('tasks', 'RecurringTask')
        Site = apps.get_model('maintenance', 'Site')
        SiteCredential = apps.get_model('maintenance', 'SiteCredential')
        PermissionPreset = apps.get_model('accounts', 'PermissionPreset')

        customer = Client.objects.create(name='Acme')
        project = Project.objects.create(client_id=customer.pk, name='Care plan', task_counter=1)
        todo = Status.objects.create(project=project, name='To Do', order=0)
        done = Status.objects.create(project=project, name='Done', order=1, category='completed')
        label = Label.objects.create(project=project, name='Care', color='#000000')

        checks = RecurringTask.objects.create(
            project=project, title='Checks', frequency='monthly', start_date=date(2026, 11, 1),
            next_date=date(2026, 12, 1), add_date_to_title=True,
        )
        Task.objects.create(project=project, number=1, status=done, title='Checks November 2026',
                            recurring=checks, recurring_date=date(2026, 11, 1))
        posts = RecurringTask.objects.create(
            project=project, title='Social posts', description='Three posts', checklist='Write\n\nSchedule',
            frequency='weekly', weekdays='0', start_date=date(2026, 11, 23), next_date=date(2026, 11, 23),
            due_after_days=2, priority='high', estimate_minutes=60, billable=False, status=done,
        )
        posts.labels.set([label])
        paused = RecurringTask.objects.create(
            project=project, title='Old', frequency='daily', start_date=date(2026, 1, 1), paused=True,
        )
        site = Site.objects.create(client_id=customer.pk, name='Shop', url='https://shop.test', platform='WordPress',
                                   hosting='Hetzner', domain_expires=date(2027, 3, 1), notes='Child theme')
        SiteCredential.objects.create(site=site, label='WP admin', url='https://shop.test/wp-admin',
                                      username='ada', password='pa55', notes='2FA on')
        PermissionPreset.objects.filter(name='Admin').update(access_services=True)

        _latest()

        from apps.accounts.permissions import PermissionPreset as Preset
        from apps.tasks.models import RecurringTask as Rule
        from apps.tasks.models import Task as CurrentTask
        from apps.vault.models import VaultEntry

        assert Preset.objects.get(name='Admin').access_vault is True
        assert Preset.objects.get(name='Developer').access_vault is False

        assert CurrentTask.objects.get(number=1).title == 'Checks'
        assert set(Rule.objects.values_list('pk', flat=True)) == {checks.pk, posts.pk}
        assert not Rule.objects.filter(pk=paused.pk).exists()
        first = CurrentTask.objects.get(recurring_id=posts.pk)
        assert first.title == 'Social posts' and first.description == 'Three posts'
        assert first.status_id == done.pk and first.priority == 'high' and first.billable is False
        assert first.start_date == date(2026, 11, 23) and first.due_date == date(2026, 11, 25)
        assert first.recurring_date == date(2026, 11, 23) and first.number == 2
        assert list(first.labels.values_list('pk', flat=True)) == [label.pk]
        assert list(first.subtasks.order_by('order').values_list('title', flat=True)) == ['Write', 'Schedule']
        assert CurrentTask.objects.get(pk=first.pk).project.task_counter == 2

        note, login = VaultEntry.objects.order_by('pk')
        assert (note.kind, note.title, note.url) == ('note', 'Shop', 'https://shop.test')
        assert 'Platform: WordPress' in note.notes and 'Domain expires: 1 Mar 2027' in note.notes
        assert note.notes.endswith('Child theme')
        assert (login.kind, login.title, login.url) == ('login', 'Shop · WP admin', 'https://shop.test/wp-admin')
        assert (login.username, login.password, login.notes) == ('ada', 'pa55', '2FA on')
        assert todo.pk
    finally:
        _latest()
