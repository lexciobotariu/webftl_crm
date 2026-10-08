"""The client Overview tab and name search on the client list (release 0.25.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientContact
from apps.clients.overview import client_overview
from apps.crm.models import Currency
from apps.invoices.services import add_line, create_invoice
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project
from apps.tasks.factories import TaskFactory, TimeEntryFactory


def _eur(owner):
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])


def _sent_invoice(owner, due, amount):
    today = timezone.localdate()
    invoice = create_invoice(client=owner, issue_date=today - timedelta(days=40), due_date=due,
                             tax_rate=Decimal('0'))
    add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal(amount))
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=['sent_at'])
    return invoice


def _user(name, **flags):
    fields = {'access_dashboard': True, 'access_clients': True, 'access_projects': True, 'access_tasks': True,
              'clients_view_all': True}
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


@pytest.mark.django_db
class TestOverviewTab:
    def test_the_client_page_opens_on_the_overview_and_the_profile_has_its_own_tab(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())

        page = client.get(reverse('client_detail', args=[owner.pk]))
        assert page.context['active_tab'] == 'overview'
        assert 'Open projects' in page.content.decode()

        profile = client.get(reverse('client_detail_profile', args=[owner.pk]))
        assert profile.context['active_tab'] == 'profile'
        assert 'Company details' in profile.content.decode()

    def test_money_projects_and_hours(self, client):
        owner = ClientFactory()
        _eur(owner)
        today = timezone.localdate()
        late = _sent_invoice(owner, today - timedelta(days=5), '100')
        _sent_invoice(owner, today + timedelta(days=10), '50')
        create_invoice(client=owner, issue_date=today, due_date=today, tax_rate=Decimal('0'))  # a draft

        running = ProjectFactory(client=owner, name='Running', hourly_rate=Decimal('10'))
        ProjectFactory(client=owner, name='Shipped', status=Project.FINISHED)
        task = TaskFactory(project=running, billable=True)
        TimeEntryFactory(task=task)  # 30 minutes, started now
        admin = AdminUserFactory()

        overview = client_overview(admin, owner, today=today)
        assert overview.outstanding == ['150.00 €']
        assert overview.overdue_total == ['100.00 €']
        assert overview.overdue_invoices == [late]
        assert overview.draft_count == 1
        assert [p.name for p in overview.open_projects] == ['Running']
        assert overview.closed_project_count == 1
        assert overview.month_hours == Decimal('0.5')
        assert overview.month_billable_hours == Decimal('0.5')
        assert overview.recent_tasks == [task]
        assert overview.last_activity is not None

        client.force_login(admin)
        html = client.get(reverse('client_detail', args=[owner.pk])).content.decode()
        assert 'Overdue invoices' in html
        assert late.number_label in html
        assert '150.00 €' in html

    def test_without_the_invoices_module_there_is_no_money(self, client):
        owner = ClientFactory()
        _eur(owner)
        _sent_invoice(owner, timezone.localdate() - timedelta(days=5), '100')
        user = _user('NoMoney', access_invoices=False)

        overview = client_overview(user, owner)
        assert not overview.show_money and overview.outstanding == []

        client.force_login(user)
        html = client.get(reverse('client_detail', args=[owner.pk])).content.decode()
        assert 'Outstanding' not in html
        assert 'Overdue invoices' not in html

    def test_a_person_without_tasks_view_all_counts_only_their_own_hours(self):
        owner = ClientFactory()
        project = ProjectFactory(client=owner)
        user = _user('Own', tasks_view_all=False)
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project)
        TimeEntryFactory(task=task, user=user)
        TimeEntryFactory(task=task)

        overview = client_overview(user, owner)
        assert not overview.everyones_time
        assert overview.month_hours == Decimal('0.5')
        assert overview.month_hours * 2 == client_overview(AdminUserFactory(), owner).month_hours


@pytest.mark.django_db
class TestClientListSearch:
    def test_name_or_contact_finds_the_client(self, client):
        acme = ClientFactory(name='Acme Ltd')
        ClientFactory(name='Globex')
        ClientContact.objects.create(client=acme, name='Ioana Zamfir', email='ioana@acme.test')
        ClientContact.objects.create(client=acme, name='Ioana Two')
        client.force_login(AdminUserFactory())

        def names(query, **extra):
            response = client.get(reverse('client_list'), {'q': query, **extra})
            return [c.name for c in response.context['clients']]

        assert names('acme') == ['Acme Ltd']
        assert names('Ioana') == ['Acme Ltd']
        assert names('nothing here') == []
        assert 'No clients match your search' in client.get(reverse('client_list'), {'q': 'zzz'}).content.decode()

    def test_the_search_applies_to_archived_clients_and_their_count(self, client):
        ClientFactory(name='Old Acme', archived_at=timezone.now())
        ClientFactory(name='Old Globex', archived_at=timezone.now())
        ClientFactory(name='Acme Now')
        client.force_login(AdminUserFactory())

        active = client.get(reverse('client_list'), {'q': 'acme'})
        assert [c.name for c in active.context['clients']] == ['Acme Now']
        assert active.context['archived_count'] == 1
        assert 'q=acme' in active.content.decode()

        archived = client.get(reverse('client_list'), {'q': 'acme', 'archived': '1'})
        assert [c.name for c in archived.context['clients']] == ['Old Acme']
