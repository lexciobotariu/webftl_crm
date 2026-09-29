import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import ProjectTaskListFilter, Status, can_edit_project
from apps.tasks.factories import TaskFactory


def _member(project):
    user = UserFactory()
    ProjectAccessFactory(project=project, user=user)
    return user


def _shown_except(project, *hidden):
    """The checkbox values the form posts when ``hidden`` are unchecked."""
    skip = {status.pk for status in hidden}
    return [status.pk for status in project.statuses.all() if status.pk not in skip]


def _tasks_url(project):
    return reverse('project_detail_tasks', args=[project.pk])


@pytest.mark.django_db
class TestProjectTaskListFilter:
    def test_hidden_status_leaves_the_list_and_stays_hidden(self, client):
        project = ProjectFactory()
        user = _member(project)
        backlog = project.statuses.get(name='Backlog')
        done = project.statuses.get(name='Done')
        kept = TaskFactory(project=project, status=backlog, title='Keep this task')
        hidden = TaskFactory(project=project, status=done, title='Hide this task')
        client.force_login(user)

        response = client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )
        assert response.status_code == 302
        assert response['Location'] == _tasks_url(project)

        again = client.get(_tasks_url(project))
        content = again.content.decode()
        assert kept.title in content
        assert hidden.title not in content
        assert again.context['list_task_count'] == 1
        assert again.context['hidden_by_filter_count'] == 1
        assert '1 task hidden' in content
        assert can_edit_project(user, project) is False

    def test_another_person_still_sees_every_task(self, client):
        project = ProjectFactory()
        owner = _member(project)
        other = _member(project)
        done = project.statuses.get(name='Done')
        task = TaskFactory(project=project, status=done, title='Visible to the other person')
        client.force_login(owner)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )

        client.force_login(other)
        response = client.get(_tasks_url(project))
        assert task.title in response.content.decode()
        assert response.context['hidden_by_filter_count'] == 0
        assert not ProjectTaskListFilter.objects.filter(user=other, project=project).exists()

    def test_status_from_another_project_is_ignored(self, client):
        project = ProjectFactory()
        other = ProjectFactory()
        user = _member(project)
        own = project.statuses.get(name='Done')
        foreign = other.statuses.get(name='Backlog')
        own_task = TaskFactory(project=project, status=own, title='Stays on this list')
        TaskFactory(project=other, status=foreign, title='Other project task')
        client.force_login(user)

        response = client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': [foreign.pk, 'not-an-id']},
        )
        assert response.status_code == 302
        saved = ProjectTaskListFilter.objects.get(user=user, project=project)
        assert list(saved.hidden_statuses.values_list('pk', flat=True)) == []

        page = client.get(_tasks_url(project))
        assert own_task.title in page.content.decode()
        assert page.context['hidden_by_filter_count'] == 0
        foreign.refresh_from_db()
        assert foreign.visible_on_board is True

        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': [foreign.pk, *_shown_except(project, own)]},
        )
        saved.refresh_from_db()
        assert list(saved.hidden_statuses.values_list('pk', flat=True)) == [own.pk]

    def test_overview_and_board_ignore_the_list_filter(self, client):
        project = ProjectFactory()
        user = _member(project)
        backlog = project.statuses.get(name='Backlog')
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=backlog, title='Still active')
        TaskFactory(project=project, status=done, title='Still counted done')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )

        overview = client.get(reverse('project_detail', args=[project.pk]))
        assert overview.context['total_tasks'] == 2
        assert overview.context['completed_tasks'] == 1
        assert overview.context['active_tasks'] == 1
        assert overview.context['overdue_tasks'] == 0
        assert overview.context['active_tab'] == 'overview'

        tasks_page = client.get(_tasks_url(project))
        assert tasks_page.context['total_tasks'] == 2
        assert tasks_page.context['completed_tasks'] == 1
        assert tasks_page.context['list_task_count'] == 1

        board = client.get(reverse('project_board', args=[project.pk]))
        board_html = board.content.decode()
        assert 'Still counted done' in board_html
        assert 'Done' in board_html
        done.refresh_from_db()
        assert done.visible_on_board is True

    def test_empty_because_of_filter_has_no_create_first_task(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=done, title='Filtered out')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )

        content = client.get(_tasks_url(project)).content.decode()
        assert 'Nothing matches this filter' in content
        assert 'Clear filter' in content
        assert 'No tasks yet' not in content
        assert 'Create the first task' not in content

    def test_clear_deletes_the_row_and_shows_every_task(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        task = TaskFactory(project=project, status=done, title='Back after clear')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )

        response = client.post(reverse('project_task_list_filter_clear', args=[project.pk]))
        assert response.status_code == 302
        assert not ProjectTaskListFilter.objects.filter(user=user, project=project).exists()
        assert task.title in client.get(_tasks_url(project)).content.decode()

    def test_saving_requires_project_access_not_edit(self, client):
        project = ProjectFactory()
        outsider = UserFactory()
        client.force_login(outsider)
        denied = client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': [project.statuses.get(name='Done').pk]},
        )
        assert denied.status_code == 403
        assert not ProjectTaskListFilter.objects.filter(project=project).exists()

    def test_one_row_per_person_and_project(self):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskListFilter.objects.create(user=user, project=project)
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectTaskListFilter.objects.create(user=user, project=project)

    def test_deleting_a_status_removes_it_from_the_filter(self):
        project = ProjectFactory()
        user = _member(project)
        review = project.statuses.get(name='Review')
        saved = ProjectTaskListFilter.objects.create(user=user, project=project)
        saved.hidden_statuses.add(review)
        review.delete()
        assert not saved.hidden_statuses.exists()

    def test_nothing_checked_shows_every_task(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        task = TaskFactory(project=project, status=done, title='Still on the list')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )
        client.post(reverse('project_task_list_filter', args=[project.pk]), {})

        page = client.get(_tasks_url(project))
        assert task.title in page.content.decode()
        assert page.context['hidden_by_filter_count'] == 0
        assert page.context['active_filter_count'] == 0

    def test_unchecked_status_is_the_one_hidden_and_shows_unchecked(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )

        options = client.get(_tasks_url(project)).context['status_options']
        assert {o['label']: o['checked'] for o in options}['Done'] is False
        assert all(o['checked'] for o in options if o['label'] != 'Done')

    def test_status_added_after_saving_is_checked_and_visible(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done)},
        )
        added = Status.objects.create(project=project, name='QA', order=99)
        task = TaskFactory(project=project, status=added, title='In the new column')

        page = client.get(_tasks_url(project))
        assert task.title in page.content.decode()
        assert {o['label']: o['checked'] for o in page.context['status_options']}['QA'] is True

    def test_only_checked_priorities_are_shown(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory(project=project, priority='high', title='High one')
        TaskFactory(project=project, priority='low', title='Low one')
        TaskFactory(project=project, priority='', title='No priority one')
        client.force_login(user)
        url = reverse('project_task_list_filter', args=[project.pk])

        client.post(url, {'shown_priorities': ['high']})
        page = client.get(_tasks_url(project))
        content = page.content.decode()
        assert 'High one' in content
        assert 'Low one' not in content
        assert 'No priority one' not in content
        assert page.context['list_task_count'] == 1
        assert page.context['hidden_by_filter_count'] == 2
        assert page.context['active_filter_count'] == 1

        client.post(url, {'shown_priorities': ['high', 'none', 'not-a-priority']})
        content = client.get(_tasks_url(project)).content.decode()
        assert 'High one' in content
        assert 'No priority one' in content
        assert 'Low one' not in content

    def test_all_priorities_checked_is_no_filter(self, client):
        project = ProjectFactory()
        user = _member(project)
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_priorities': ['low', 'medium', 'high', 'urgent', 'none']},
        )
        assert ProjectTaskListFilter.objects.get(user=user, project=project).shown_priorities == []

    def test_status_and_priority_filters_combine(self, client):
        project = ProjectFactory()
        user = _member(project)
        backlog = project.statuses.get(name='Backlog')
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=backlog, priority='high', title='Match')
        TaskFactory(project=project, status=done, priority='high', title='Wrong status')
        TaskFactory(project=project, status=backlog, priority='low', title='Wrong priority')
        client.force_login(user)
        client.post(
            reverse('project_task_list_filter', args=[project.pk]),
            {'shown_statuses': _shown_except(project, done), 'shown_priorities': ['high']},
        )

        page = client.get(_tasks_url(project))
        content = page.content.decode()
        assert 'Match' in content
        assert 'Wrong status' not in content
        assert 'Wrong priority' not in content
        assert page.context['active_filter_count'] == 2
