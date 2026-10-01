import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Status
from apps.tasks import services
from apps.tasks.factories import TaskFactory
from apps.tasks.models import Task
from apps.tasks.viewspec import TaskViewOptions, TaskViewSpec


def _status(project, category):
    return project.statuses.get(category=category) if category != Status.CANCELED else (
        project.statuses.create(name='Canceled', category=Status.CANCELED, order=9)
    )


def _done(project):
    return project.statuses.get(category=Status.COMPLETED)


def _todo(project):
    return project.statuses.get(name='To Do')


def _age(task, days):
    """Pretend ``task`` was closed ``days`` days ago."""
    Task.objects.filter(pk=task.pk).update(closed_at=timezone.now() - timedelta(days=days))
    task.refresh_from_db()
    return task


@pytest.mark.django_db
class TestClosedAt:
    def test_creating_a_closed_task_sets_it(self):
        project = ProjectFactory()

        task = TaskFactory(project=project, status=_done(project))

        assert task.closed_at is not None

    def test_closing_sets_it_and_reopening_clears_it(self):
        project = ProjectFactory()
        task = TaskFactory(project=project, status=_todo(project))
        assert task.closed_at is None

        task.status = _done(project)
        task.save()
        closed_at = task.closed_at
        assert closed_at is not None

        task.title = 'still done'
        task.save()
        task.refresh_from_db()
        assert task.closed_at == closed_at

        task.status = _todo(project)
        task.save()
        task.refresh_from_db()
        assert task.closed_at is None

    def test_moving_between_closed_statuses_keeps_the_first_close(self):
        project = ProjectFactory()
        task = _age(TaskFactory(project=project, status=_done(project)), 3)
        first = task.closed_at

        task.status = _status(project, Status.CANCELED)
        task.save()
        task.refresh_from_db()

        assert task.closed_at == first

    def test_a_save_with_update_fields_status_also_writes_closed_at(self):
        project = ProjectFactory()
        task = TaskFactory(project=project, status=_todo(project))

        task.status = _done(project)
        task.save(update_fields=['status'])
        task.refresh_from_db()

        assert task.closed_at is not None

    def test_the_board_move_sets_it(self):
        project = ProjectFactory()
        admin = AdminUserFactory()
        task = TaskFactory(project=project, status=_todo(project))

        services.move_task(task, _done(project), admin)
        task.refresh_from_db()

        assert task.closed_at is not None

    def test_the_github_closed_webhook_sets_it(self):
        from apps.integrations.github import process_webhook_issue

        project = ProjectFactory()
        task = TaskFactory(project=project, status=_todo(project), github_issue_id=77)

        process_webhook_issue({'action': 'closed', 'issue': {'id': 77}}, project)
        task.refresh_from_db()

        assert task.closed_at is not None

    def test_changing_a_status_type_updates_its_tasks(self, client):
        project = ProjectFactory()
        review = project.statuses.get(name='Review')
        task = TaskFactory(project=project, status=review)
        before = Task.objects.get(pk=task.pk).updated_at
        client.force_login(AdminUserFactory())
        url = reverse('status_set_category', args=[project.pk, review.pk])

        client.post(url, {'category': Status.COMPLETED})
        task.refresh_from_db()
        assert task.closed_at is not None
        assert task.updated_at == before

        client.post(url, {'category': Status.STARTED})
        task.refresh_from_db()
        assert task.closed_at is None


@pytest.mark.django_db
class TestArchivedQuery:
    def test_archived_is_closed_and_older_than_the_cutoff(self):
        project = ProjectFactory()
        old = _age(TaskFactory(project=project, status=_done(project)), settings.TASK_ARCHIVE_AFTER_DAYS + 1)
        recent = _age(TaskFactory(project=project, status=_done(project)), settings.TASK_ARCHIVE_AFTER_DAYS - 1)
        open_task = TaskFactory(project=project, status=_todo(project))

        archived = set(Task.objects.archived())

        assert old in archived
        assert recent not in archived and open_task not in archived
        assert old.is_archived and not recent.is_archived and not open_task.is_archived

    def test_matching_leaves_archived_out_unless_asked(self):
        project = ProjectFactory()
        old = _age(TaskFactory(project=project, status=_done(project)), 30)
        recent = TaskFactory(project=project, status=_done(project))
        no_date = TaskFactory(project=project, status=_done(project))
        Task.objects.filter(pk=no_date.pk).update(closed_at=None)
        options = TaskViewOptions()

        default = set(Task.objects.matching(TaskViewSpec.from_params({}, options)))
        shown = set(Task.objects.matching(TaskViewSpec.from_params({'archived': '1'}, options)))

        assert old not in default and recent in default and no_date in default
        assert old in shown


class TestSpec:
    def test_archived_round_trips_and_counts_as_a_filter(self):
        options = TaskViewOptions()

        spec = TaskViewSpec.from_params({'archived': '1'}, options)

        assert spec.archived
        assert spec.to_params()['archived'] == '1'
        assert spec.filter_count == 1
        assert not TaskViewSpec.from_params({}, options).archived
        assert 'archived' not in TaskViewSpec.from_params({}, options).to_params()

    def test_the_filter_form_and_clear(self):
        options = TaskViewOptions()

        assert TaskViewSpec.from_params({'filter': '1', 'archived': '1'}, options).archived
        assert not TaskViewSpec.from_params({'filter': '1'}, options).archived
        assert not TaskViewSpec.from_params({'archived': '1', 'clear': '1'}, options).archived


@pytest.mark.django_db
class TestPages:
    def _project_with_tasks(self):
        project = ProjectFactory()
        _age(TaskFactory(project=project, status=_done(project), title='Ancient done'), 40)
        TaskFactory(project=project, status=_done(project), title='Fresh done')
        TaskFactory(project=project, status=_todo(project), title='Still open')
        return project

    def test_the_list_hides_archived_and_offers_to_show_them(self, client):
        project = self._project_with_tasks()
        client.force_login(AdminUserFactory())

        html = client.get(reverse('project_tasks', args=[project.pk]), {'layout': 'list'}).content.decode()

        assert 'Ancient done' not in html and 'Fresh done' in html
        assert re.search(r'1 archived', html)
        assert 'hidden by filters' not in html
        assert 'name="archived"' in html

    def test_show_archived_brings_them_back(self, client):
        project = self._project_with_tasks()
        client.force_login(AdminUserFactory())

        html = client.get(
            reverse('project_tasks', args=[project.pk]), {'layout': 'list', 'archived': '1'}
        ).content.decode()

        assert 'Ancient done' in html
        assert not re.search(r'\d+ archived', html)

    def test_the_board_hides_archived_and_says_so_in_an_archived_only_column(self, client):
        project = ProjectFactory()
        _age(TaskFactory(project=project, status=_done(project), title='Ancient done'), 40)
        client.force_login(AdminUserFactory())

        html = client.get(reverse('project_tasks', args=[project.pk]), {'layout': 'board'}).content.decode()

        assert 'Ancient done' not in html
        assert '1 archived' in html
        assert 'Only archived tasks' in html

    def test_the_board_shows_archived_when_asked(self, client):
        project = ProjectFactory()
        _age(TaskFactory(project=project, status=_done(project), title='Ancient done'), 40)
        client.force_login(AdminUserFactory())

        html = client.get(
            reverse('project_tasks', args=[project.pk]), {'layout': 'board', 'archived': '1'}
        ).content.decode()

        assert 'Ancient done' in html

    def test_my_tasks_show_all_includes_archived(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        _age(TaskFactory(project=project, status=_done(project), assignee=admin, title='Ancient done'), 40)
        TaskFactory(project=project, status=_todo(project), assignee=admin, title='Still open')
        client.force_login(admin)

        html = client.get(reverse('my_tasks'), {'layout': 'list'}).content.decode()
        show_all = re.search(r'href="([^"]*)"[^>]*>Show all', html).group(1).replace('&amp;', '&')
        everything = client.get(show_all).content.decode()

        assert 'Ancient done' not in html
        assert 'archived=1' in show_all
        assert 'Ancient done' in everything

    def test_the_drawer_says_archived(self, client):
        project = ProjectFactory()
        task = _age(TaskFactory(project=project, status=_done(project)), 40)
        client.force_login(AdminUserFactory())

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        assert 'Archived' in html

    def test_search_and_counts_keep_archived(self, client):
        from apps.search.services import search

        project = ProjectFactory()
        admin = AdminUserFactory()
        old = _age(TaskFactory(project=project, status=_done(project), title='Ancient done'), 40)

        assert old in search(admin, 'Ancient').tasks
        assert project.task_count == 1


@pytest.mark.django_db
class TestGitHubSync:
    def test_an_opened_webhook_for_a_known_issue_does_not_move_it_back(self):
        from apps.integrations.github import process_webhook_issue

        project = ProjectFactory()
        task = TaskFactory(project=project, status=_done(project), github_issue_id=5)

        process_webhook_issue({'action': 'opened', 'issue': {
            'id': 5, 'number': 1, 'title': 'Same', 'body': '',
        }}, project)
        task.refresh_from_db()

        assert task.status == _done(project)

    def test_a_new_issue_still_starts_in_the_first_status(self):
        from apps.integrations.github import process_webhook_issue

        project = ProjectFactory()

        process_webhook_issue({'action': 'opened', 'issue': {
            'id': 6, 'number': 2, 'title': 'New', 'body': '',
        }}, project)

        assert Task.objects.get(github_issue_id=6).status == project.statuses.first()


BEFORE = [('tasks', '0014_activity_edited_at_and_types')]
AFTER = [('tasks', '0016_task_closed_at_data')]


@pytest.mark.django_db(transaction=True)
def test_the_migration_fills_closed_at_and_goes_back():
    from apps.clients.models import Client

    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    try:
        apps = executor.loader.project_state(BEFORE).apps
        Project = apps.get_model('projects', 'Project')
        HStatus = apps.get_model('projects', 'Status')
        HTask = apps.get_model('tasks', 'Task')
        Activity = apps.get_model('tasks', 'TaskActivity')
        client = Client.objects.create(name='Acme')
        project = Project.objects.create(client_id=client.pk, name='P', key='PP')
        done = HStatus.objects.create(project=project, name='Done', category='completed')
        todo = HStatus.objects.create(project=project, name='To Do', category='unstarted')
        with_change = HTask.objects.create(project=project, status=done, title='a', number=1)
        without = HTask.objects.create(project=project, status=done, title='b', number=2)
        open_task = HTask.objects.create(project=project, status=todo, title='c', number=3)
        changed_at = timezone.now() - timedelta(days=30)
        old_update = timezone.now() - timedelta(days=60)
        change = Activity.objects.create(task=with_change, activity_type='status_change', new_value='Done')
        Activity.objects.filter(pk=change.pk).update(created_at=changed_at)
        HTask.objects.filter(pk=without.pk).update(updated_at=old_update)

        apps = MigrationExecutor(connection).loader.project_state(AFTER).apps
        MigrationExecutor(connection).migrate(AFTER)
        HTask = apps.get_model('tasks', 'Task')
        closed = dict(HTask.objects.values_list('pk', 'closed_at'))
        assert closed[with_change.pk] == changed_at
        assert closed[without.pk] == old_update
        assert closed[open_task.pk] is None
        assert HTask.objects.get(pk=without.pk).updated_at == old_update

        MigrationExecutor(connection).migrate(BEFORE)
        MigrationExecutor(connection).migrate(AFTER)
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
class TestArchiveReviewFixes:
    def test_a_reopened_issue_brings_its_task_back(self):
        # A sync no longer resets the status, so "reopened" has to move the task itself.
        from apps.integrations.github import process_webhook_issue

        project = ProjectFactory()
        task = _age(TaskFactory(project=project, status=_done(project), github_issue_id=7), 30)

        process_webhook_issue({'action': 'reopened', 'issue': {
            'id': 7, 'number': 3, 'title': 'Back', 'body': '',
        }}, project)
        task.refresh_from_db()

        assert not task.status.is_closed
        assert task.closed_at is None
        assert not task.is_archived

    def test_reopening_an_issue_whose_task_is_open_leaves_it_where_it_is(self):
        from apps.integrations.github import process_webhook_issue

        project = ProjectFactory()
        review = project.statuses.get(name='Review')
        task = TaskFactory(project=project, status=review, github_issue_id=8)

        process_webhook_issue({'action': 'reopened', 'issue': {
            'id': 8, 'number': 4, 'title': 'Open', 'body': '',
        }}, project)
        task.refresh_from_db()

        assert task.status == review

    def test_saving_a_status_with_a_new_type_closes_or_reopens_its_tasks(self):
        # The rule is on the model, so the admin follows it, not only the settings page.
        project = ProjectFactory()
        review = project.statuses.get(name='Review')
        task = TaskFactory(project=project, status=review)
        assert task.closed_at is None

        review.category = Status.COMPLETED
        review.save()
        task.refresh_from_db()
        assert task.closed_at is not None

        review.category = Status.STARTED
        review.save()
        task.refresh_from_db()
        assert task.closed_at is None

    def test_saving_other_status_fields_leaves_closed_at_alone(self):
        project = ProjectFactory()
        done = _done(project)
        task = _age(TaskFactory(project=project, status=done), 30)
        closed_at = task.closed_at

        done.visible_on_board = False
        done.save(update_fields=['visible_on_board'])
        task.refresh_from_db()

        assert task.closed_at == closed_at

    def test_a_list_whose_tasks_are_all_archived_says_so(self, client):
        project = ProjectFactory()
        _age(TaskFactory(project=project, status=_done(project), title='Ancient done'), 30)
        client.force_login(AdminUserFactory())

        html = client.get(reverse('project_tasks', args=[project.pk]), {'layout': 'list'}).content.decode()

        assert 'Everything here is archived' in html
        assert 'Show 1 archived' in html
        assert 'No tasks yet' not in html
        assert 'Create the first task' not in html
