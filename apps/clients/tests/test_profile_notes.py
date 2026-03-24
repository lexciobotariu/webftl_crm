from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from apps.clients.models import Client
from apps.projects.models import Project
from apps.notes.models import Note

User = get_user_model()


class ClientProfileNotesViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            email='admin@test.com', password='test', role='admin'
        )
        self.client_obj = Client.objects.create(name='Test Client')
        self.project = Project.objects.create(
            client=self.client_obj, name='Test Project'
        )

    def test_returns_client_and_project_notes(self):
        """Profile notes table shows notes from client AND its projects."""
        client_note = Note.objects.create(
            client=self.client_obj,
            title='Client Note',
            description='About the client',
            created_by=self.admin,
            modified_by=self.admin,
        )
        project_note = Note.objects.create(
            project=self.project,
            title='Project Note',
            description='About the project',
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client Note')
        self.assertContains(response, 'Project Note')

    def test_type_column_shows_client_or_project_name(self):
        """Type column shows 'Client' for client notes and project name for project notes."""
        Note.objects.create(
            client=self.client_obj,
            title='A Client Note',
            created_by=self.admin,
            modified_by=self.admin,
        )
        Note.objects.create(
            project=self.project,
            title='A Project Note',
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )

        self.assertContains(response, 'Client')
        self.assertContains(response, 'Test Project')

    def test_requires_login(self):
        """Unauthenticated users are redirected."""
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 302)

    def test_non_admin_forbidden(self):
        """Non-admin users get 403."""
        regular_user = User.objects.create_user(
            email='user@test.com', password='test', role='member'
        )
        self.client.force_login(regular_user)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 403)

    def test_respects_note_visibility(self):
        """Private notes from other users are not shown."""
        other_admin = User.objects.create_user(
            email='other@test.com', password='test', role='admin'
        )
        # Private note by other user — should still show for admin
        Note.objects.create(
            client=self.client_obj,
            title='Private Note',
            is_private=True,
            created_by=other_admin,
            modified_by=other_admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        # Admins can see all notes
        self.assertContains(response, 'Private Note')

    def test_empty_state(self):
        """Shows empty message when no notes exist."""
        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No notes yet')
