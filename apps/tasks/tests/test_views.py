import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.factories import UserFactory
from apps.tasks.factories import TaskFactory, SubtaskFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory, StatusFactory


@pytest.mark.django_db
class TestMyTasks:
    def test_my_tasks_requires_login(self, client):
        response = client.get(reverse('my_tasks'))
        assert response.status_code == 302

    def test_my_tasks_shows_only_assigned(self, client):
        user = UserFactory()
        other = UserFactory()
        project = ProjectFactory()
        status = project.statuses.first()
        TaskFactory(project=project, status=status, assignee=user, title='My Task')
        TaskFactory(project=project, status=status, assignee=other, title='Other Task')
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        content = response.content.decode()
        assert 'My Task' in content
        assert 'Other Task' not in content


@pytest.mark.django_db
class TestTaskCreate:
    def test_task_create_requires_login(self, client):
        project = ProjectFactory()
        response = client.get(reverse('task_create', args=[project.pk]))
        assert response.status_code == 302

    def test_task_create_requires_editor_role(self, client):
        """Viewers cannot create tasks."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Description'}
        )
        assert response.status_code == 403

    def test_task_create_with_valid_data(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Description'}
        )
        assert response.status_code == 302
        from apps.tasks.models import Task
        assert Task.objects.filter(title='New Task').exists()

    def test_task_create_records_activity_with_user(self, client):
        """Creating a task records activity with the creating user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status = StatusFactory(project=project)
        client.force_login(user)

        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Test'}
        )

        task = project.tasks.first()
        activity = TaskActivity.objects.filter(task=task, activity_type='created').first()
        assert activity is not None
        assert activity.user == user


@pytest.mark.django_db
class TestTaskEdit:
    def test_task_edit_records_activity_with_user(self, client):
        """Editing a task via form records activity with the editing user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status = StatusFactory(project=project, name='Backlog')
        task = TaskFactory(project=project, status=status, priority='low')
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_edit', args=[task.pk]),
            {'title': 'Updated Title', 'description': 'Updated', 'priority': 'high'}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='priority_change').first()
        assert activity is not None
        assert activity.user == user


@pytest.mark.django_db
class TestTaskMove:
    def test_move_task_to_new_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )
        assert response.status_code == 204
        task.refresh_from_db()
        assert task.status == status2

    def test_move_task_requires_editor(self, client):
        """Viewers cannot move tasks."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )
        assert response.status_code == 403

    def test_move_task_invalid_status(self, client):
        user = UserFactory()
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        ProjectMemberFactory(project=project1, user=user, role='editor')
        task = TaskFactory(project=project1, status=project1.statuses.first())
        other_status = project2.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': other_status.pk}
        )
        assert response.status_code == 404

    def test_task_move_records_activity_with_user(self, client):
        """Moving a task (drag-drop) records activity with the user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user


class TestTaskUpdateStatus:
    @pytest.mark.django_db
    def test_task_update_status_records_activity_with_user(self, client):
        """Changing status via dropdown records activity with the user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='In Progress')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_update_status', args=[task.pk]),
            {'status_id': status2.pk}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user


@pytest.mark.django_db
class TestSubtasks:
    def test_create_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        client.force_login(user)
        response = client.post(
            reverse('subtask_create', args=[task.pk]),
            {'title': 'New Subtask'}
        )
        assert response.status_code == 200
        assert task.subtasks.filter(title='New Subtask').exists()

    def test_toggle_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task, completed=False)
        client.force_login(user)
        response = client.post(
            reverse('subtask_toggle', args=[task.pk, subtask.pk])
        )
        assert response.status_code == 200
        subtask.refresh_from_db()
        assert subtask.completed is True

    def test_delete_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task)
        client.force_login(user)
        response = client.post(
            reverse('subtask_delete', args=[task.pk, subtask.pk])
        )
        assert response.status_code == 200
        assert not task.subtasks.filter(pk=subtask.pk).exists()


@pytest.mark.django_db
@pytest.mark.security
class TestAttachmentUpload:
    def test_upload_valid_file(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        file = SimpleUploadedFile('test.txt', b'file content', content_type='text/plain')
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': file}
        )
        assert response.status_code == 200
        assert task.attachments.count() == 1

    def test_upload_no_file(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {}
        )
        assert response.status_code == 400

    def test_upload_requires_editor(self, client):
        """Viewers cannot upload attachments."""
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        file = SimpleUploadedFile('test.txt', b'file content', content_type='text/plain')
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': file}
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestComments:
    def test_create_comment(self, client):
        """Viewers can create comments."""
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'This is a comment'}
        )
        assert response.status_code == 200
        assert task.activities.filter(activity_type='comment').exists()

    def test_empty_comment_rejected(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': '   '}
        )
        assert response.status_code == 400

    def test_comment_requires_access(self, client):
        """Users without project access cannot comment."""
        user = UserFactory()
        task = TaskFactory()
        # No membership created
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'This is a comment'}
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestMyTasksTabs:
    def test_my_tasks_default_tab_is_tasks(self, client):
        """GET /tasks/my/ should set active_tab to 'tasks'"""
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'tasks'

    def test_my_tasks_todos_tab(self, client):
        """GET /tasks/my/todos/ should set active_tab to 'todos'"""
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('my_tasks_todos'))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'todos'
