import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def _currency_id():
    currency, _created = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$'},
    )
    return currency.pk


@pytest.mark.django_db
class TestClientList:
    def test_client_list_requires_login(self, client):
        response = client.get(reverse('client_list'))
        assert response.status_code == 302

    def test_client_list_shows_clients(self, client):
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        ClientFactory(name='Test Client')
        response = client.get(reverse('client_list'))
        assert response.status_code == 200
        assert 'Test Client' in response.content.decode()

    def test_client_list_pagination(self, client):
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        for i in range(25):
            ClientFactory(name=f'Client {i}')
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
class TestClientCreate:
    def test_client_create_requires_login(self, client):
        response = client.post(reverse('client_create'), {'name': 'New Client'})
        assert response.status_code == 302

    def test_client_create_requires_admin(self, client):
        """Non-admin users cannot create clients."""
        user = UserFactory()
        client.force_login(user)
        response = client.post(reverse('client_create'), {'name': 'New Client'})
        assert response.status_code == 403

    def test_client_create_with_valid_data(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('client_create'), {
            'name': 'New Client',
            'email': 'new@client.com',
            'phone': '555-1234',
            'address': '123 Main St',
            'notes': 'Important client',
            'currency': _currency_id(),
        })
        assert response.status_code == 302
        from apps.clients.models import Client
        assert Client.objects.filter(name='New Client').exists()

    def test_client_create_with_invalid_data(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('client_create'), {
            'name': '',
        })
        assert response.status_code == 200
        from apps.clients.models import Client
        assert Client.objects.count() == 0


@pytest.mark.django_db
class TestClientBillingFields:
    def test_create_and_edit_save_tax_id_and_overrides(self, client):
        from apps.clients.models import Client

        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('client_create'), {
            'name': 'Billed Client',
            'email': 'contact@client.com',
            'phone': '',
            'address': '1 Billing St',
            'notes': '',
            'billing_name': 'Billed Client LLC',
            'billing_email': 'ap@client.com',
            'tax_id': 'EIN-42',
            'currency': _currency_id(),
        })
        assert created.status_code == 302
        saved = Client.objects.get(name='Billed Client')
        assert saved.billing_name == 'Billed Client LLC'
        assert saved.billing_email == 'ap@client.com'
        assert saved.tax_id == 'EIN-42'
        assert saved.name == 'Billed Client'
        assert saved.email == 'contact@client.com'

        edited = client.post(reverse('client_edit', args=[saved.pk]), {
            'name': 'Billed Client',
            'email': 'contact@client.com',
            'phone': '',
            'address': '1 Billing St',
            'notes': '',
            'billing_name': 'Billed Client Inc',
            'billing_email': 'finance@client.com',
            'tax_id': 'EIN-99',
        })
        assert edited.status_code == 302
        saved.refresh_from_db()
        assert saved.billing_name == 'Billed Client Inc'
        assert saved.billing_email == 'finance@client.com'
        assert saved.tax_id == 'EIN-99'

        drawer = client.post(reverse('client_edit_drawer', args=[saved.pk]), {
            'name': 'Billed Client',
            'email': 'contact@client.com',
            'phone': '',
            'address': '1 Billing St',
            'billing_name': 'Drawer Billing',
            'billing_email': 'drawer-ap@client.com',
            'tax_id': 'TAX-7',
        })
        assert drawer.status_code == 200
        saved.refresh_from_db()
        assert saved.billing_name == 'Drawer Billing'
        assert saved.billing_email == 'drawer-ap@client.com'
        assert saved.tax_id == 'TAX-7'

    def test_blank_billing_fields_are_not_copied_from_contact(self, client):
        from apps.clients.models import Client

        admin = AdminUserFactory()
        client.force_login(admin)
        created = client.post(reverse('client_create'), {
            'name': 'Plain Client',
            'email': 'plain@client.com',
            'phone': '',
            'address': '',
            'notes': '',
            'billing_name': '',
            'billing_email': '',
            'tax_id': '',
            'currency': _currency_id(),
        })
        assert created.status_code == 302
        saved = Client.objects.get(name='Plain Client')
        assert saved.billing_name == ''
        assert saved.billing_email == ''
        assert saved.bill_to_name == 'Plain Client'
        assert saved.bill_to_email == 'plain@client.com'

        drawer = client.post(reverse('client_create_drawer'), {
            'name': 'Drawer Plain',
            'email': 'drawer-plain@client.com',
            'phone': '',
            'address': '',
            'currency': _currency_id(),
        })
        assert drawer.status_code == 200
        drawer_client = Client.objects.get(name='Drawer Plain')
        assert drawer_client.billing_name == ''
        assert drawer_client.billing_email == ''
        assert drawer_client.tax_id == ''

    def test_forms_list_billing_fields(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        existing = ClientFactory(
            billing_name='Kept Billing',
            billing_email='kept@client.com',
            tax_id='KEEP-1',
        )

        create_html = client.get(reverse('client_create')).content.decode()
        drawer_html = client.get(reverse('client_create_drawer')).content.decode()
        edit_html = client.get(reverse('client_edit', args=[existing.pk])).content.decode()
        edit_drawer = client.get(reverse('client_edit_drawer', args=[existing.pk])).content.decode()

        for html in (create_html, drawer_html, edit_html, edit_drawer):
            assert 'name="billing_name"' in html
            assert 'name="billing_email"' in html
            assert 'name="tax_id"' in html
            assert 'A blank value uses the client name.' in html
            assert 'A blank value uses the billing contact email, else the client email.' in html
            assert '>Billing<' in html

        assert 'value="Kept Billing"' in edit_drawer
        assert 'value="kept@client.com"' in edit_drawer
        assert 'value="KEEP-1"' in edit_drawer

    def test_profile_shows_resolved_billing_name_and_tax_id(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        fallback = ClientFactory(
            name='Fallback Co',
            email='fallback@client.com',
            billing_name='',
            billing_email='',
            tax_id='',
        )
        html = client.get(reverse('client_detail', args=[fallback.pk])).content.decode()
        billing = html.split('>Billing</h2>', 1)[1].split('>Notes</h2>', 1)[0]
        assert 'Fallback Co' in billing
        assert 'fallback@client.com' in billing
        assert '—' in billing

        overridden = ClientFactory(
            name='Contact Co',
            email='contact@client.com',
            billing_name='Invoice Co',
            billing_email='invoice@client.com',
            tax_id='RO123456',
        )
        html = client.get(reverse('client_detail', args=[overridden.pk])).content.decode()
        billing = html.split('>Billing</h2>', 1)[1].split('>Notes</h2>', 1)[0]
        contact = html.split('>Company details</h2>', 1)[1].split('>Billing</h2>', 1)[0]
        assert 'Invoice Co' in billing
        assert 'invoice@client.com' in billing
        assert 'RO123456' in billing
        assert '>Address<' in contact
        assert 'Invoice Co' not in contact


@pytest.mark.django_db
class TestClientDetail:
    def test_client_detail_shows_info(self, client):
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        test_client = ClientFactory(name='Detail Client', email='detail@test.com')
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[test_client.pk]))
        assert response.status_code == 200
        assert 'Detail Client' in response.content.decode()

    def test_client_detail_404_for_nonexistent(self, client):
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[99999]))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.security
class TestClientDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        test_client = ClientFactory()
        client.force_login(user)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 403

    def test_admin_can_delete(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 302
        from apps.clients.models import Client
        assert not Client.objects.filter(pk=test_client.pk).exists()

    def test_delete_requires_post(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.get(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 405

    def test_admin_can_delete_client_whose_project_has_tasks(self, client):
        """The whole client -> project -> status/task cascade must go through."""
        from apps.clients.models import Client
        from apps.projects.factories import ProjectFactory
        from apps.tasks.factories import TaskFactory
        from apps.tasks.models import Task

        admin = AdminUserFactory()
        test_client = ClientFactory()
        project = ProjectFactory(client=test_client)
        task = TaskFactory(project=project, status=project.statuses.first())
        client.force_login(admin)

        response = client.post(reverse('client_delete', args=[test_client.pk]))

        assert response.status_code == 302
        assert not Client.objects.filter(pk=test_client.pk).exists()
        assert not Task.objects.filter(pk=task.pk).exists()


@pytest.mark.django_db
class TestClientDetailTabs:
    def test_client_detail_default_tab_is_profile(self, client):
        """GET /clients/<pk>/ should set active_tab to 'profile'"""
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'profile'

    def test_client_detail_projects_tab(self, client):
        """GET /clients/<pk>/projects/ should set active_tab to 'projects'"""
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail_projects', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'projects'

    def test_member_sees_only_accessible_projects(self, client):
        """A non-member does not see another project's name on the client.

        The Admin preset has projects_view_all, so this uses a view-own preset
        that can still open the client section.
        """
        preset = PermissionPreset.objects.create(name='ClientAccess', access_clients=True)
        user = UserFactory(permission_preset=preset)
        client_obj = ClientFactory()
        mine = ProjectFactory(client=client_obj, name='Mine Project')
        ProjectFactory(client=client_obj, name='Secret Project')
        ProjectAccessFactory(project=mine, user=user)
        client.force_login(user)

        response = client.get(reverse('client_detail_projects', args=[client_obj.pk]))
        content = response.content.decode()

        assert response.status_code == 200
        assert 'Mine Project' in content
        assert 'Secret Project' not in content
        assert 'Add Project' not in content
        assert reverse('client_edit_drawer', args=[client_obj.pk]) not in content

    def test_admin_sees_every_project_and_the_actions(self, client):
        admin = AdminUserFactory()
        client_obj = ClientFactory()
        ProjectFactory(client=client_obj, name='Mine Project')
        ProjectFactory(client=client_obj, name='Secret Project')
        client.force_login(admin)

        response = client.get(reverse('client_detail_projects', args=[client_obj.pk]))
        content = response.content.decode()

        assert 'Mine Project' in content
        assert 'Secret Project' in content
        assert 'Add Project' in content
        assert reverse('client_edit_drawer', args=[client_obj.pk]) in content

    def test_client_detail_todos_tab(self, client):
        """GET /clients/<pk>/todos/ should set active_tab to 'todos'"""
        preset = PermissionPreset.objects.get(name='Admin')
        user = UserFactory(permission_preset=preset)
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail_todos', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'todos'
