"""
Tests for race conditions in concurrent operations.
These tests verify data integrity under concurrent access.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.test import TransactionTestCase
from django.db import connection
from apps.projects.factories import ProjectFactory
from apps.tasks.factories import TaskFactory


@pytest.mark.race
class TestStatusOrderRace(TransactionTestCase):
    """Test race conditions in status ordering."""

    @pytest.mark.xfail(reason="Known race condition: status.order = project.statuses.count() is not atomic")
    def test_concurrent_status_creation(self):
        """Multiple concurrent status creations should have unique orders."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        project = ProjectFactory()
        user = UserFactory()
        initial_count = project.statuses.count()

        def create_status(name):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('status_create', args=[project.pk]),
                {'name': name}
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_status, f'Status {i}')
                for i in range(5)
            ]
            for future in as_completed(futures):
                future.result()

        project.refresh_from_db()
        new_count = project.statuses.count()
        assert new_count == initial_count + 5

        # Check for duplicate orders (race condition symptom)
        orders = list(project.statuses.values_list('order', flat=True))
        assert len(orders) == len(set(orders)), "Duplicate order values detected!"


@pytest.mark.race
class TestSubtaskOrderRace(TransactionTestCase):
    """Test race conditions in subtask ordering."""

    @pytest.mark.xfail(reason="Known race condition: subtask.order = task.subtasks.count() is not atomic")
    def test_concurrent_subtask_creation(self):
        """Multiple concurrent subtask creations should have unique orders."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        task = TaskFactory()
        user = UserFactory()

        def create_subtask(title):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('subtask_create', args=[task.pk]),
                {'title': title}
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_subtask, f'Subtask {i}')
                for i in range(5)
            ]
            for future in as_completed(futures):
                future.result()

        task.refresh_from_db()
        assert task.subtasks.count() == 5

        # Check for duplicate orders (race condition symptom)
        orders = list(task.subtasks.values_list('order', flat=True))
        assert len(orders) == len(set(orders)), "Duplicate subtask order values detected!"


@pytest.mark.race
class TestTaskMoveRace(TransactionTestCase):
    """Test race conditions in task movement."""

    def test_concurrent_task_moves(self):
        """Concurrent moves of same task should result in consistent state."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        project = ProjectFactory()
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        user = UserFactory()

        def move_task(status_id):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('task_move'),
                {'task_id': task.pk, 'status_id': status_id}
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(move_task, status1.pk),
                executor.submit(move_task, status2.pk),
            ]
            for future in as_completed(futures):
                future.result()

        task.refresh_from_db()
        # Task should be in one valid status
        assert task.status in [status1, status2]
