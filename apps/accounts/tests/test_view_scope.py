import re

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import can_access_project, can_edit_project, can_work_on_project
from apps.tasks.factories import TaskFactory
from apps.todos.factories import TodoFactory


def _preset(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'access_tasks': True,
        'access_todos': True,
        'clients_view_all': False,
        'projects_view_all': False,
    }
    fields.update(overrides)
    return PermissionPreset.objects.create(name=name, **fields)


def _user(name, **overrides):
    return UserFactory(permission_preset=_preset(name, **overrides))


def _lists(client):
    dashboard = client.get(reverse('dashboard'))
    clients = client.get(reverse('client_list'))
    projects = client.get(reverse('project_list'))
    assert dashboard.context['client_count'] == clients.context['total_count']
    assert dashboard.context['project_count'] == projects.context['total_count']
    return dashboard, clients, projects


def _checkbox_checked(html, name):
    match = re.search(rf'<input type="checkbox" name="{name}"([^>]*)>', html)
    assert match, name
    return 'checked' in match.group(1)


@pytest.mark.django_db
class TestViewOwn:
    def test_member_sees_only_their_project_and_client(self, client):
        user = _user('ViewOwn')
        mine_client = ClientFactory(name='Mine Client')
        other_client = ClientFactory(name='Other Client')
        mine = ProjectFactory(client=mine_client, name='Mine Project')
        ProjectFactory(client=other_client, name='Other Project')
        ProjectAccessFactory(project=mine, user=user)
        client.force_login(user)

        dashboard, clients_page, projects_page = _lists(client)
        client_html = clients_page.content.decode()
        project_html = projects_page.content.decode()

        assert dashboard.context['client_count'] == 1
        assert dashboard.context['project_count'] == 1
        assert 'Mine Client' in client_html
        assert 'Other Client' not in client_html
        assert 'Mine Project' in project_html
        assert 'Other Project' not in project_html

    def test_two_projects_on_one_client_count_once(self, client):
        user = _user('DistinctClients')
        shared = ClientFactory(name='Shared Client')
        first = ProjectFactory(client=shared, name='First Project')
        second = ProjectFactory(client=shared, name='Second Project')
        ProjectAccessFactory(project=first, user=user)
        ProjectAccessFactory(project=second, user=user)
        client.force_login(user)

        dashboard, _, projects_page = _lists(client)
        assert dashboard.context['client_count'] == 1
        assert dashboard.context['project_count'] == 2
        html = projects_page.content.decode()
        assert 'First Project' in html
        assert 'Second Project' in html


@pytest.mark.django_db
class TestClientsViewAll:
    def test_every_client_but_only_member_projects(self, client):
        user = _user('ClientsAll', clients_view_all=True)
        mine_client = ClientFactory(name='Mine Client')
        other_client = ClientFactory(name='Other Client')
        mine = ProjectFactory(client=mine_client, name='Mine Project')
        ProjectFactory(client=other_client, name='Hidden Project')
        ProjectAccessFactory(project=mine, user=user)
        client.force_login(user)

        dashboard, clients_page, projects_page = _lists(client)
        assert dashboard.context['client_count'] == 2
        assert dashboard.context['project_count'] == 1
        client_html = clients_page.content.decode()
        assert 'Mine Client' in client_html
        assert 'Other Client' in client_html
        project_html = projects_page.content.decode()
        assert 'Mine Project' in project_html
        assert 'Hidden Project' not in project_html

        detail = client.get(reverse('client_detail_projects', args=[other_client.pk]))
        assert detail.status_code == 200
        assert 'Hidden Project' not in detail.content.decode()


@pytest.mark.django_db
class TestProjectsViewAll:
    def test_every_project_opens_as_viewer_only(self, client):
        user = _user('ProjectsAll', projects_view_all=True, tasks_edit_own=True)
        mine_client = ClientFactory(name='Mine Client')
        other_client = ClientFactory(name='Other Client')
        mine = ProjectFactory(client=mine_client, name='Mine Project')
        foreign = ProjectFactory(client=other_client, name='Foreign Project')
        ProjectAccessFactory(project=mine, user=user)
        mine_task = TaskFactory(project=mine, title='Mine Task')
        foreign_task = TaskFactory(project=foreign, title='Foreign Task')
        client.force_login(user)

        dashboard, clients_page, projects_page = _lists(client)
        assert dashboard.context['client_count'] == 1
        assert dashboard.context['project_count'] == 2
        assert 'Other Client' not in clients_page.content.decode()
        project_html = projects_page.content.decode()
        assert 'Mine Project' in project_html
        assert 'Foreign Project' in project_html

        assert can_access_project(user, mine) is True
        assert can_work_on_project(user, mine) is True
        assert can_edit_project(user, mine) is False
        assert can_access_project(user, foreign) is True
        assert can_work_on_project(user, foreign) is False
        assert can_edit_project(user, foreign) is False

        assert client.get(reverse('project_board', args=[foreign.pk])).status_code == 200
        assert client.get(reverse('project_settings', args=[foreign.pk])).status_code == 403
        assert client.get(reverse('task_edit', args=[foreign_task.pk])).status_code == 403
        comment = client.post(
            reverse('comment_create', args=[foreign_task.pk]),
            {'content': 'Should not land'},
        )
        assert comment.status_code == 403
        assert not foreign_task.activities.filter(activity_type='comment').exists()

        kept = client.post(
            reverse('comment_create', args=[mine_task.pk]),
            {'content': 'Editor still can'},
        )
        assert kept.status_code == 200
        assert mine_task.activities.filter(activity_type='comment').exists()


@pytest.mark.django_db
class TestDashboardCards:
    def test_clients_card_hidden_without_access(self, client):
        user = _user('NoClients', access_clients=False)
        client.force_login(user)
        content = client.get(reverse('dashboard')).content.decode()
        assert reverse('client_list') not in content
        assert reverse('project_list') in content

    def test_projects_card_hidden_without_access(self, client):
        user = _user('NoProjects', access_projects=False)
        client.force_login(user)
        content = client.get(reverse('dashboard')).content.decode()
        assert reverse('project_list') not in content
        assert reverse('client_list') in content


@pytest.mark.django_db
class TestPersonalTasksAndTodos:
    def test_counts_stay_limited_to_the_user(self, client):
        user = _user('Personal', clients_view_all=True, projects_view_all=True)
        other = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, assignee=user, title='Mine Task')
        TaskFactory(project=project, assignee=other, title='Their Task')
        outside = ProjectFactory()
        TaskFactory(project=outside, assignee=user, title='Outside Task')
        TodoFactory(owner=user, title='My Todo')
        TodoFactory(owner=other, title='Their Todo')
        client.force_login(user)

        response = client.get(reverse('dashboard'))
        assert response.context['my_task_count'] == 1
        assert response.context['todo_count'] == 1
        task_titles = [task.title for task in response.context['recent_tasks']]
        todo_titles = [todo.title for todo in response.context['recent_todos']]
        assert task_titles == ['Mine Task']
        assert todo_titles == ['My Todo']


@pytest.mark.django_db
class TestAdminBypass:
    def test_admin_sees_everything_with_flags_off(self, client):
        preset = _preset('FlagsOff')
        admin = AdminUserFactory(permission_preset=preset)
        assert admin.has_app_permission('clients_view_all') is True
        assert admin.has_app_permission('projects_view_all') is True
        assert preset.clients_view_all is False
        assert preset.projects_view_all is False
        client_a = ClientFactory(name='Admin Client A')
        client_b = ClientFactory(name='Admin Client B')
        ProjectFactory(client=client_a, name='Admin Project A')
        ProjectFactory(client=client_b, name='Admin Project B')
        client.force_login(admin)

        dashboard, clients_page, projects_page = _lists(client)
        assert dashboard.context['client_count'] == 2
        assert dashboard.context['project_count'] == 2
        client_html = clients_page.content.decode()
        project_html = projects_page.content.decode()
        assert 'Admin Client A' in client_html
        assert 'Admin Client B' in client_html
        assert 'Admin Project A' in project_html
        assert 'Admin Project B' in project_html


@pytest.mark.django_db
class TestPresetFlags:
    def test_seeded_presets_and_custom_default(self):
        admin = PermissionPreset.objects.get(name='Admin')
        developer = PermissionPreset.objects.get(name='Developer')
        custom = PermissionPreset.objects.create(name='ExistingCustom')
        assert admin.clients_view_all is True
        assert admin.projects_view_all is True
        assert developer.clients_view_all is False
        assert developer.projects_view_all is False
        assert custom.clients_view_all is False
        assert custom.projects_view_all is False

    def test_drawer_checkboxes_and_save(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        create_html = client.get(reverse('preset_create')).content.decode()
        clients = create_html.split('data-module="clients"', 1)[1].split('data-module="projects"', 1)[0]
        projects = create_html.split('data-module="projects"', 1)[1].split('data-module="tasks"', 1)[0]
        assert 'View all' in clients
        assert 'View all' in projects
        assert _checkbox_checked(create_html, 'clients_view_all') is False
        assert _checkbox_checked(create_html, 'projects_view_all') is False

        admin_preset = PermissionPreset.objects.get(name='Admin')
        admin_html = client.get(reverse('preset_edit', args=[admin_preset.pk])).content.decode()
        assert _checkbox_checked(admin_html, 'clients_view_all') is True
        assert _checkbox_checked(admin_html, 'projects_view_all') is True

        developer = PermissionPreset.objects.get(name='Developer')
        developer_html = client.get(reverse('preset_edit', args=[developer.pk])).content.decode()
        assert _checkbox_checked(developer_html, 'clients_view_all') is False
        assert _checkbox_checked(developer_html, 'projects_view_all') is False

        response = client.post(reverse('preset_create'), {
            'name': 'ViewAllCustom',
            'access_dashboard': 'on',
            'access_clients': 'on',
            'access_projects': 'on',
            'clients_view_all': 'on',
            'projects_view_all': 'on',
        })
        assert response.status_code == 200
        saved = PermissionPreset.objects.get(name='ViewAllCustom')
        assert saved.clients_view_all is True
        assert saved.projects_view_all is True
        assert saved.access_clients is True
        assert saved.access_projects is True
