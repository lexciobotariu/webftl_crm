"""Which clients a project can go on, and what its fields accept."""
import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project


def _user(name, **flags):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'access_tasks': True,
        'clients_view_all': False,
        'projects_create': True,
    }
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


def _own_client(user, name='Mine'):
    own = ClientFactory(name=name)
    ProjectAccessFactory(project=ProjectFactory(client=own), user=user)
    return own


@pytest.mark.django_db
class TestClientVisibility:
    def test_the_client_drawer_refuses_a_client_the_person_cannot_see(self, client):
        user = _user('Limited')
        hidden = ClientFactory(name='Hidden Co')
        client.force_login(user)
        assert client.get(reverse('client_create_project', args=[hidden.pk])).status_code == 404
        response = client.post(reverse('client_create_project', args=[hidden.pk]), {'name': 'Sneaky'})
        assert response.status_code == 404
        assert not Project.objects.filter(name='Sneaky').exists()

    def test_the_create_page_offers_and_accepts_only_visible_clients(self, client):
        user = _user('Limited')
        own = _own_client(user)
        hidden = ClientFactory(name='Hidden Co')
        client.force_login(user)

        page = client.get(reverse('project_create'))
        assert list(page.context['form'].fields['client'].queryset) == [own]
        assert 'Hidden Co' not in page.content.decode()

        response = client.post(reverse('project_create'), {'client': hidden.pk, 'name': 'Sneaky'})
        assert response.status_code == 200
        assert not Project.objects.filter(name='Sneaky').exists()


@pytest.mark.django_db
class TestFieldRules:
    @pytest.mark.parametrize('url', ['javascript:alert(1)', 'ftp://example.com/repo'])
    def test_settings_refuse_a_repository_that_is_not_a_web_address(self, client, url):
        admin = AdminUserFactory()
        project = ProjectFactory(github_repo_url='')
        client.force_login(admin)
        response = client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': project.name, 'key': project.key, 'github_repo_url': url,
        })
        assert 'https://' in response.content.decode()
        project.refresh_from_db()
        assert project.github_repo_url == ''

    def test_settings_refuse_a_name_that_is_too_long(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(name='Short')
        client.force_login(admin)
        response = client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': 'x' * 256, 'key': project.key,
        })
        assert response.status_code == 200
        assert 'at most 255' in response.content.decode()
        project.refresh_from_db()
        assert project.name == 'Short'

    def test_the_client_drawer_validates_too(self, client):
        admin = AdminUserFactory()
        owner = ClientFactory()
        client.force_login(admin)
        long_name = client.post(reverse('client_create_project', args=[owner.pk]), {'name': 'x' * 256})
        bad_url = client.post(reverse('client_create_project', args=[owner.pk]), {
            'name': 'Fine', 'github_repo_url': 'javascript:alert(1)',
        })
        assert long_name.status_code == 200
        assert bad_url.status_code == 200
        assert not owner.projects.exists()

    def test_an_old_unsafe_value_is_never_rendered_as_a_link(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(github_repo_url='javascript:alert(1)')
        client.force_login(admin)
        page = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert 'href="javascript:' not in page

    def test_sync_switch_is_kept_without_the_field_and_set_with_it(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(github_repo_url='https://github.com/org/repo', github_sync_enabled=True)
        client.force_login(admin)
        url = reverse('project_settings_update', args=[project.pk])
        client.post(url, {'name': project.name, 'key': project.key, 'github_repo_url': project.github_repo_url})
        project.refresh_from_db()
        assert project.github_sync_enabled

        client.post(url, {
            'name': project.name, 'key': project.key,
            'github_repo_url': project.github_repo_url, 'github_sync_field': '1',
        })
        project.refresh_from_db()
        assert not project.github_sync_enabled

        client.post(url, {
            'name': project.name, 'key': project.key, 'github_repo_url': '',
            'github_sync_field': '1', 'github_sync_enabled': 'on',
        })
        project.refresh_from_db()
        assert not project.github_sync_enabled


@pytest.mark.django_db
class TestListAndLinks:
    def test_a_non_numeric_client_filter_is_ignored(self, client):
        admin = AdminUserFactory()
        ProjectFactory()
        client.force_login(admin)
        response = client.get(reverse('project_list') + '?client=abc')
        assert response.status_code == 200
        assert response.context['total_count'] == 1

    def test_a_client_the_person_cannot_see_is_not_linked(self, client):
        user = _user('ViewAll', projects_view_all=True, projects_create=False)
        hidden = ClientFactory(name='Hidden Co')
        project = ProjectFactory(client=hidden)
        client.force_login(user)
        hidden_url = reverse('client_detail', args=[hidden.pk])
        assert hidden_url not in client.get(reverse('project_list')).content.decode()
        assert hidden_url not in client.get(reverse('project_detail', args=[project.pk])).content.decode()

    def test_edit_all_lists_the_projects_it_can_open(self, client):
        user = _user('EditAll', projects_edit_all=True, projects_create=False)
        project = ProjectFactory()
        client.force_login(user)
        assert client.get(reverse('project_detail', args=[project.pk])).status_code == 200
        assert project in client.get(reverse('project_list')).context['projects']
