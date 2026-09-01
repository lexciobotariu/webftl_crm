import json

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.clients.factories import ClientFactory
from apps.notes.forms import NoteForm
from apps.notes.models import Note
from apps.projects.factories import ProjectFactory, ProjectMemberFactory


@pytest.mark.django_db
class TestNoteForm:
    def test_form_invalid_without_parent(self):
        form = NoteForm({'title': 'Orphan note'})
        assert not form.is_valid()
        assert 'client or a project' in str(form.non_field_errors())

    def test_form_valid_with_client_parent(self):
        client_obj = ClientFactory()
        form = NoteForm({'title': 'Client note'}, client=client_obj)
        assert form.is_valid()

    def test_form_valid_with_project_parent(self):
        project = ProjectFactory()
        form = NoteForm({'title': 'Project note'}, project=project)
        assert form.is_valid()


@pytest.mark.django_db
class TestNoteCreateDrawer:
    def test_create_client_note(self, client):
        admin = AdminUserFactory()
        client_obj = ClientFactory()
        client.force_login(admin)
        response = client.post(
            reverse('client_note_create_drawer', args=[client_obj.pk]),
            {'title': 'Client note', 'description': 'Details'},
        )
        assert response.status_code == 200
        note = Note.objects.get(title='Client note')
        assert note.client == client_obj
        assert note.project is None
        triggers = json.loads(response['HX-Trigger'])
        assert triggers['notesChanged'] is True
        assert triggers['closeSlideOver'] is True

    def test_create_project_note(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        client.force_login(user)
        response = client.post(
            reverse('project_note_create_drawer', args=[project.pk]),
            {'title': 'Project note', 'description': 'Details'},
        )
        assert response.status_code == 200
        note = Note.objects.get(title='Project note')
        assert note.project == project
        assert note.client is None
        triggers = json.loads(response['HX-Trigger'])
        assert triggers['notesChanged'] is True

    def test_create_rejects_empty_title(self, client):
        admin = AdminUserFactory()
        client_obj = ClientFactory()
        client.force_login(admin)
        response = client.post(
            reverse('client_note_create_drawer', args=[client_obj.pk]),
            {'title': '   '},
        )
        assert response.status_code == 200
        assert not Note.objects.exists()
        assert b'required' in response.content.lower()


@pytest.mark.django_db
class TestNoteEditDrawer:
    def test_edit_note(self, client):
        admin = AdminUserFactory()
        client_obj = ClientFactory()
        note = Note.objects.create(
            client=client_obj,
            title='Original',
            description='Old',
            created_by=admin,
            modified_by=admin,
        )
        client.force_login(admin)
        response = client.post(
            reverse('note_edit_drawer', args=[note.pk]),
            {'title': 'Updated', 'description': 'New text'},
        )
        assert response.status_code == 200
        note.refresh_from_db()
        assert note.title == 'Updated'
        assert note.description == 'New text'
        triggers = json.loads(response['HX-Trigger'])
        assert triggers['notesChanged'] is True
