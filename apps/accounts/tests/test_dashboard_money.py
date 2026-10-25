"""Money and deadlines on the dashboard (release 0.35.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.models import Payment
from apps.invoices.services import add_line, create_invoice
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project
from apps.tasks.factories import TaskFactory, TimeEntryFactory


def _client(name, code='EUR', symbol='€'):
    owner = ClientFactory(name=name)
    owner.currency, _ = Currency.objects.get_or_create(code=code, defaults={'name': code, 'symbol': symbol})
    owner.save(update_fields=['currency'])
    return owner


def _invoice(owner, amount, due=None, sent=True, paid=None, cancelled=False):
    today = timezone.localdate()
    invoice = create_invoice(client=owner, issue_date=today - timedelta(days=40),
                             due_date=due or today + timedelta(days=30), tax_rate=Decimal('0'))
    add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal(amount))
    if sent:
        invoice.sent_at = timezone.now()
    if cancelled:
        invoice.cancelled_at = timezone.now()
    invoice.save()
    if paid:
        Payment.objects.create(invoice=invoice, amount=Decimal(paid), date=today)
    return invoice


@pytest.mark.django_db
class TestMoney:
    def test_admin_sees_what_to_collect_overdue_paid_and_unbilled(self, client):
        today = timezone.localdate()
        acme, globex = _client('Acme'), _client('Globex', 'USD', '$')
        _invoice(acme, '10', sent=False)  # draft: not counted
        _invoice(acme, '100')
        late = _invoice(globex, '200', due=today - timedelta(days=3))
        _invoice(acme, '50', paid='20')
        _invoice(acme, '70', cancelled=True)
        project = ProjectFactory(client=acme, billing_type=Project.HOURLY, hourly_rate=Decimal('40'))
        task = TaskFactory(project=project, billable=True)
        start = timezone.now() - timedelta(hours=3)
        TimeEntryFactory(task=task, started_at=start, ended_at=start + timedelta(hours=2))

        client.force_login(AdminUserFactory())
        response = client.get(reverse('dashboard'))
        money = response.context['money']
        assert sorted(money.outstanding) == sorted(['130.00 €', '$200.00'])
        assert money.outstanding_count == 3
        assert money.overdue == ['$200.00']
        assert money.overdue_invoices == [late]
        assert money.paid_this_month == ['20.00 €']
        assert money.show_unbilled
        assert money.unbilled_hours == Decimal('2.0')
        assert money.unbilled_amounts == ['80.00 €']
        html = response.content.decode()
        assert 'To collect' in html
        assert late.number_label in html

    def test_people_without_invoices_see_no_money(self, client):
        _invoice(_client('Acme'), '100')
        client.force_login(UserFactory())
        response = client.get(reverse('dashboard'))
        assert 'money' not in response.context
        assert 'To collect' not in response.content.decode()


@pytest.mark.django_db
class TestDeadlines:
    def test_my_late_and_upcoming_tasks_and_project_deadlines(self, client):
        today = timezone.localdate()
        me = UserFactory()
        project = ProjectFactory(name='Website', deadline=today + timedelta(days=5))
        ProjectFactory(name='Far away', deadline=today + timedelta(days=60))
        ProjectAccessFactory(project=project, user=me)
        late = TaskFactory(project=project, assignee=me, due_date=today - timedelta(days=1), title='Late one')
        soon = TaskFactory(project=project, assignee=me, due_date=today + timedelta(days=2), title='Soon one')
        TaskFactory(project=project, assignee=me, due_date=today + timedelta(days=30), title='Later one')
        TaskFactory(project=project, due_date=today, title='Someone else')

        client.force_login(me)
        response = client.get(reverse('dashboard'))
        deadlines = response.context['deadlines']
        assert deadlines.late_tasks == [late]
        assert deadlines.week_tasks == [soon]
        assert [p.name for p in deadlines.projects] == ['Website']
        html = response.content.decode()
        section = html[html.index('id="dashboard-deadlines"'):html.index('<!-- Recent Tasks Section -->')]
        assert 'Late one' in section and 'Soon one' in section and 'Website' in section
        assert 'Later one' not in section and 'Someone else' not in section
