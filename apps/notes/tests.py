import json

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.notes.forms import NoteForm
from apps.notes.models import Note
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


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
        ProjectAccessFactory(project=project, user=user)
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


def _preset(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'access_notes': True,
        'clients_view_all': False,
        'projects_view_all': False,
        'projects_edit_all': False,
        'notes_view_all': False,
        'notes_edit_public': False,
    }
    fields.update(overrides)
    return PermissionPreset.objects.create(name=name, **fields)


def _user(name, **overrides):
    return UserFactory(permission_preset=_preset(name, **overrides))


def _note(*, title, author, client=None, project=None, private=False):
    return Note.objects.create(
        title=title,
        client=client,
        project=project,
        is_private=private,
        created_by=author,
        modified_by=author,
    )


@pytest.mark.django_db
class TestPrivateNotes:
    def test_hidden_from_everyone_except_the_author_including_admin(self, client):
        author = _user('NoteAuthor')
        stranger = _user('NoteStranger', notes_view_all=True, notes_edit_public=True)
        admin = AdminUserFactory()
        client_obj = ClientFactory(created_by=author)
        project = ProjectFactory(client=client_obj)
        ProjectAccessFactory(project=project, user=author)
        private_client = _note(
            title='Secret Client', author=author, client=client_obj, private=True
        )
        private_project = _note(
            title='Secret Project', author=author, project=project, private=True
        )

        for viewer in (admin, stranger):
            client.force_login(viewer)
            client_list = client.get(reverse('client_notes_list', args=[client_obj.pk]))
            project_list = client.get(reverse('project_notes_list', args=[project.pk]))
            profile = client.get(reverse('client_profile_notes', args=[client_obj.pk]))
            assert client_list.status_code == 200
            assert project_list.status_code == 200
            assert profile.status_code == 200
            body = (
                client_list.content.decode()
                + project_list.content.decode()
                + profile.content.decode()
            )
            assert 'Secret Client' not in body
            assert 'Secret Project' not in body
            assert client.get(reverse('note_detail_drawer', args=[private_client.pk])).status_code == 403
            assert client.get(reverse('note_detail_drawer', args=[private_project.pk])).status_code == 403

        client.force_login(author)
        assert 'Secret Client' in client.get(
            reverse('client_notes_list', args=[client_obj.pk])
        ).content.decode()
        assert 'Secret Project' in client.get(
            reverse('project_notes_list', args=[project.pk])
        ).content.decode()
        assert client.get(reverse('note_detail_drawer', args=[private_client.pk])).status_code == 200
        assert client.get(reverse('note_detail_drawer', args=[private_project.pk])).status_code == 200
        profile = client.get(reverse('client_profile_notes', args=[client_obj.pk])).content.decode()
        assert 'Secret Client' in profile
        assert 'Secret Project' in profile


@pytest.mark.django_db
class TestViewOwn:
    def test_public_note_follows_the_parent_they_can_open(self, client):
        viewer = _user('ViewOwn')
        author = _user('PublicAuthor')
        open_client = ClientFactory(created_by=viewer)
        hidden_client = ClientFactory(created_by=author)
        open_project = ProjectFactory(client=open_client)
        hidden_project = ProjectFactory(client=hidden_client)
        ProjectAccessFactory(project=open_project, user=viewer)
        open_client_note = _note(title='Open Client Note', author=author, client=open_client)
        hidden_client_note = _note(title='Hidden Client Note', author=author, client=hidden_client)
        open_project_note = _note(title='Open Project Note', author=author, project=open_project)
        hidden_project_note = _note(
            title='Hidden Project Note', author=author, project=hidden_project
        )

        client.force_login(viewer)
        assert 'Open Client Note' in client.get(
            reverse('client_notes_list', args=[open_client.pk])
        ).content.decode()
        assert 'Hidden Client Note' not in client.get(
            reverse('client_notes_list', args=[hidden_client.pk])
        ).content.decode()
        assert 'Open Project Note' in client.get(
            reverse('project_notes_list', args=[open_project.pk])
        ).content.decode()
        assert 'Hidden Project Note' not in client.get(
            reverse('project_notes_list', args=[hidden_project.pk])
        ).content.decode()
        assert client.get(reverse('note_detail_drawer', args=[open_client_note.pk])).status_code == 200
        assert client.get(reverse('note_detail_drawer', args=[hidden_client_note.pk])).status_code == 403
        assert client.get(reverse('note_detail_drawer', args=[open_project_note.pk])).status_code == 200
        assert client.get(
            reverse('note_detail_drawer', args=[hidden_project_note.pk])
        ).status_code == 403

        open_profile = client.get(
            reverse('client_profile_notes', args=[open_client.pk])
        ).content.decode()
        assert 'Open Client Note' in open_profile
        assert 'Open Project Note' in open_profile
        hidden_profile = client.get(
            reverse('client_profile_notes', args=[hidden_client.pk])
        ).content.decode()
        assert 'Hidden Client Note' not in hidden_profile
        assert 'Hidden Project Note' not in hidden_profile

        wide = _user('WideParent', clients_view_all=True, projects_edit_all=True)
        client.force_login(wide)
        assert 'Hidden Client Note' in client.get(
            reverse('client_notes_list', args=[hidden_client.pk])
        ).content.decode()
        assert client.get(
            reverse('note_detail_drawer', args=[hidden_project_note.pk])
        ).status_code == 200


@pytest.mark.django_db
class TestParentAccessDoesNotListNotes:
    def test_clients_or_projects_access_alone_does_not_list_notes(self, client):
        author = _user('ListedAuthor')
        client_only = _user('ClientsOnly', access_notes=False, clients_view_all=True)
        project_only = _user('ProjectsOnly', access_notes=False, projects_view_all=True)
        row_only = _user('RowOnly', access_notes=False)
        client_obj = ClientFactory(created_by=author)
        project = ProjectFactory(client=client_obj)
        ProjectAccessFactory(project=project, user=author)
        ProjectAccessFactory(project=project, user=row_only)
        _note(title='Client Public', author=author, client=client_obj)
        _note(title='Project Public', author=author, project=project)

        client.force_login(client_only)
        assert client.get(reverse('client_notes_list', args=[client_obj.pk])).status_code == 403
        profile = client.get(reverse('client_profile_notes', args=[client_obj.pk]))
        assert profile.status_code == 200
        profile_body = profile.content.decode()
        assert 'Client Public' not in profile_body
        assert 'Project Public' not in profile_body

        client.force_login(project_only)
        assert client.get(reverse('project_notes_list', args=[project.pk])).status_code == 403
        project_profile = client.get(
            reverse('client_profile_notes', args=[client_obj.pk])
        ).content.decode()
        assert 'Client Public' not in project_profile
        assert 'Project Public' not in project_profile

        client.force_login(row_only)
        assert client.get(reverse('client_notes_list', args=[client_obj.pk])).status_code == 403
        assert client.get(reverse('project_notes_list', args=[project.pk])).status_code == 403


@pytest.mark.django_db
class TestViewAll:
    def test_public_note_on_a_hidden_parent_and_private_stays_hidden(self, client):
        author = _user('FarAuthor')
        viewer = _user('ViewAll', notes_view_all=True)
        hidden_client = ClientFactory(created_by=author)
        hidden_project = ProjectFactory()
        public_client = _note(title='Far Client Note', author=author, client=hidden_client)
        public_project = _note(title='Far Project Note', author=author, project=hidden_project)
        private = _note(title='Far Private', author=author, client=hidden_client, private=True)

        client.force_login(viewer)
        client_list = client.get(
            reverse('client_notes_list', args=[hidden_client.pk])
        ).content.decode()
        assert 'Far Client Note' in client_list
        assert 'Far Private' not in client_list
        assert 'Far Project Note' in client.get(
            reverse('project_notes_list', args=[hidden_project.pk])
        ).content.decode()
        assert client.get(reverse('note_detail_drawer', args=[public_client.pk])).status_code == 200
        assert client.get(reverse('note_detail_drawer', args=[public_project.pk])).status_code == 200
        assert client.get(reverse('note_detail_drawer', args=[private.pk])).status_code == 403
        profile = client.get(
            reverse('client_profile_notes', args=[hidden_client.pk])
        ).content.decode()
        assert 'Far Client Note' in profile
        assert 'Far Private' not in profile
        assert client.post(reverse('client_note_create_drawer', args=[hidden_client.pk]), {
            'title': 'Not Allowed',
            'description': '',
        }).status_code == 403
        assert not Note.objects.filter(title='Not Allowed').exists()


@pytest.mark.django_db
class TestNoteWrites:
    def test_author_edits_and_deletes_own_note(self, client):
        author = _user('Owner')
        client_obj = ClientFactory(created_by=author)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=author)
        own_client = _note(title='Mine Client', author=author, client=client_obj)
        own_project = _note(title='Mine Project', author=author, project=project)
        own_private = _note(title='Mine Private', author=author, client=client_obj, private=True)

        client.force_login(author)
        edited = client.post(reverse('note_edit_drawer', args=[own_client.pk]), {
            'title': 'Mine Client Edited',
            'description': 'updated',
        })
        assert edited.status_code == 200
        own_client.refresh_from_db()
        assert own_client.title == 'Mine Client Edited'

        private_edit = client.post(reverse('note_edit_drawer', args=[own_private.pk]), {
            'title': 'Mine Private Edited',
            'description': '',
            'is_private': 'on',
        })
        assert private_edit.status_code == 200
        own_private.refresh_from_db()
        assert own_private.title == 'Mine Private Edited'
        assert own_private.is_private is True

        deleted = client.post(reverse('note_delete', args=[own_project.pk]))
        assert deleted.status_code == 200
        assert not Note.objects.filter(pk=own_project.pk).exists()

    def test_edit_public_changes_another_public_note_not_a_private_one(self, client):
        author = _user('Writer')
        editor = _user('PublicEditor', notes_edit_public=True)
        hidden_client = ClientFactory(created_by=author)
        hidden_project = ProjectFactory()
        public_client = _note(title='Their Client', author=author, client=hidden_client)
        public_project = _note(title='Their Project', author=author, project=hidden_project)
        private = _note(title='Their Private', author=author, client=hidden_client, private=True)

        client.force_login(editor)
        edited = client.post(reverse('note_edit_drawer', args=[public_client.pk]), {
            'title': 'Edited By Other',
            'description': 'changed',
        })
        assert edited.status_code == 200
        public_client.refresh_from_db()
        assert public_client.title == 'Edited By Other'

        deleted = client.post(reverse('note_delete', args=[public_project.pk]))
        assert deleted.status_code == 200
        assert not Note.objects.filter(pk=public_project.pk).exists()

        assert client.post(reverse('note_edit_drawer', args=[private.pk]), {
            'title': 'Hacked',
            'description': '',
        }).status_code == 403
        assert client.post(reverse('note_delete', args=[private.pk])).status_code == 403
        private.refresh_from_db()
        assert private.title == 'Their Private'
        assert private.is_private is True

        admin = AdminUserFactory()
        client.force_login(admin)
        assert client.post(reverse('note_edit_drawer', args=[private.pk]), {
            'title': 'Admin Hack',
            'description': '',
        }).status_code == 403
        assert client.post(reverse('note_delete', args=[private.pk])).status_code == 403
        private.refresh_from_db()
        assert private.title == 'Their Private'

    def test_create_on_a_client_or_project_they_can_open(self, client):
        user = _user('Creator', projects_view_all=True)
        visible = ClientFactory(created_by=user)
        hidden = ClientFactory()
        project = ProjectFactory()
        client.force_login(user)

        created = client.post(reverse('client_note_create_drawer', args=[visible.pk]), {
            'title': 'New Client Note',
            'description': 'hi',
            'is_private': 'on',
        })
        assert created.status_code == 200
        note = Note.objects.get(title='New Client Note')
        assert note.client_id == visible.pk
        assert note.is_private is True
        assert note.created_by_id == user.id

        assert client.post(reverse('client_note_create_drawer', args=[hidden.pk]), {
            'title': 'Should Not',
            'description': '',
        }).status_code == 403
        assert not Note.objects.filter(title='Should Not').exists()

        project_note = client.post(reverse('project_note_create_drawer', args=[project.pk]), {
            'title': 'New Project Note',
            'description': '',
        })
        assert project_note.status_code == 200
        assert Note.objects.filter(
            title='New Project Note', project=project, created_by=user
        ).exists()
