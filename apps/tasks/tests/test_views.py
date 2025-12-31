import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.factories import UserFactory
from apps.tasks.factories import TaskFactory, SubtaskFactory
from apps.projects.factories import ProjectFactory


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

    def test_task_create_with_valid_data(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Description'}
        )
        assert response.status_code == 302
        from apps.tasks.models import Task
        assert Task.objects.filter(title='New Task').exists()


@pytest.mark.django_db
class TestTaskMove:
    def test_move_task_to_new_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
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

    def test_move_task_invalid_status(self, client):
        user = UserFactory()
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        task = TaskFactory(project=project1, status=project1.statuses.first())
        other_status = project2.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': other_status.pk}
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSubtasks:
    def test_create_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
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
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {}
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestComments:
    def test_create_comment(self, client):
        user = UserFactory()
        task = TaskFactory()
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
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': '   '}
        )
        assert response.status_code == 400
