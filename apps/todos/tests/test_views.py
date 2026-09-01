from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permissions import PermissionPreset
from apps.clients.models import Client

from ..models import Todo

User = get_user_model()


class TodoViewTest(TestCase):
    def setUp(self):
        self.client = DjangoTestClient()
        preset = PermissionPreset.objects.create(
            name='TodoTester',
            access_dashboard=True,
            access_todos=True,
            access_clients=True,
        )
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            name='Test User',
            permission_preset=preset,
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='otherpass123',
            name='Other User',
        )
        self.client_obj = Client.objects.create(
            name='Test Client',
            email='client@example.com',
            phone='123-456-7890'
        )
        self.client.force_login(self.user)

    def test_todo_list_view(self):
        """Test the todo list view."""
        # Create some todos
        Todo.objects.create(owner=self.user, title='Todo 1')
        Todo.objects.create(owner=self.user, title='Todo 2', is_completed=True)

        response = self.client.get(reverse('todo_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Todo 1')
        self.assertNotContains(response, 'Todo 2')  # Completed hidden by default

    def test_todo_list_with_completed(self):
        """Test showing completed todos."""
        Todo.objects.create(owner=self.user, title='Todo 1', is_completed=True)

        response = self.client.get(reverse('todo_list') + '?show_completed=true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Todo 1')

    def test_todo_create_get(self):
        """Test getting the create todo form."""
        response = self.client.get(reverse('todo_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add To-Do')

    def test_todo_create_post(self):
        """Test creating a new todo."""
        response = self.client.post(reverse('todo_create'), {
            'title': 'New Todo',
            'description': 'Description',
            'due_date': '2026-12-31'
        })
        self.assertEqual(response.status_code, 200)

        # Check todo was created
        todo = Todo.objects.get(title='New Todo')
        self.assertEqual(todo.owner, self.user)
        self.assertEqual(todo.description, 'Description')

    def test_todo_create_with_client(self):
        """Test creating a todo with a client."""
        response = self.client.post(reverse('todo_create'), {
            'title': 'Client Todo',
            'client': self.client_obj.id
        })
        self.assertEqual(response.status_code, 200)

        todo = Todo.objects.get(title='Client Todo')
        self.assertEqual(todo.client, self.client_obj)

    def test_todo_detail_view(self):
        """Test viewing a todo detail."""
        todo = Todo.objects.create(owner=self.user, title='Test Todo')

        response = self.client.get(reverse('todo_detail', args=[todo.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Todo')

    def test_todo_detail_other_user_denied(self):
        """Test cannot view another user's todo."""
        todo = Todo.objects.create(owner=self.other_user, title='Other Todo')

        response = self.client.get(reverse('todo_detail', args=[todo.id]))
        self.assertEqual(response.status_code, 404)

    def test_todo_toggle(self):
        """Test toggling todo completion."""
        todo = Todo.objects.create(owner=self.user, title='Test Todo')

        # Mark as completed
        response = self.client.post(reverse('todo_toggle', args=[todo.id]))
        self.assertEqual(response.status_code, 200)

        todo.refresh_from_db()
        self.assertTrue(todo.is_completed)
        self.assertIsNotNone(todo.completed_at)

    def test_todo_delete(self):
        """Test deleting a todo."""
        todo = Todo.objects.create(owner=self.user, title='Test Todo')

        response = self.client.post(reverse('todo_delete', args=[todo.id]))
        self.assertEqual(response.status_code, 200)

        with self.assertRaises(Todo.DoesNotExist):
            Todo.objects.get(id=todo.id)

    def test_client_todo_list(self):
        """Test viewing todos for a specific client."""
        Todo.objects.create(owner=self.user, client=self.client_obj, title='Client Todo')
        Todo.objects.create(owner=self.user, title='Personal Todo')

        response = self.client.get(reverse('client_todo_list', args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client Todo')
        self.assertNotContains(response, 'Personal Todo')

    def test_client_todo_create(self):
        """Test creating a todo from client page."""
        response = self.client.post(reverse('client_todo_create', args=[self.client_obj.id]), {
            'title': 'New Client Todo',
            'description': 'For client'
        })
        self.assertEqual(response.status_code, 200)

        todo = Todo.objects.get(title='New Client Todo')
        self.assertEqual(todo.client, self.client_obj)

    def test_unauthenticated_access_denied(self):
        """Test unauthenticated users cannot access todo views."""
        self.client.logout()

        urls = [
            reverse('todo_list'),
            reverse('todo_create'),
            reverse('todo_detail', args=[1]),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)  # Redirect to login
