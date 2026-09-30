import pytest

from apps.projects.factories import ProjectFactory
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory


@pytest.mark.django_db
class TestTaskModel:
    def test_create_task(self):
        task = TaskFactory()
        assert task.title is not None
        assert task.project is not None
        assert task.status is not None

    def test_task_str(self):
        task = TaskFactory(title='Test Task')
        assert str(task) == 'Test Task'

    def test_subtask_progress_none_when_empty(self):
        task = TaskFactory()
        assert task.subtask_progress is None

    def test_subtask_progress_calculation(self):
        task = TaskFactory()
        SubtaskFactory(task=task, completed=True)
        SubtaskFactory(task=task, completed=False)
        SubtaskFactory(task=task, completed=True)
        assert task.subtask_progress == '2/3'


@pytest.mark.django_db
class TestLabelModel:
    def test_label_unique_per_project(self):
        project = ProjectFactory()
        LabelFactory(project=project, name='Bug')
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            LabelFactory(project=project, name='Bug')

    def test_same_label_name_different_projects(self):
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        LabelFactory(project=project1, name='Bug')
        label2 = LabelFactory(project=project2, name='Bug')
        assert label2.pk is not None


@pytest.mark.django_db
class TestSubtaskModel:
    def test_subtask_ordering(self):
        task = TaskFactory()
        SubtaskFactory(task=task, order=2, title='Third')
        SubtaskFactory(task=task, order=0, title='First')
        SubtaskFactory(task=task, order=1, title='Second')
        subtasks = list(task.subtasks.all())
        assert subtasks[0].title == 'First'


@pytest.mark.django_db
class TestTaskQuerySetStatusCategories:
    def _task(self, category, **kwargs):
        from apps.projects.factories import StatusFactory
        project = ProjectFactory()
        return TaskFactory(
            project=project, status=StatusFactory(project=project, category=category), **kwargs
        )

    def test_done_is_completed_only(self):
        from apps.tasks.models import Task
        completed = self._task('completed')
        self._task('canceled')
        self._task('started')
        assert list(Task.objects.done()) == [completed]

    def test_active_excludes_completed_and_canceled(self):
        from apps.tasks.models import Task
        self._task('completed')
        self._task('canceled')
        started = self._task('started')
        backlog = self._task('backlog')
        assert set(Task.objects.active()) == {started, backlog}

    def test_overdue_ignores_canceled_and_completed(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.tasks.models import Task
        yesterday = timezone.now().date() - timedelta(days=1)
        late = self._task('started', due_date=yesterday)
        self._task('canceled', due_date=yesterday)
        self._task('completed', due_date=yesterday)
        assert list(Task.objects.overdue()) == [late]

    def test_is_overdue_false_for_canceled(self):
        from datetime import timedelta

        from django.utils import timezone
        yesterday = timezone.now().date() - timedelta(days=1)
        assert self._task('started', due_date=yesterday).is_overdue is True
        assert self._task('canceled', due_date=yesterday).is_overdue is False
        assert self._task('completed', due_date=yesterday).is_overdue is False
