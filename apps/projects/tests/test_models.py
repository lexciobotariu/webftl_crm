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


@pytest.mark.django_db
class TestStatusCategory:
    def test_default_statuses_get_a_category_each(self):
        project = ProjectFactory()
        categories = dict(project.statuses.values_list('name', 'category'))
        assert categories == {
            'Backlog': 'backlog',
            'To Do': 'unstarted',
            'In Progress': 'started',
            'Review': 'started',
            'Done': 'completed',
        }

    def test_new_status_defaults_to_unstarted(self):
        assert StatusFactory().category == 'unstarted'

    @pytest.mark.parametrize('category,completed,closed', [
        ('backlog', False, False),
        ('unstarted', False, False),
        ('started', False, False),
        ('completed', True, True),
        ('canceled', False, True),
    ])
    def test_completed_and_closed_flags(self, category, completed, closed):
        status = StatusFactory(category=category)
        assert status.is_completed is completed
        assert status.is_closed is closed

    def test_is_done_is_gone(self):
        assert not hasattr(StatusFactory(), 'is_done')
