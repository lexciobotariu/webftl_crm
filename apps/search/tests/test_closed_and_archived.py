"""Finished and cancelled projects and archived clients stay out of pickers and search."""
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.forms import InvoiceLineForm
from apps.invoices.services import add_line, create_invoice
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.search.services import search


@pytest.mark.django_db
class TestPalette:
    def test_closed_projects_and_archived_clients_are_not_found(self):
        admin = AdminUserFactory()
        ProjectFactory(name='Zebra open')
        ProjectFactory(name='Zebra shipped', status=Project.FINISHED)
        ProjectFactory(name='Zebra dropped', status=Project.CANCELLED)
        ClientFactory(name='Zebra Co')
        ClientFactory(name='Zebra Old', archived_at=timezone.now())

        results = search(admin, 'Zebra')
        assert [p.name for p in results.projects] == ['Zebra open']
        assert 'Zebra Old' not in [c.name for c in results.clients]
        assert 'Zebra Co' in [c.name for c in results.clients]


@pytest.mark.django_db
class TestInvoiceLinePicker:
    def _invoice(self, owner):
        owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
        owner.save(update_fields=['currency'])
        return create_invoice(client=owner, issue_date=date(2026, 10, 1), due_date=date(2026, 10, 31),
                              tax_rate=Decimal('0'))

    def test_only_open_projects_are_offered_plus_the_one_on_the_line(self):
        owner = ClientFactory()
        open_project = ProjectFactory(client=owner, name='Open')
        on_hold = ProjectFactory(client=owner, name='Paused', status=Project.ON_HOLD)
        finished = ProjectFactory(client=owner, name='Done', status=Project.FINISHED)
        invoice = self._invoice(owner)

        offered = set(InvoiceLineForm(invoice=invoice).fields['project'].queryset)
        assert offered == {open_project, on_hold}

        line = add_line(invoice, project=finished, description='', quantity=Decimal('1'), unit_price=Decimal('5'))
        editing = InvoiceLineForm(invoice=invoice, current_project_id=line.project_id)
        assert finished in set(editing.fields['project'].queryset)

    def test_a_finished_project_is_refused_on_a_new_line(self):
        owner = ClientFactory()
        finished = ProjectFactory(client=owner, status=Project.FINISHED)
        invoice = self._invoice(owner)

        form = InvoiceLineForm({'project': finished.pk, 'quantity': '1', 'unit_price': '5'}, invoice=invoice)
        assert not form.is_valid()
        assert 'project' in form.errors
