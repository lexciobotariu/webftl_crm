"""
Tests for race conditions in concurrent operations.
These tests verify data integrity under concurrent access.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.test import TransactionTestCase

from apps.projects.factories import ProjectFactory
from apps.tasks.factories import TaskFactory


@pytest.mark.race
class TestStatusOrderRace(TransactionTestCase):
    """Test race conditions in status ordering."""

    def test_concurrent_status_creation(self):
        """Multiple concurrent status creations should have unique orders."""
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectMemberFactory

        project = ProjectFactory()
        user = UserFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        initial_count = project.statuses.count()

        def create_status(name):
            try:
                client = Client()
                client.force_login(user)
                return client.post(
                    reverse('status_create', args=[project.pk]),
                    {'name': name}
                )
            finally:
                from django.db import connection
                connection.close()

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

    def test_concurrent_subtask_creation(self):
        """Multiple concurrent subtask creations should have unique orders."""
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectMemberFactory

        task = TaskFactory()
        user = UserFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        def create_subtask(title):
            try:
                client = Client()
                client.force_login(user)
                return client.post(
                    reverse('subtask_create', args=[task.pk]),
                    {'title': title}
                )
            finally:
                from django.db import connection
                connection.close()

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
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectMemberFactory

        project = ProjectFactory()
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        user = UserFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')

        def move_task(status_id):
            try:
                client = Client()
                client.force_login(user)
                return client.post(
                    reverse('task_move'),
                    {'task_id': task.pk, 'status_id': status_id}
                )
            finally:
                from django.db import connection
                connection.close()

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

    def test_concurrent_reorders_leave_a_consistent_column(self):
        """Concurrent drags within one column must not corrupt `order`."""
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectMemberFactory
        from apps.tasks.models import Task

        project = ProjectFactory()
        status = project.statuses.first()
        tasks = [
            TaskFactory(project=project, status=status, order=i)
            for i in range(5)
        ]
        user = UserFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')

        def reorder(task_id, position):
            try:
                client = Client()
                client.force_login(user)
                return client.post(
                    reverse('task_move'),
                    {'task_id': task_id, 'status_id': status.pk, 'position': position},
                )
            finally:
                from django.db import connection
                connection.close()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(reorder, task.pk, (index + 2) % 5)
                for index, task in enumerate(tasks)
            ]
            for future in as_completed(futures):
                assert future.result().status_code == 204

        orders = list(
            Task.objects.filter(status=status).order_by('order').values_list('order', flat=True)
        )
        assert orders == list(range(5)), f"Column order is not a dense sequence: {orders}"
