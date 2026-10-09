"""The inline editor on a draft invoice or estimate, and the optional project (release 0.31.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.estimates import (
    add_estimate_line,
    convert_to_invoice,
    create_estimate,
    mark_estimate_sent,
    record_answer,
)
from apps.invoices.models import Invoice
from apps.invoices.recurring import create_due_invoices, save_recurring
from apps.invoices.services import add_line, create_invoice, mark_sent
from apps.projects.factories import ProjectFactory


def _today():
    return timezone.localdate()


def _client(name='Acme'):
    owner = ClientFactory(name=name, billing_email=f'{name.lower()}@bill.test')
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    return owner


def _invoice(owner=None, project=None):
    return create_invoice(
        client=owner or _client(),
        project=project,
        issue_date=_today(),
        due_date=_today() + timedelta(days=14),
        tax_rate=Decimal('10'),
    )


def _header(invoice, **changes):
    data = {
        'client': invoice.client_id,
        'project': invoice.project_id or '',
        'issue_date': invoice.issue_date.isoformat(),
        'due_date': invoice.due_date.isoformat(),
        'tax_rate': str(invoice.tax_rate),
    }
    data.update(changes)
    return data


@pytest.mark.django_db
class TestInvoiceEditor:
    def test_a_draft_shows_the_editor_and_a_sent_invoice_does_not(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()
        page = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert 'id="doc-header"' in page
        assert 'id="new-line"' in page

        add_line(invoice, project=None, description='Design', quantity=Decimal('1'), unit_price=Decimal('10'))
        mark_sent(invoice)
        page = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert 'id="doc-header"' not in page
        assert 'Design' in page

    def test_header_saves_on_change_and_returns_new_totals(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()
        add_line(invoice, project=None, description='Design', quantity=Decimal('2'), unit_price=Decimal('50'))

        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, tax_rate='20'))
        assert response.status_code == 200
        html = response.content.decode()
        assert 'id="doc-header"' in html
        assert 'id="doc-totals" hx-swap-oob="true"' in html
        assert '120.00' in html
        invoice.refresh_from_db()
        assert invoice.tax_rate == Decimal('20.00')

    def test_an_invalid_value_is_shown_and_not_saved(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()
        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, tax_rate='-5'))
        assert response.status_code == 200
        assert 'text-error' in response.content.decode()
        invoice.refresh_from_db()
        assert invoice.tax_rate == Decimal('10.00')

    def test_changing_the_client_clears_the_project_and_reloads(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner)
        invoice = _invoice(owner, project)
        other = _client('Other')

        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, client=other.pk))
        assert response['HX-Refresh'] == 'true'
        invoice.refresh_from_db()
        assert invoice.client == other
        assert invoice.project is None
        assert invoice.bill_to_email == 'other@bill.test'

    def test_a_project_of_another_client_is_refused(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()
        foreign = ProjectFactory(client=_client('Other'))
        client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, project=foreign.pk))
        invoice.refresh_from_db()
        assert invoice.project is None

    def test_lines_are_added_edited_and_removed_inline(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()

        missing = client.post(reverse('invoice_line_create', args=[invoice.pk]),
                              {'description': '', 'quantity': '1', 'unit_price': '5'})
        assert 'Enter a description.' in missing.content.decode()
        assert invoice.lines.count() == 0

        added = client.post(reverse('invoice_line_create', args=[invoice.pk]),
                            {'description': 'Hosting', 'quantity': '1', 'unit_price': '30'})
        assert 'id="doc-lines"' in added.content.decode()
        line = invoice.lines.get()

        edited = client.post(reverse('invoice_line_edit', args=[invoice.pk, line.pk]),
                             {'description': 'Hosting (year)', 'quantity': '12', 'unit_price': '30'})
        html = edited.content.decode()
        assert f'id="line-amount-{line.pk}" hx-swap-oob="true"' in html
        assert 'id="doc-totals" hx-swap-oob="true"' in html
        assert '396.00' in html  # 360 + 10%
        line.refresh_from_db()
        assert (line.description, line.quantity) == ('Hosting (year)', Decimal('12.00'))

        bad = client.post(reverse('invoice_line_edit', args=[invoice.pk, line.pk]),
                          {'description': 'Hosting', 'quantity': '0', 'unit_price': '30'})
        assert 'greater than or equal to 0.01' in bad.content.decode()
        line.refresh_from_db()
        assert line.quantity == Decimal('12.00')

        removed = client.post(reverse('invoice_line_delete', args=[invoice.pk, line.pk]))
        assert removed.status_code == 200
        assert invoice.lines.count() == 0

    def test_a_project_line_keeps_its_project_and_may_have_an_empty_description(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner, name='Website')
        invoice = _invoice(owner)
        line = add_line(invoice, project=project, description='', quantity=Decimal('1'), unit_price=Decimal('5'))
        assert line.description == 'Website'

        client.post(reverse('invoice_line_edit', args=[invoice.pk, line.pk]),
                    {'description': 'Homepage design', 'quantity': '3', 'unit_price': '5'})
        line.refresh_from_db()
        assert line.project == project
        assert line.description == 'Homepage design'

    def test_a_sent_invoice_refuses_header_changes(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice()
        add_line(invoice, project=None, description='Design', quantity=Decimal('1'), unit_price=Decimal('10'))
        mark_sent(invoice)
        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, tax_rate='0'))
        assert response.status_code == 403
        invoice.refresh_from_db()
        assert invoice.tax_rate == Decimal('10.00')


@pytest.mark.django_db
class TestEstimateEditor:
    def test_header_and_lines_edit_inline(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner)
        estimate = create_estimate(client=owner, issue_date=_today(), valid_until=_today() + timedelta(days=30),
                                   tax_rate=Decimal('0'))
        page = client.get(reverse('estimate_detail', args=[estimate.pk])).content.decode()
        assert 'id="doc-header"' in page

        client.post(reverse('estimate_header', args=[estimate.pk]), {
            'client': owner.pk, 'project': project.pk, 'issue_date': _today().isoformat(),
            'valid_until': (_today() + timedelta(days=10)).isoformat(), 'tax_rate': '19', 'notes': 'Scope',
        })
        estimate.refresh_from_db()
        assert (estimate.project, estimate.tax_rate, estimate.notes) == (project, Decimal('19.00'), 'Scope')

        client.post(reverse('estimate_line_create', args=[estimate.pk]),
                    {'description': 'Design', 'quantity': '2', 'unit_price': '100'})
        line = estimate.lines.get()
        client.post(reverse('estimate_line_edit', args=[estimate.pk, line.pk]),
                    {'description': 'Design', 'quantity': '3', 'unit_price': '100'})
        estimate.refresh_from_db()
        assert estimate.total == Decimal('357.00')

        client.post(reverse('estimate_line_delete', args=[estimate.pk, line.pk]))
        assert estimate.lines.count() == 0


@pytest.mark.django_db
class TestProjectCarriedOver:
    def test_convert_and_recurring_keep_the_project(self):
        owner = _client()
        project = ProjectFactory(client=owner)
        estimate = create_estimate(client=owner, project=project, issue_date=_today(),
                                   valid_until=_today() + timedelta(days=30), tax_rate=Decimal('0'))
        add_estimate_line(estimate, project=None, description='Design', quantity=Decimal('1'),
                          unit_price=Decimal('10'))
        mark_estimate_sent(estimate)
        record_answer(estimate, 'accepted')
        invoice = convert_to_invoice(estimate)
        assert invoice.project == project

        save_recurring(invoice, frequency='monthly', next_date=_today())
        created = create_due_invoices(today=_today())
        assert [draft.project for draft in created] == [project]

    def test_list_filters_by_project(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner, name='Website')
        on_project = _invoice(owner, project)
        _invoice(owner)
        response = client.get(reverse('invoice_list'), {'project': project.pk})
        assert list(response.context['invoices']) == [on_project]
        assert Invoice.objects.count() == 2

    def test_new_invoice_from_a_project_prefills_client_and_project(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner)
        response = client.get(reverse('invoice_create'), {'project': project.pk})
        form = response.context['form']
        assert form.initial['client'] == owner.pk
        assert form.initial['project'] == project.pk


@pytest.mark.django_db
class TestProjectPage:
    def test_project_overview_lists_its_invoices(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        project = ProjectFactory(client=owner, name='Website')
        invoice = _invoice(owner, project)
        _invoice(owner)
        page = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert 'id="project-invoices"' in page
        assert invoice.number_label in page
        assert 'INV-0002' not in page
        assert f'?project={project.pk}' in page
