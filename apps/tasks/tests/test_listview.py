import pytest
from django.http import QueryDict

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Status
from apps.tasks.factories import TaskFactory
from apps.tasks.listview import build_groups, filter_options, group_choices
from apps.tasks.models import Task
from apps.tasks.viewspec import TaskViewOptions, TaskViewSpec

MY_OPTIONS = TaskViewOptions(
    layouts=('list',),
    groups=('project', 'category', 'priority', 'none'),
    categories=frozenset(value for value, _label in Status.CATEGORY_CHOICES),
    has_assignee_filter=False,
    default_group='project',
    default_categories=frozenset({'backlog', 'unstarted', 'started'}),
)


def my_spec(query=''):
    return TaskViewSpec.from_params(QueryDict(query), MY_OPTIONS)


def grouped(spec):
    tasks = Task.objects.matching(spec).ordered_for(spec).select_related('project', 'status')
    return build_groups(tasks, spec, Task.objects.group_counts(spec))


@pytest.mark.django_db
class TestBuildGroups:
    def test_project_groups_are_labelled_with_the_project(self):
        one, two = ProjectFactory(name='Alpha'), ProjectFactory(name='Beta')
        TaskFactory.create_batch(2, project=one)
        TaskFactory(project=two)
        groups = grouped(my_spec())
        assert [(g['label'], g['count'], g['kind']) for g in groups] == [
            ('Alpha', 2, 'project'), ('Beta', 1, 'project'),
        ]
        assert groups[0]['project'] == one
        assert groups[0]['key'] == f'project-{one.pk}'

    def test_category_groups_are_labelled_with_the_status_type(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='Review'))
        TaskFactory(project=project, status=project.statuses.get(name='In Progress'))
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'))
        groups = grouped(my_spec('group=category'))
        assert [(g['label'], g['category'], g['count']) for g in groups] == [
            ('Backlog', 'backlog', 1), ('Started', 'started', 2),
        ]
        assert groups[1]['key'] == 'category-started'


class TestGroupChoices:
    def test_follows_the_page_options(self):
        assert group_choices(MY_OPTIONS) == [
            ('project', 'Project'), ('category', 'Status type'),
            ('priority', 'Priority'), ('none', 'No grouping'),
        ]
        assert [value for value, _ in group_choices(TaskViewOptions())] == [
            'status', 'assignee', 'priority', 'none',
        ]


@pytest.mark.django_db
class TestFilterOptions:
    def test_a_page_with_only_type_and_priority_filters(self):
        options = filter_options([], my_spec('category=completed'), [], [], categories=MY_OPTIONS.categories)
        assert set(options) == {'priority_options', 'label_options', 'category_options'}
        checked = {o['value']: o['checked'] for o in options['category_options']}
        assert checked == {
            'backlog': False, 'unstarted': False, 'started': False,
            'completed': True, 'canceled': False,
        }
        assert [o['label'] for o in options['category_options']][:2] == ['Backlog', 'Unstarted']

    def test_the_default_selection_is_checked(self):
        options = filter_options([], my_spec(), [], [], categories=MY_OPTIONS.categories)
        assert [o['value'] for o in options['category_options'] if o['checked']] == [
            'backlog', 'unstarted', 'started',
        ]

    def test_the_project_page_keeps_status_and_assignee_groups(self):
        project = ProjectFactory()
        user = UserFactory()
        spec = TaskViewSpec.from_params(QueryDict(), TaskViewOptions())
        options = filter_options(list(project.statuses.all()), spec, [user], [])
        assert len(options['status_options']) == 5
        assert options['assignee_options'][0]['value'] == 'none'
        assert 'category_options' not in options
