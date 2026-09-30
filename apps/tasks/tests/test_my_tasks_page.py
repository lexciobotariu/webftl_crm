import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import LabelFactory, TaskFactory
from apps.tasks.models import MyTasksView

TOOLBAR = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TRIGGER': 'task-toolbar'}
SEARCH = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TRIGGER': 'task-search'}


def _project(user, name=None):
    project = ProjectFactory(name=name) if name else ProjectFactory()
    ProjectAccessFactory(project=project, user=user)
    return project


def _task(project, user, status, title, **extra):
    return TaskFactory(
        project=project,
        status=project.statuses.get(name=status),
        assignee=user,
        title=title,
        **extra,
    )


def _url(query=''):
    base = reverse('my_tasks')
    return f'{base}?{query}' if query else base


def _titles(response):
    return [task.title for group in response.context['groups'] for task in group['rows']]


@pytest.fixture
def person(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.mark.django_db
class TestDefaultView:
    def test_a_bare_url_redirects_to_the_canonical_default(self, client, person):
        response = client.get(_url())
        assert response.status_code == 302
        assert response['Location'] == f'{reverse("my_tasks")}?layout=list'

    def test_the_todos_tab_renders_without_a_query_string(self, client, person):
        response = client.get(reverse('my_tasks_todos'))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'todos'

    def test_only_open_assigned_tasks_are_shown(self, client, person):
        project = _project(person)
        _task(project, person, 'Backlog', 'Backlog one')
        _task(project, person, 'To Do', 'Todo one')
        _task(project, person, 'In Progress', 'Started one')
        _task(project, person, 'Done', 'Finished one')
        TaskFactory(project=project, assignee=UserFactory(), title='Somebody else')
        response = client.get(_url('layout=list'))
        assert sorted(_titles(response)) == ['Backlog one', 'Started one', 'Todo one']
        assert response.context['total_matching'] == 3
        assert response.context['hidden_count'] == 1
        assert response.context['spec'].filter_count == 0

    def test_grouped_by_project_by_default(self, client, person):
        beta = _project(person, 'Beta')
        alpha = _project(person, 'Alpha')
        _task(beta, person, 'To Do', 'in beta')
        _task(alpha, person, 'To Do', 'in alpha')
        response = client.get(_url('layout=list'))
        assert [g['label'] for g in response.context['groups']] == ['Alpha', 'Beta']
        assert [g['kind'] for g in response.context['groups']] == ['project', 'project']

    def test_tasks_on_projects_the_person_cannot_view_stay_out(self, client, person):
        hidden = ProjectFactory()
        _task(hidden, person, 'To Do', 'No access here')
        response = client.get(_url('layout=list'))
        assert _titles(response) == []

    def test_the_page_is_list_only(self, client, person):
        response = client.get(_url('layout=board'))
        assert response.context['spec'].layout == 'list'
        assert 'name="layout" value="board"' not in response.content.decode()

    def test_the_assigned_badge_is_the_dashboard_number(self, client, person):
        project = _project(person)
        _task(project, person, 'Backlog', 'a')
        _task(project, person, 'Done', 'b')
        _task(project, person, 'Review', 'c')
        page = client.get(_url('layout=list'))
        assert page.context['total_count'] == 2
        # Still two while looking at finished tasks, and on the To-Dos tab.
        assert client.get(_url('layout=list&category=completed')).context['total_count'] == 2
        assert client.get(reverse('my_tasks_todos')).context['total_count'] == 2
        assert client.get(reverse('dashboard')).context['my_task_count'] == 2

    def test_a_refresh_after_an_edit_updates_the_badge_too(self, client, person):
        # The refresher swaps #task-view; the badge rides along out of band, so
        # finishing a task in the drawer cannot leave the old number in the header.
        html = client.get(_url('layout=list')).content.decode()
        assert 'id="assigned-count"' in html
        assert 'id="task-view-refresh"' in html
        assert 'hx-select-oob="#assigned-count"' in html
        assert "source: '#task-view-refresh'" in html


@pytest.mark.django_db
class TestFilters:
    def test_a_status_type_shows_exactly_those(self, client, person):
        project = _project(person)
        _task(project, person, 'To Do', 'open')
        _task(project, person, 'Done', 'finished')
        response = client.get(_url('layout=list&category=completed'))
        assert _titles(response) == ['finished']
        assert response.context['spec'].filter_count == 1
        assert '<span class="bg-accent text-on-accent' in response.content.decode()

    def test_all_five_types_show_everything(self, client, person):
        project = _project(person)
        _task(project, person, 'To Do', 'open')
        _task(project, person, 'Done', 'finished')
        types = ''.join(f'&category={c}' for c in ('backlog', 'unstarted', 'started', 'completed', 'canceled'))
        response = client.get(_url('layout=list' + types))
        assert sorted(_titles(response)) == ['finished', 'open']
        assert response.context['hidden_count'] == 0

    def test_type_priority_and_search_combine(self, client, person):
        project = _project(person)
        _task(project, person, 'To Do', 'Fix login', priority='high')
        _task(project, person, 'To Do', 'Fix logout', priority='low')
        _task(project, person, 'Done', 'Fix signup', priority='high')
        response = client.get(_url('layout=list&priority=high&q=fix'))
        assert _titles(response) == ['Fix login']

    def test_labels_and_assignees_are_not_offered(self, client, person):
        project = _project(person)
        LabelFactory(project=project)
        content = client.get(_url('layout=list')).content.decode()
        assert 'name="assignee"' not in content
        assert 'name="label"' not in content
        assert 'name="shown_category"' in content
        assert 'name="shown_status"' not in content

    def test_group_by_status_type_and_priority(self, client, person):
        project = _project(person)
        _task(project, person, 'Backlog', 'one', priority='urgent')
        _task(project, person, 'Review', 'two', priority='low')
        by_type = client.get(_url('layout=list&group=category'))
        assert [g['label'] for g in by_type.context['groups']] == ['Backlog', 'Started']
        by_priority = client.get(_url('layout=list&group=priority'))
        assert [g['label'] for g in by_priority.context['groups']] == ['Urgent', 'Low']

    def test_a_group_the_page_does_not_offer_falls_back(self, client, person):
        assert client.get(_url('layout=list&group=assignee')).context['spec'].group == 'project'


@pytest.mark.django_db
class TestSavedView:
    def test_a_toolbar_change_is_remembered_per_person(self, client, person):
        client.get(_url('layout=list&category=completed&group=category'), **TOOLBAR)
        saved = MyTasksView.objects.get(user=person)
        assert saved.params == {'layout': 'list', 'category': ['completed'], 'group': 'category'}
        assert not MyTasksView.objects.exclude(user=person).exists()

    def test_a_bare_url_restores_it(self, client, person):
        client.get(_url('layout=list&category=completed'), **TOOLBAR)
        response = client.get(_url())
        assert response.status_code == 302
        assert response['Location'] == f'{reverse("my_tasks")}?layout=list&category=completed'

    def test_a_shared_link_does_not_overwrite_it(self, client, person):
        client.get(_url('layout=list&category=completed'), **TOOLBAR)
        client.get(_url('layout=list&group=none'))
        client.get(_url('layout=list&group=priority'), **SEARCH)
        assert MyTasksView.objects.get(user=person).params['category'] == ['completed']
        assert 'group' not in MyTasksView.objects.get(user=person).params

    def test_going_back_to_the_default_forgets_it(self, client, person):
        client.get(_url('layout=list&category=completed'), **TOOLBAR)
        client.get(_url('layout=list'), **TOOLBAR)
        assert not MyTasksView.objects.filter(user=person).exists()

    def test_a_saved_view_that_turned_default_is_dropped_on_restore(self, client, person):
        MyTasksView.objects.create(user=person, params={'layout': 'list', 'category': ['nonsense']})
        response = client.get(_url())
        assert response['Location'] == f'{reverse("my_tasks")}?layout=list'
        assert not MyTasksView.objects.filter(user=person).exists()

    def test_clear_returns_to_the_default_not_to_everything(self, client, person):
        project = _project(person)
        _task(project, person, 'Done', 'finished')
        client.get(_url('layout=list&category=completed'), **TOOLBAR)
        response = client.get(_url('layout=list&clear=1&filter=1'), **TOOLBAR)
        assert _titles(response) == []
        assert response.context['spec'].is_default
        assert not MyTasksView.objects.filter(user=person).exists()

    def test_toolbar_responses_push_the_canonical_url(self, client, person):
        response = client.get(_url('layout=list&category=completed&filter=1&shown_category=completed'), **TOOLBAR)
        assert response['HX-Push-Url'] == f'{reverse("my_tasks")}?layout=list&category=completed'
        response = client.get(_url('layout=list'), **SEARCH)
        assert response['HX-Replace-Url'] == f'{reverse("my_tasks")}?layout=list'


@pytest.mark.django_db
class TestEmptyStates:
    def test_nothing_assigned(self, client, person):
        content = client.get(_url('layout=list')).content.decode()
        assert 'No open tasks assigned to you' in content
        assert 'Show all' not in content

    def test_only_finished_tasks_offer_show_all(self, client, person):
        project = _project(person)
        _task(project, person, 'Done', 'finished')
        response = client.get(_url('layout=list'))
        content = response.content.decode()
        assert 'No open tasks assigned to you' in content
        assert 'Show all 1' in content
        assert 'category=completed' in content

    def test_a_filter_that_matches_nothing_offers_clear(self, client, person):
        project = _project(person)
        _task(project, person, 'To Do', 'open', priority='low')
        content = client.get(_url('layout=list&priority=urgent')).content.decode()
        assert 'Nothing matches this filter' in content
        assert 'id="task-toolbar-clear"' in content


@pytest.mark.django_db
class TestShowMore:
    def test_rows_are_cut_at_the_limit_and_more_is_offered(self, client, person):
        project = _project(person)
        TaskFactory.create_batch(203, project=project, assignee=person, status=project.statuses.get(name='To Do'))
        response = client.get(_url('layout=list'))
        assert len(_titles(response)) == 200
        assert response.context['total_matching'] == 203
        assert response.context['more_url'] == f'{reverse("my_tasks")}?layout=list&limit=400'
        assert len(_titles(client.get(response.context['more_url']))) == 203


@pytest.mark.django_db
class TestQueryCount:
    def test_rows_do_not_add_queries(self, client, person):
        project = _project(person)
        label = LabelFactory(project=project)
        client.get(_url('layout=list'))  # the first request creates one-off rows (company settings)

        def queries_for(n):
            for _ in range(n):
                task = _task(_project(person), person, 'To Do', 'row')
                task.labels.add(label)
            with CaptureQueriesContext(connection) as captured:
                assert client.get(_url('layout=list')).status_code == 200
            return len(captured)

        few = queries_for(3)
        many = queries_for(20)
        assert many == few
