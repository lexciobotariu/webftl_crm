import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory, StatusFactory
from apps.tasks.factories import SubtaskFactory, TaskFactory
from apps.tasks.models import Task


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
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, status=status, assignee=user, title='My Task')
        TaskFactory(project=project, status=status, assignee=other, title='Other Task')
        client.force_login(user)
        response = client.get(reverse('my_tasks'), {'layout': 'list'})
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
        """A person without a ProjectAccess row cannot create tasks."""
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Description'}
        )
        assert response.status_code == 403

    def test_task_create_with_valid_data(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        ProjectAccessFactory(project=project, user=user)
        StatusFactory(project=project)
        client.force_login(user)

        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Test'}
        )
        assert response.status_code in (200, 302)

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
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.get(name='Backlog')
        task = TaskFactory(project=project, status=status, priority='low')
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_edit', args=[task.pk]),
            {'title': 'Updated Title', 'description': 'Updated', 'priority': 'high'}
        )
        assert response.status_code in (200, 302)

        activity = TaskActivity.objects.filter(task=task, activity_type='priority_change').first()
        assert activity is not None
        assert activity.user == user


@pytest.mark.django_db
class TestTaskMove:
    def test_move_task_to_new_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        """A person without a ProjectAccess row cannot move tasks."""
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
        assert response.status_code == 403

    def test_move_task_invalid_status(self, client):
        user = UserFactory()
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        ProjectAccessFactory(project=project1, user=user)
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
        ProjectAccessFactory(project=project, user=user)
        status1 = project.statuses.get(name='Backlog')
        status2 = project.statuses.get(name='Done')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )
        assert response.status_code == 204

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
        ProjectAccessFactory(project=project, user=user)
        status1 = project.statuses.get(name='Backlog')
        status2 = project.statuses.get(name='In Progress')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_update_status', args=[task.pk]),
            {'status_id': status2.pk}
        )
        assert response.status_code == 200

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user

    @pytest.mark.django_db
    def test_task_update_status_renders_new_status_in_dropdown(self, client):
        """The swapped dropdown must show the status the task was just moved to,
        not the stale pre-move status from the caller's instance."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status1 = project.statuses.get(name='Backlog')
        status2 = project.statuses.get(name='In Progress')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        response = client.post(
            reverse('task_update_status', args=[task.pk]),
            {'status_id': status2.pk}
        )
        assert response.status_code == 200
        content = response.content.decode()
        # The button label (<span>...</span>) shows the current status; the
        # option list also contains both names, so assert on the label markup.
        assert f'<span>{status2.name}</span>' in content
        assert f'<span>{status1.name}</span>' not in content


@pytest.mark.django_db
class TestSubtasks:
    def test_create_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=user)
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
        ProjectAccessFactory(project=task.project, user=user)
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
        ProjectAccessFactory(project=task.project, user=user)
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
        ProjectAccessFactory(project=task.project, user=user)
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
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {}
        )
        assert response.status_code == 400

    def test_upload_requires_editor(self, client):
        """A person without a ProjectAccess row cannot upload attachments."""
        user = UserFactory()
        task = TaskFactory()
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
        """Editors can create comments."""
        user = UserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'This is a comment'}
        )
        assert response.status_code == 200
        assert task.activities.filter(activity_type='comment').exists()

    def test_viewer_cannot_comment(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'This is a comment'}
        )
        assert response.status_code == 403
        assert not task.activities.filter(activity_type='comment').exists()

    def test_empty_comment_rejected(self, client):
        user = UserFactory()
        task = TaskFactory()
        ProjectAccessFactory(project=task.project, user=user)
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
        response = client.get(reverse('my_tasks'), {'layout': 'list'})
        assert response.status_code == 200
        assert response.context['active_tab'] == 'tasks'

    def test_my_tasks_todos_tab(self, client):
        """GET /tasks/my/todos/ should set active_tab to 'todos'"""
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('my_tasks_todos'))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'todos'


@pytest.mark.django_db
class TestTaskChangedTrigger:
    """Every property edit tells the Tasks page to re-fetch its rows."""

    @pytest.mark.parametrize('route,payload', [
        ('task_update_assignee', {'assignee_id': ''}),
        ('task_update_priority', {'priority': 'high'}),
        ('task_update_due_date', {'due_date': '2030-01-02'}),
        ('task_update_estimate', {'time_estimate': '3'}),
        ('task_edit_title', {'title': 'A new title'}),
    ])
    def test_property_updates_emit_task_changed(self, client, route, payload):
        from apps.accounts.factories import AdminUserFactory

        task = TaskFactory()
        client.force_login(AdminUserFactory())
        response = client.post(reverse(route, args=[task.pk]), payload)
        assert response.status_code == 200
        assert 'taskChanged' in response['HX-Trigger']
        assert f'taskUpdated-{task.pk}' in response['HX-Trigger']

    def test_label_toggle_emits_task_changed(self, client):
        from apps.accounts.factories import AdminUserFactory
        from apps.tasks.factories import LabelFactory

        task = TaskFactory()
        label = LabelFactory(project=task.project)
        client.force_login(AdminUserFactory())
        response = client.post(reverse('task_toggle_label', args=[task.pk, label.pk]))
        assert response.status_code == 200
        assert 'taskChanged' in response['HX-Trigger']


@pytest.mark.django_db
class TestTaskMoveAfterId:
    def _setup(self, client):
        from apps.accounts.factories import AdminUserFactory

        project = ProjectFactory()
        status = project.statuses.get(name='Backlog')
        tasks = {
            title: TaskFactory(project=project, status=status, title=title, order=index)
            for index, title in enumerate(['A', 'B', 'C'])
        }
        client.force_login(AdminUserFactory())
        return project, status, tasks

    @staticmethod
    def _column(status):
        return list(
            Task.objects.filter(status=status).order_by('order').values_list('title', flat=True)
        )

    def test_after_id_drops_below_the_anchor_card(self, client):
        project, status, tasks = self._setup(client)
        response = client.post(reverse('task_move'), {
            'task_id': tasks['A'].pk, 'status_id': status.pk, 'after_id': tasks['B'].pk,
        })
        assert response.status_code == 204
        assert self._column(status) == ['B', 'A', 'C']

    def test_empty_after_id_means_first(self, client):
        project, status, tasks = self._setup(client)
        client.post(reverse('task_move'), {
            'task_id': tasks['C'].pk, 'status_id': status.pk, 'after_id': '',
        })
        assert self._column(status) == ['C', 'A', 'B']

    def test_missing_after_id_keeps_the_old_behaviour(self, client):
        project, status, tasks = self._setup(client)
        client.post(reverse('task_move'), {'task_id': tasks['A'].pk, 'status_id': status.pk})
        assert self._column(status) == ['B', 'C', 'A']
        client.post(reverse('task_move'), {
            'task_id': tasks['A'].pk, 'status_id': status.pk, 'position': 0,
        })
        assert self._column(status) == ['A', 'B', 'C']

    def test_invalid_after_id_is_a_400(self, client):
        project, status, tasks = self._setup(client)
        response = client.post(reverse('task_move'), {
            'task_id': tasks['A'].pk, 'status_id': status.pk, 'after_id': 'abc',
        })
        assert response.status_code == 400
        assert self._column(status) == ['A', 'B', 'C']

    def test_unknown_after_id_appends(self, client):
        project, status, tasks = self._setup(client)
        response = client.post(reverse('task_move'), {
            'task_id': tasks['A'].pk, 'status_id': status.pk, 'after_id': 424242,
        })
        assert response.status_code == 204
        assert self._column(status) == ['B', 'C', 'A']
