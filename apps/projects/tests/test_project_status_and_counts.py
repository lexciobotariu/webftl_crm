"""Project status, the task counts on project lists, the New Project drawer and delete rules."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.services import add_line, create_invoice
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project, Status
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import Task


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


def _archived_task(project):
    task = TaskFactory(project=project, status=project.statuses.get(category=Status.COMPLETED))
    Task.objects.filter(pk=task.pk).update(closed_at=timezone.now() - timedelta(days=365))
    return task


@pytest.mark.django_db
class TestTaskCounts:
    def test_lists_count_visible_tasks_without_archived_ones(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(name='Counted')
        TaskFactory.create_batch(2, project=project)
        _archived_task(project)
        client.force_login(admin)

        listing = client.get(reverse('project_list'))
        row = next(p for p in listing.context['projects'] if p.pk == project.pk)
        assert row.num_tasks == 2

        on_client = client.get(reverse('client_detail_projects', args=[project.client_id]))
        assert [p.num_tasks for p in on_client.context['projects']] == [2]

        overview = client.get(reverse('project_detail', args=[project.pk]))
        assert overview.context['total_tasks'] == 2
        assert overview.context['archived_tasks'] == 1
        assert '+1 archived' in overview.content.decode()

    def test_a_person_without_the_tasks_module_counts_none(self, client):
        user = _user('NoTasks', access_tasks=False)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(3, project=project)
        client.force_login(user)

        listing = client.get(reverse('project_list'))
        assert [p.num_tasks for p in listing.context['projects']] == [0]


@pytest.mark.django_db
class TestStatus:
    def test_new_projects_are_active(self):
        assert ProjectFactory().status == Project.ACTIVE

    def test_the_list_shows_open_projects_and_a_toggle_for_closed_ones(self, client):
        admin = AdminUserFactory()
        active = ProjectFactory(name='Running')
        on_hold = ProjectFactory(name='Paused', status=Project.ON_HOLD)
        finished = ProjectFactory(name='Shipped', status=Project.FINISHED)
        cancelled = ProjectFactory(name='Dropped', status=Project.CANCELLED)
        client.force_login(admin)

        listing = client.get(reverse('project_list'))
        assert {p.pk for p in listing.context['projects']} == {active.pk, on_hold.pk}
        assert listing.context['closed_count'] == 2
        html = listing.content.decode()
        assert 'Show finished and cancelled (2)' in html
        assert 'On hold' in html

        closed = client.get(reverse('project_list') + '?closed=1')
        assert {p.pk for p in closed.context['projects']} == {finished.pk, cancelled.pk}
        assert 'Back to open projects' in closed.content.decode()

    def test_settings_change_the_status_and_refuse_an_unknown_one(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        url = reverse('project_settings_update', args=[project.pk])
        fields = {'name': project.name, 'key': project.key}

        client.post(url, {**fields, 'status': Project.FINISHED})
        project.refresh_from_db()
        assert project.status == Project.FINISHED

        response = client.post(url, {**fields, 'status': 'gone'})
        assert 'Choose a status' in response.content.decode()
        project.refresh_from_db()
        assert project.status == Project.FINISHED

        # A form without the field keeps the status.
        client.post(url, fields)
        project.refresh_from_db()
        assert project.status == Project.FINISHED

    def test_the_overview_shows_the_status(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(status=Project.ON_HOLD)
        client.force_login(admin)
        assert 'On hold' in client.get(reverse('project_detail', args=[project.pk])).content.decode()

    def test_the_dashboard_counts_open_projects(self, client):
        admin = AdminUserFactory()
        ProjectFactory()
        ProjectFactory(status=Project.ON_HOLD)
        ProjectFactory(status=Project.FINISHED)
        client.force_login(admin)
        assert client.get(reverse('dashboard')).context['project_count'] == 2


@pytest.mark.django_db
class TestCreateDrawer:
    def test_the_projects_page_opens_the_drawer(self, client):
        user = _user('Creator')
        ProjectAccessFactory(project=ProjectFactory(client=ClientFactory(name='Mine')), user=user)
        client.force_login(user)

        html = client.get(reverse('project_list')).content.decode()
        assert f'hx-get="{reverse("project_create")}"' in html

        drawer = client.get(reverse('project_create'), HTTP_HX_REQUEST='true')
        assert drawer.status_code == 200
        assert 'projects/partials/project_create_drawer.html' in [t.name for t in drawer.templates]
        body = drawer.content.decode()
        assert 'name="client"' in body
        assert 'Mine' in body

    def test_the_page_address_lands_on_the_list_with_the_drawer_open(self, client):
        user = _user('Creator')
        own = ClientFactory()
        client.force_login(user)

        response = client.get(reverse('project_create') + f'?client={own.pk}')
        assert response.status_code == 302
        assert response['Location'] == reverse('project_list') + f'?new=1&new_client={own.pk}'

        listing = client.get(response['Location'])
        assert listing.context['open_create_drawer'] is True
        assert f'{reverse("project_create")}?client={own.pk}' in listing.content.decode()

    def test_a_valid_drawer_post_redirects_to_the_new_project(self, client):
        admin = AdminUserFactory()
        owner = ClientFactory()
        client.force_login(admin)

        response = client.post(reverse('project_create'), {
            'client': owner.pk, 'name': 'Drawer Made', 'description': '**Bold**',
        }, HTTP_HX_REQUEST='true')
        project = Project.objects.get(name='Drawer Made')
        assert response['HX-Redirect'] == reverse('project_tasks', args=[project.pk])

    def test_an_invalid_post_shows_the_drawer_again_with_what_was_typed(self, client):
        admin = AdminUserFactory()
        owner = ClientFactory()
        client.force_login(admin)

        response = client.post(reverse('project_create'), {
            'client': owner.pk, 'name': 'Kept', 'github_repo_url': 'javascript:alert(1)',
        }, HTTP_HX_REQUEST='true')
        body = response.content.decode()
        assert response.status_code == 200
        assert 'value="Kept"' in body
        assert f'<option value="{owner.pk}" selected>' in body
        assert not Project.objects.filter(name='Kept').exists()

    def test_the_client_page_uses_the_same_drawer_with_the_client_fixed(self, client):
        admin = AdminUserFactory()
        owner = ClientFactory(name='Fixed Co')
        client.force_login(admin)

        drawer = client.get(reverse('client_create_project', args=[owner.pk]), HTTP_HX_REQUEST='true')
        assert 'projects/partials/project_create_drawer.html' in [t.name for t in drawer.templates]
        body = drawer.content.decode()
        assert 'name="client"' not in body
        assert 'Fixed Co' in body


@pytest.mark.django_db
class TestMarkdownDescription:
    def test_the_overview_renders_the_description_as_markdown(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory(description='**Bold** <script>x</script>')
        client.force_login(admin)
        html = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert '<strong>Bold</strong>' in html
        assert '<script>x</script>' not in html

    def test_settings_and_the_drawer_use_the_markdown_editor(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        preview = reverse('markdown_preview')
        assert preview in client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert preview in client.get(reverse('project_create'), HTTP_HX_REQUEST='true').content.decode()


@pytest.mark.django_db
class TestDeleteRules:
    def test_a_project_with_logged_time_is_not_deleted(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        TimeEntryFactory(task=TaskFactory(project=project))
        client.force_login(admin)

        settings_html = client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert reverse('project_delete', args=[project.pk]) not in settings_html
        assert 'has logged time' in settings_html

        response = client.post(reverse('project_delete', args=[project.pk]))
        assert response.status_code == 400
        assert 'Finished or Cancelled' in response.content.decode()
        assert Project.objects.filter(pk=project.pk).exists()

    def test_a_project_on_an_invoice_is_not_deleted(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        project.client.currency, _ = Currency.objects.get_or_create(
            code='EUR', defaults={'name': 'Euro', 'symbol': '€'}
        )
        project.client.save(update_fields=['currency'])
        today = timezone.localdate()
        invoice = create_invoice(client=project.client, issue_date=today, due_date=today, tax_rate=Decimal('0'))
        add_line(invoice, project=project, description='', quantity=Decimal('1'), unit_price=Decimal('10'))
        # The invoice itself protects the client, not the project; the line does.
        client.force_login(admin)

        response = client.post(reverse('project_delete', args=[project.pk]))
        assert response.status_code == 400
        assert 'on an invoice' in response.content.decode()
        assert Project.objects.filter(pk=project.pk).exists()

    def test_a_project_without_time_or_invoices_is_deleted(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        TaskFactory(project=project)
        client.force_login(admin)

        assert reverse('project_delete', args=[project.pk]) in client.get(
            reverse('project_settings', args=[project.pk])
        ).content.decode()
        client.post(reverse('project_delete', args=[project.pk]))
        assert not Project.objects.filter(pk=project.pk).exists()

    def test_a_client_whose_projects_have_logged_time_is_not_deleted(self, client):
        admin = AdminUserFactory()
        owner = ClientFactory()
        TimeEntryFactory(task=TaskFactory(project=ProjectFactory(client=owner)))
        client.force_login(admin)

        page = client.get(reverse('client_detail', args=[owner.pk])).content.decode()
        assert reverse('client_delete', args=[owner.pk]) not in page

        response = client.post(reverse('client_delete', args=[owner.pk]))
        assert response.status_code == 400
        assert 'logged time' in response.content.decode()
        owner.refresh_from_db()
