from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.clients.models import Client

from ..models import Todo

User = get_user_model()


class TodoModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            name='Test User',
        )
        self.client = Client.objects.create(
            name='Test Client',
            email='client@example.com',
            phone='123-456-7890'
        )

    def test_todo_creation(self):
        """Test creating a personal todo."""
        todo = Todo.objects.create(
            owner=self.user,
            title='Test Todo',
            description='Test description',
            due_date=timezone.now().date()
        )
        self.assertEqual(todo.owner, self.user)
        self.assertEqual(todo.title, 'Test Todo')
        self.assertEqual(todo.description, 'Test description')
        self.assertFalse(todo.is_completed)
        self.assertIsNone(todo.completed_at)
        self.assertEqual(str(todo), 'Test Todo')

    def test_client_todo_creation(self):
        """Test creating a client-linked todo."""
        todo = Todo.objects.create(
            owner=self.user,
            client=self.client,
            title='Client Todo'
        )
        self.assertEqual(todo.client, self.client)
        self.assertEqual(todo.title, 'Client Todo')

    def test_todo_completion(self):
        """Test marking a todo as completed."""
        todo = Todo.objects.create(
            owner=self.user,
            title='Test Todo'
        )
        # Initially not completed
        self.assertFalse(todo.is_completed)
        self.assertIsNone(todo.completed_at)

        # Mark as completed
        todo.is_completed = True
        todo.completed_at = timezone.now()
        todo.save()

        self.assertTrue(todo.is_completed)
        self.assertIsNotNone(todo.completed_at)

    def test_todo_ordering(self):
        """Test todos are ordered correctly."""
        # Create todos with different states
        todo1 = Todo.objects.create(owner=self.user, title='Completed Todo')
        todo1.is_completed = True
        todo1.save()

        todo2 = Todo.objects.create(
            owner=self.user,
            title='Due Tomorrow',
            due_date=timezone.now().date() + timezone.timedelta(days=1)
        )

        todo3 = Todo.objects.create(
            owner=self.user,
            title='Due Today',
            due_date=timezone.now().date()
        )

        todos = list(Todo.objects.all())
        # Incomplete todos should come first, ordered by due date, then by created_at desc
        self.assertEqual(todos[0], todo3)  # Due today (incomplete)
        self.assertEqual(todos[1], todo2)  # Due tomorrow (incomplete)
        self.assertEqual(todos[2], todo1)  # Completed

    def test_todo_private_to_owner(self):
        """Test todos are private to their owner."""
        other_user = User.objects.create_user(
            email='other@example.com',
            password='otherpass123',
            name='Other User',
        )

        todo = Todo.objects.create(
            owner=self.user,
            title='My Todo'
        )

        # Should only find todos for the correct owner
        user_todos = Todo.objects.filter(owner=self.user)
        other_todos = Todo.objects.filter(owner=other_user)

        self.assertIn(todo, user_todos)
        self.assertNotIn(todo, other_todos)
