from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import ProjectTaskView
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory

TOOLBAR = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TRIGGER': 'task-toolbar'}


def _member(project):
    user = UserFactory()
    ProjectAccessFactory(project=project, user=user)
    return user


def _board(project, query=''):
    url = reverse('project_tasks', args=[project.pk])
    return f'{url}?layout=board' + (f'&{query}' if query else '')


def _columns(response):
    return [status.name for status in response.context['visible_statuses']]


def _cards(response, status_name):
    status = next(s for s in response.context['visible_statuses'] if s.name == status_name)
    return [task.title for task in status.tasks.all()]


@pytest.mark.django_db
class TestBoardLayout:
    def test_columns_are_the_statuses_shown_on_the_board(self, client):
        project = ProjectFactory()
        project.statuses.filter(name='Done').update(visible_on_board=False)
        client.force_login(_member(project))
        response = client.get(_board(project))
        assert response.status_code == 200
        assert _columns(response) == ['Backlog', 'To Do', 'In Progress', 'Review']
        assert response.context['spec'].layout == 'board'

    def test_columns_follow_the_status_order_not_the_database_order(self, client):
        project = ProjectFactory()
        project.statuses.filter(name='Backlog').update(order=50)
        client.force_login(_member(project))
        assert _columns(client.get(_board(project))) == [
            'To Do', 'In Progress', 'Review', 'Done', 'Backlog',
        ]

    def test_a_status_hidden_by_the_filter_loses_its_column(self, client):
        project = ProjectFactory()
        review = project.statuses.get(name='Review')
        TaskFactory(project=project, status=review, title='In review')
        client.force_login(_member(project))
        response = client.get(_board(project, f'hide_status={review.pk}'))
        assert 'Review' not in _columns(response)

    def test_filters_apply_to_the_cards_and_their_counts(self, client):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        TaskFactory(project=project, status=backlog, priority='high', title='Urgent-ish')
        TaskFactory(project=project, status=backlog, priority='low', title='Whenever')
        client.force_login(_member(project))
        response = client.get(_board(project, 'priority=high'))
        assert _cards(response, 'Backlog') == ['Urgent-ish']
        backlog_column = next(s for s in response.context['visible_statuses'] if s.name == 'Backlog')
        assert backlog_column.board_task_count == 1

    def test_cards_keep_their_manual_order_whatever_the_list_sort(self, client):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        TaskFactory(project=project, status=backlog, title='second', order=1, priority='urgent')
        TaskFactory(project=project, status=backlog, title='first', order=0, priority='low')
        client.force_login(_member(project))
        response = client.get(_board(project, 'sort=title&dir=desc&group=assignee'))
        assert _cards(response, 'Backlog') == ['first', 'second']

    def test_hidden_task_count_is_filtered_tasks_in_hidden_columns(self, client):
        project = ProjectFactory()
        done = project.statuses.get(name='Done')
        done.visible_on_board = False
        done.save()
        TaskFactory(project=project, status=done, priority='high')
        TaskFactory(project=project, status=done, priority='low')
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'))
        client.force_login(_member(project))
        assert client.get(_board(project)).context['hidden_task_count'] == 2
        assert client.get(_board(project, 'priority=high')).context['hidden_task_count'] == 1

    def test_no_hidden_count_when_every_column_is_shown(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        assert client.get(_board(project)).context['hidden_task_count'] == 0

    def test_the_board_loads_every_card_not_one_page(self, client):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        TaskFactory.create_batch(205, project=project, status=backlog)
        client.force_login(_member(project))
        response = client.get(_board(project))
        assert len(_cards(response, 'Backlog')) == 205

    def test_outsider_is_forbidden(self, client):
        project = ProjectFactory()
        client.force_login(UserFactory())
        assert client.get(_board(project)).status_code == 403

    def test_board_request_from_htmx_is_still_the_full_page(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        html = client.get(_board(project), HTTP_HX_REQUEST='true').content.decode()
        assert 'id="task-view"' in html
        assert 'id="task-toolbar"' in html


@pytest.mark.django_db
class TestBoardCards:
    def test_card_shows_id_avatar_subtasks_and_overdue_date(self, client):
        project = ProjectFactory(name='Website')
        assignee = UserFactory(name='Zoe')
        task = TaskFactory(
            project=project,
            assignee=assignee,
            due_date=timezone.now().date() - timedelta(days=2),
            priority='high',
        )
        SubtaskFactory(task=task, completed=True)
        SubtaskFactory(task=task, completed=False)
        client.force_login(_member(project))
        html = client.get(_board(project)).content.decode()
        assert f'WEBS-{task.pk}' in html
        assert 'title="Zoe"' in html
        assert '1/2' in html
        assert 'text-error' in html

    def test_card_for_a_task_without_subtasks_shows_no_progress(self, client):
        project = ProjectFactory()
        TaskFactory(project=project)
        client.force_login(_member(project))
        html = client.get(_board(project)).content.decode()
        assert 'data-subtasks' not in html

    def test_board_query_count_does_not_grow_with_cards(self, client):
        project = ProjectFactory()
        user = _member(project)
        label = LabelFactory(project=project)
        client.force_login(user)
        client.get(_board(project))  # first request creates one-off rows

        def queries_for(n):
            for _ in range(n):
                task = TaskFactory(project=project, assignee=UserFactory())
                task.labels.add(label)
                SubtaskFactory(task=task)
            with CaptureQueriesContext(connection) as captured:
                assert client.get(_board(project)).status_code == 200
            return len(captured)

        few = queries_for(3)
        many = queries_for(30)
        assert many == few


@pytest.mark.django_db
class TestBoardShell:
    def test_drag_and_drop_store_lives_outside_the_swapped_fragment(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        html = client.get(reverse('project_tasks', args=[project.pk])).content.decode()
        store = html.index("Alpine.store('kanban'")
        assert store < html.index('id="task-view"')
        assert html.count("Alpine.store('kanban'") == 1
        assert 'after_id' in html

    def test_the_page_refreshes_the_fragment_after_a_move(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        html = client.get(_board(project)).content.decode()
        assert "refreshFragment('#task-view')" in html


@pytest.mark.django_db
class TestBoardSavedLayout:
    def test_choosing_board_in_the_toolbar_is_remembered(self, client):
        project = ProjectFactory()
        user = _member(project)
        client.force_login(user)
        client.get(_board(project), **TOOLBAR)
        assert ProjectTaskView.objects.get(user=user, project=project).params == {'layout': 'board'}

    def test_bare_tasks_url_reopens_the_board(self, client):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskView.objects.create(user=user, project=project, params={'layout': 'board'})
        client.force_login(user)
        response = client.get(reverse('project_tasks', args=[project.pk]))
        assert response.status_code == 302
        assert response['Location'] == _board(project)

    def test_switching_back_to_list_forgets_the_board(self, client):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskView.objects.create(user=user, project=project, params={'layout': 'board'})
        client.force_login(user)
        client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list', **TOOLBAR)
        assert not ProjectTaskView.objects.filter(user=user, project=project).exists()


@pytest.mark.django_db
class TestKanbanUrlRedirects:
    def test_old_board_url_redirects_to_the_board_layout(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.status_code == 302
        assert response['Location'] == _board(project)
        assert reverse('project_board', args=[project.pk]) == f'/projects/{project.pk}/kanban/'

    def test_old_board_url_does_not_leak_a_project_to_outsiders(self, client):
        project = ProjectFactory()
        client.force_login(UserFactory())
        response = client.get(reverse('project_board', args=[project.pk]), follow=True)
        assert response.status_code == 403
