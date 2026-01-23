# apps/tasks/tests/test_services.py
import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory, StatusFactory
from apps.tasks import services
from apps.tasks.factories import SubtaskFactory, TaskFactory
from apps.tasks.models import Subtask, TaskActivity


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


@pytest.mark.django_db
class TestSubtaskServices:
    def test_create_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        subtask = services.create_subtask(task, 'New subtask', user)

        assert subtask.task == task
        assert subtask.title == 'New subtask'
        assert subtask.completed is False

    def test_create_subtask_auto_orders(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        SubtaskFactory(task=task, order=0)
        SubtaskFactory(task=task, order=1)

        subtask = services.create_subtask(task, 'Third', user)

        assert subtask.order == 2

    def test_create_subtask_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.create_subtask(task, 'Subtask', user)

    def test_toggle_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task, completed=False)

        result = services.toggle_subtask(subtask, user)

        subtask.refresh_from_db()
        assert subtask.completed is True
        assert result == subtask

    def test_toggle_subtask_again(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task, completed=True)

        services.toggle_subtask(subtask, user)

        subtask.refresh_from_db()
        assert subtask.completed is False

    def test_delete_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task)
        subtask_pk = subtask.pk

        services.delete_subtask(subtask, user)

        assert not Subtask.objects.filter(pk=subtask_pk).exists()

    def test_delete_subtask_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        subtask = SubtaskFactory(task=task)

        with pytest.raises(PermissionDenied):
            services.delete_subtask(subtask, user)


@pytest.mark.django_db
class TestCommentService:
    def test_add_comment(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        activity = services.add_comment(task, 'This is a comment', user)

        assert activity.task == task
        assert activity.user == user
        assert activity.activity_type == 'comment'
        assert activity.content == 'This is a comment'

    def test_add_comment_requires_viewer(self):
        user = UserFactory()
        task = TaskFactory()
        # No membership

        with pytest.raises(PermissionDenied):
            services.add_comment(task, 'Comment', user)


@pytest.mark.django_db
class TestAttachmentService:
    def test_validate_upload_valid_file(self):
        file = SimpleUploadedFile('test.pdf', b'content', content_type='application/pdf')

        error = services.validate_upload(file)

        assert error is None

    def test_validate_upload_no_file(self):
        error = services.validate_upload(None)

        assert error is not None
        assert 'No file provided' in error.message

    def test_validate_upload_invalid_extension(self):
        file = SimpleUploadedFile('test.exe', b'content')

        error = services.validate_upload(file)

        assert error is not None
        assert 'not allowed' in error.message

    def test_validate_upload_file_too_large(self):
        # Create file larger than 10MB
        large_content = b'x' * (11 * 1024 * 1024)
        file = SimpleUploadedFile('test.txt', large_content)

        error = services.validate_upload(file)

        assert error is not None
        assert 'too large' in error.message

    def test_upload_attachment(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        file = SimpleUploadedFile('test.txt', b'content', content_type='text/plain')

        attachment = services.upload_attachment(task, file, user)

        assert attachment.task == task
        assert attachment.uploaded_by == user
        assert attachment.filename == 'test.txt'

    def test_upload_attachment_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        file = SimpleUploadedFile('test.txt', b'content')

        with pytest.raises(PermissionDenied):
            services.upload_attachment(task, file, user)

    def test_upload_attachment_validates_file(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        file = SimpleUploadedFile('test.exe', b'content')

        with pytest.raises(ValueError) as exc_info:
            services.upload_attachment(task, file, user)

        assert 'not allowed' in str(exc_info.value)
