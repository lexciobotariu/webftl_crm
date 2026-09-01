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
