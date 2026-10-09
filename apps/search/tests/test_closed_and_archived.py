"""Finished and cancelled projects and archived clients stay out of pickers and search."""

import pytest
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.invoices.forms import InvoiceForm
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
class TestInvoiceProjectPicker:
    """The project picker on an invoice offers open projects, plus the one it already has."""

    def test_only_open_projects_are_offered_plus_the_current_one(self):
        owner = ClientFactory()
        open_project = ProjectFactory(client=owner, name='Open')
        on_hold = ProjectFactory(client=owner, name='Paused', status=Project.ON_HOLD)
        finished = ProjectFactory(client=owner, name='Done', status=Project.FINISHED)
        admin = AdminUserFactory()

        offered = set(InvoiceForm(user=admin).fields['project'].queryset.filter(client=owner))
        assert offered == {open_project, on_hold}
        editing = InvoiceForm(user=admin, current_project_id=finished.pk)
        assert finished in set(editing.fields['project'].queryset)

    def test_a_finished_project_is_refused_on_a_new_invoice(self):
        owner = ClientFactory()
        finished = ProjectFactory(client=owner, status=Project.FINISHED)
        form = InvoiceForm({'client': owner.pk, 'project': finished.pk, 'issue_date': '2026-10-01',
                            'due_date': '2026-10-31', 'tax_rate': '0'}, user=AdminUserFactory())
        assert not form.is_valid()
        assert 'project' in form.errors