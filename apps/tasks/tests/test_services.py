# apps/tasks/tests/test_services.py
import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory, StatusFactory
from apps.tasks import services
from apps.tasks.factories import TaskFactory
from apps.tasks.models import TaskActivity


@pytest.mark.django_db
class TestPermissions:
    def test_require_access_raises_for_non_member(self):
        user = UserFactory()
        project = ProjectFactory()
        # No membership created

        with pytest.raises(PermissionDenied) as exc_info:
            services.require_access(user, project, 'editor')

        assert 'Editor access required' in str(exc_info.value)

    def test_require_access_passes_for_editor(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')

        # Should not raise
        services.require_access(user, project, 'editor')

    def test_require_access_passes_for_admin(self):
        from apps.accounts.factories import AdminUserFactory
        admin = AdminUserFactory()
        project = ProjectFactory()
        # No membership needed for admin

        # Should not raise
        services.require_access(admin, project, 'manager')


@pytest.mark.django_db
class TestUpdateTaskField:
    def test_update_task_field_changes_value(self):
        user = UserFactory()
        task = TaskFactory(priority='low')
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        result = services.update_task_field(task, 'priority', 'high', user)

        task.refresh_from_db()
        assert task.priority == 'high'
        assert result == task

    def test_update_task_field_creates_activity(self):
        user = UserFactory()
        task = TaskFactory(priority='low')
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        TaskActivity.objects.filter(task=task).delete()

        services.update_task_field(task, 'priority', 'high', user)

        activity = TaskActivity.objects.filter(task=task, activity_type='priority_change').first()
        assert activity is not None
        assert activity.user == user

    def test_update_task_field_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.update_task_field(task, 'priority', 'high', user)


@pytest.mark.django_db
class TestMoveTask:
    def test_move_task_changes_status(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='editor')

        services.move_task(task, status2, user)

        task.refresh_from_db()
        assert task.status == status2

    def test_move_task_creates_activity(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='editor')
        TaskActivity.objects.filter(task=task).delete()

        services.move_task(task, status2, user)

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user

    def test_move_task_requires_editor(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.move_task(task, status2, user)
