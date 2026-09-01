import pytest

from apps.projects.factories import ProjectFactory, StatusFactory
from apps.tasks.factories import TaskFactory


@pytest.mark.django_db
class TestProjectModel:
    def test_create_project_creates_default_statuses(self):
        project = ProjectFactory()
        assert project.statuses.count() == 5
        status_names = list(project.statuses.values_list('name', flat=True))
        assert 'Backlog' in status_names
        assert 'Done' in status_names

    def test_project_str(self):
        project = ProjectFactory(name='Test Project')
        assert project.name in str(project)
        assert project.client.name in str(project)

    def test_task_count_property(self):
        project = ProjectFactory()
        assert project.task_count == 0
        status = project.statuses.first()
        TaskFactory(project=project, status=status)
        TaskFactory(project=project, status=status)
        assert project.task_count == 2


@pytest.mark.django_db
class TestStatusModel:
    def test_status_ordering(self):
        project = ProjectFactory()
        project.statuses.all().delete()
        StatusFactory(project=project, name='Third', order=2)
        StatusFactory(project=project, name='First', order=0)
        StatusFactory(project=project, name='Second', order=1)
        statuses = list(project.statuses.all())
        assert statuses[0].name == 'First'
        assert statuses[1].name == 'Second'
        assert statuses[2].name == 'Third'

    def test_task_count_property(self):
        project = ProjectFactory()
        status = project.statuses.first()
        assert status.task_count == 0
        TaskFactory(project=project, status=status)
        assert status.task_count == 1

    def test_visible_on_board_defaults_true(self):
        project = ProjectFactory()
        status = project.statuses.first()
        assert status.visible_on_board is True

    def test_visible_on_board_can_be_set_false(self):
        project = ProjectFactory()
        status = project.statuses.first()
        status.visible_on_board = False
        status.save()
        status.refresh_from_db()
        assert status.visible_on_board is False
