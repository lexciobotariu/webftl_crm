"""The client message log: internal notes, and later the emails sent to the client."""
import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientMessage, messages_visible_to
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def _member(name='Member', **flags):
    fields = {'access_dashboard': True, 'access_clients': True, 'access_projects': True, 'clients_view_all': True}
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


def _post(client, owner, **data):
    return client.post(reverse('client_message_create', args=[owner.pk]), data, HTTP_HX_REQUEST='true')


@pytest.mark.django_db
class TestNotes:
    def test_a_note_is_added_and_shown_newest_first(self, client):
        owner = ClientFactory()
        project = ProjectFactory(client=owner, name='Website')
        admin = AdminUserFactory()
        client.force_login(admin)

        _post(client, owner, body='Kickoff call, **budget agreed**')
        response = _post(client, owner, body='Sent the mockups', project=project.pk)
        assert response['HX-Trigger'] == 'messagesChanged'
        html = response.content.decode()
        assert html.index('Sent the mockups') < html.index('Kickoff call')
        assert '<strong>budget agreed</strong>' in html

        latest = owner.messages.first()
        assert (latest.kind, latest.project, latest.author) == (ClientMessage.NOTE, project, admin)

        page = client.get(reverse('client_detail_messages', args=[owner.pk]))
        assert page.context['active_tab'] == 'messages'
        assert page.context['message_count'] == 2

    def test_an_empty_note_or_a_foreign_project_is_refused(self, client):
        owner = ClientFactory()
        other = ProjectFactory()
        client.force_login(AdminUserFactory())

        assert 'Write something first' in _post(client, owner, body='   ').content.decode()
        body = _post(client, owner, body='Keep me', project=other.pk).content.decode()
        assert "Choose one of this client" in body
        assert 'Keep me' in body
        assert not owner.messages.exists()

    def test_only_the_author_or_an_admin_deletes_a_note(self, client):
        owner = ClientFactory()
        author, other = _member('A'), _member('B')
        note = ClientMessage.objects.create(client=owner, body='Mine', author=author)

        client.force_login(other)
        response = client.post(reverse('client_message_delete', args=[owner.pk, note.pk]))
        assert response.status_code == 403

        client.force_login(author)
        client.post(reverse('client_message_delete', args=[owner.pk, note.pk]))
        assert not ClientMessage.objects.filter(pk=note.pk).exists()

    def test_a_logged_email_is_not_deleted(self, client):
        owner = ClientFactory()
        email = ClientMessage.objects.create(client=owner, kind=ClientMessage.EMAIL, subject='Invoice', body='x')
        client.force_login(AdminUserFactory())
        assert client.post(reverse('client_message_delete', args=[owner.pk, email.pk])).status_code == 400


@pytest.mark.django_db
class TestVisibility:
    def test_notes_on_projects_out_of_sight_are_hidden(self):
        owner = ClientFactory()
        mine, hidden = ProjectFactory(client=owner), ProjectFactory(client=owner)
        user = _member(projects_view_all=False)
        ProjectAccessFactory(project=mine, user=user)
        general = ClientMessage.objects.create(client=owner, body='General')
        on_mine = ClientMessage.objects.create(client=owner, project=mine, body='Mine')
        ClientMessage.objects.create(client=owner, project=hidden, body='Hidden')

        assert set(messages_visible_to(user, owner)) == {general, on_mine}

    def test_a_client_out_of_sight_takes_no_notes(self, client):
        owner = ClientFactory()
        client.force_login(_member(clients_view_all=False))
        assert _post(client, owner, body='Nope').status_code == 404
