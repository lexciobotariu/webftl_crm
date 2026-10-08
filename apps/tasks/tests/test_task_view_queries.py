from datetime import date

import pytest
from django.db import connection
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, StatusFactory
from apps.projects.models import Status
from apps.tasks.factories import LabelFactory, TaskFactory
from apps.tasks.models import Task
from apps.tasks.viewspec import TaskViewOptions, TaskViewSpec


def spec_for(project, query=''):
    options = TaskViewOptions(
        status_ids=frozenset(project.statuses.values_list('pk', flat=True)),
        assignee_ids=frozenset(
            Task.objects.filter(project=project, assignee__isnull=False).values_list(
                'assignee_id', flat=True
            )
        ),
        label_ids=frozenset(project.labels.values_list('pk', flat=True)),
    )
    return TaskViewSpec.from_params(QueryDict(query), options)


def titles(qs):
    return [task.title for task in qs]


@pytest.mark.django_db
class TestMatching:
    def test_default_spec_matches_everything(self):
        project = ProjectFactory()
        TaskFactory.create_batch(3, project=project)
        assert Task.objects.matching(spec_for(project)).count() == 3

    def test_hidden_status_is_excluded(self):
        project = ProjectFactory()
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, title='keep')
        TaskFactory(project=project, status=done, title='hide')
        spec = spec_for(project, f'hide_status={done.pk}')
        assert titles(Task.objects.matching(spec)) == ['keep']

    def test_priorities_filter_includes_none(self):
        project = ProjectFactory()
        TaskFactory(project=project, priority='high', title='high')
        TaskFactory(project=project, priority='low', title='low')
        TaskFactory(project=project, priority='', title='none')
        spec = spec_for(project, 'priority=high&priority=none')
        assert sorted(titles(Task.objects.matching(spec))) == ['high', 'none']

    def test_assignee_filter_with_unassigned(self):
        project = ProjectFactory()
        ann, bob = UserFactory(), UserFactory()
        TaskFactory(project=project, assignee=ann, title='ann')
        TaskFactory(project=project, assignee=bob, title='bob')
        TaskFactory(project=project, assignee=None, title='nobody')
        assert titles(Task.objects.matching(spec_for(project, f'assignee={ann.pk}'))) == ['ann']
        both = spec_for(project, f'assignee={ann.pk}&assignee=none')
        assert sorted(titles(Task.objects.matching(both))) == ['ann', 'nobody']

    def test_label_filter_is_any_of_and_does_not_duplicate_rows(self):
        project = ProjectFactory()
        bug, ui = LabelFactory(project=project, name='bug'), LabelFactory(project=project, name='ui')
        both = TaskFactory(project=project, title='both')
        both.labels.set([bug, ui])
        only_ui = TaskFactory(project=project, title='only ui')
        only_ui.labels.set([ui])
        TaskFactory(project=project, title='unlabelled')
        spec = spec_for(project, f'label={bug.pk}&label={ui.pk}')
        result = Task.objects.matching(spec)
        assert sorted(titles(result)) == ['both', 'only ui']
        assert result.count() == 2

    def test_search_matches_titles_case_insensitively(self):
        project = ProjectFactory()
        TaskFactory(project=project, title='Fix the Login page')
        TaskFactory(project=project, title='Write docs')
        assert titles(Task.objects.matching(spec_for(project, 'q=login'))) == ['Fix the Login page']

    def test_filters_combine(self):
        project = ProjectFactory()
        ann = UserFactory()
        TaskFactory(project=project, assignee=ann, priority='high', title='match')
        TaskFactory(project=project, assignee=ann, priority='low', title='wrong priority')
        TaskFactory(project=project, priority='high', title='wrong assignee')
        spec = spec_for(project, f'assignee={ann.pk}&priority=high')
        assert titles(Task.objects.matching(spec)) == ['match']


@pytest.mark.django_db
class TestOrderedFor:
    def test_priority_sort_puts_urgent_first_and_none_last(self):
        project = ProjectFactory()
        for priority in ('low', '', 'urgent', 'medium', 'high'):
            TaskFactory(project=project, priority=priority, title=priority or 'none')
        spec = spec_for(project, 'group=none')
        assert titles(Task.objects.ordered_for(spec)) == ['urgent', 'high', 'medium', 'low', 'none']
        reverse = spec_for(project, 'group=none&dir=desc')
        assert titles(Task.objects.ordered_for(reverse)) == ['none', 'low', 'medium', 'high', 'urgent']

    def test_due_sort_puts_undated_tasks_last_either_way(self):
        project = ProjectFactory()
        TaskFactory(project=project, title='late', due_date=date(2030, 2, 1))
        TaskFactory(project=project, title='early', due_date=date(2030, 1, 1))
        TaskFactory(project=project, title='undated', due_date=None)
        asc = spec_for(project, 'group=none&sort=due')
        assert titles(Task.objects.ordered_for(asc)) == ['early', 'late', 'undated']
        desc = spec_for(project, 'group=none&sort=due&dir=desc')
        assert titles(Task.objects.ordered_for(desc)) == ['late', 'early', 'undated']

    def test_title_sort_ignores_case(self):
        project = ProjectFactory()
        for title in ('banana', 'Apple', 'cherry'):
            TaskFactory(project=project, title=title)
        spec = spec_for(project, 'group=none&sort=title')
        assert titles(Task.objects.ordered_for(spec)) == ['Apple', 'banana', 'cherry']

    def test_created_sort_defaults_to_newest_first(self):
        project = ProjectFactory()
        first = TaskFactory(project=project, title='first')
        second = TaskFactory(project=project, title='second')
        spec = spec_for(project, 'group=none&sort=created')
        assert titles(Task.objects.ordered_for(spec)) == ['second', 'first']
        assert first.pk < second.pk

    def test_status_groups_follow_the_column_order_then_the_sort_key(self):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=done, priority='urgent', title='done urgent')
        TaskFactory(project=project, status=backlog, priority='low', title='backlog low')
        TaskFactory(project=project, status=backlog, priority='high', title='backlog high')
        result = titles(Task.objects.ordered_for(spec_for(project, 'sort=priority')))
        assert result == ['backlog high', 'backlog low', 'done urgent']

    def test_assignee_groups_are_alphabetical_with_unassigned_last(self):
        project = ProjectFactory()
        zed = UserFactory(name='Zed')
        amy = UserFactory(name='Amy')
        TaskFactory(project=project, assignee=None, title='nobody')
        TaskFactory(project=project, assignee=zed, title='zed')
        TaskFactory(project=project, assignee=amy, title='amy')
        result = titles(Task.objects.ordered_for(spec_for(project, 'group=assignee')))
        assert result == ['amy', 'zed', 'nobody']

    def test_priority_groups_run_from_urgent_to_none(self):
        project = ProjectFactory()
        for priority in ('', 'low', 'urgent'):
            TaskFactory(project=project, priority=priority, title=priority or 'none')
        result = titles(Task.objects.ordered_for(spec_for(project, 'group=priority&sort=title')))
        assert result == ['urgent', 'low', 'none']

    def test_ties_break_the_same_way_every_time(self):
        project = ProjectFactory()
        TaskFactory.create_batch(5, project=project, priority='high', title='same')
        spec = spec_for(project, 'group=none')
        first = [t.pk for t in Task.objects.ordered_for(spec)]
        assert first == [t.pk for t in Task.objects.ordered_for(spec)]


@pytest.mark.django_db
class TestGroupCounts:
    def test_counts_every_matching_task_by_status(self):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        done = project.statuses.get(name='Done')
        TaskFactory.create_batch(3, project=project, status=backlog)
        TaskFactory(project=project, status=done)
        counts = Task.objects.group_counts(spec_for(project))
        assert counts == {backlog.pk: 3, done.pk: 1}

    def test_counts_respect_the_filters(self):
        project = ProjectFactory()
        backlog = project.statuses.get(name='Backlog')
        TaskFactory(project=project, status=backlog, priority='high')
        TaskFactory(project=project, status=backlog, priority='low')
        counts = Task.objects.group_counts(spec_for(project, 'priority=high'))
        assert counts == {backlog.pk: 1}

    def test_counts_by_assignee_use_none_for_unassigned(self):
        project = ProjectFactory()
        ann = UserFactory()
        TaskFactory(project=project, assignee=ann)
        TaskFactory.create_batch(2, project=project, assignee=None)
        counts = Task.objects.group_counts(spec_for(project, 'group=assignee'))
        assert counts == {ann.pk: 1, None: 2}

    def test_counts_by_priority(self):
        project = ProjectFactory()
        TaskFactory(project=project, priority='high')
        TaskFactory.create_batch(2, project=project, priority='')
        counts = Task.objects.group_counts(spec_for(project, 'group=priority'))
        assert counts == {'high': 1, '': 2}

    def test_no_grouping_has_no_counts(self):
        project = ProjectFactory()
        TaskFactory(project=project)
        assert Task.objects.group_counts(spec_for(project, 'group=none')) == {}

    def test_counting_is_one_query(self):
        project = ProjectFactory()
        TaskFactory.create_batch(4, project=project)
        spec = spec_for(project)
        with CaptureQueriesContext(connection) as queries:
            Task.objects.group_counts(spec)
        assert len(queries) == 1



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


@pytest.mark.django_db
class TestAcrossProjects:
    def test_category_filter_keeps_only_those_status_types(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'), title='backlog')
        TaskFactory(project=project, status=project.statuses.get(name='Review'), title='review')
        TaskFactory(project=project, status=project.statuses.get(name='Done'), title='done')
        assert sorted(titles(Task.objects.matching(my_spec()))) == ['backlog', 'review']
        done = my_spec('category=completed')
        assert titles(Task.objects.matching(done)) == ['done']

    def test_category_filter_spans_projects_with_different_column_names(self):
        one, two = ProjectFactory(), ProjectFactory()
        StatusFactory(project=two, name='Doing', category=Status.STARTED)
        TaskFactory(project=one, status=one.statuses.get(name='In Progress'), title='one')
        TaskFactory(project=two, status=two.statuses.get(name='Doing'), title='two')
        assert sorted(titles(Task.objects.matching(my_spec('category=started')))) == ['one', 'two']

    def test_a_page_without_the_type_filter_is_not_narrowed(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='Done'))
        assert Task.objects.matching(spec_for(project)).count() == 1

    def test_project_groups_are_alphabetical_then_split_by_id(self):
        zulu = ProjectFactory(name='Zulu')
        alpha = ProjectFactory(name='alpha')
        twin = ProjectFactory(name='alpha')
        TaskFactory(project=zulu, title='a in zulu')
        TaskFactory(project=twin, title='b in twin')
        TaskFactory(project=alpha, title='c in alpha')
        result = titles(Task.objects.ordered_for(my_spec('sort=title')))
        assert result == ['c in alpha', 'b in twin', 'a in zulu']
        assert alpha.pk < twin.pk

    def test_category_groups_follow_the_order_of_the_status_types(self):
        project = ProjectFactory()
        for name in ('Done', 'Review', 'Backlog', 'To Do'):
            TaskFactory(project=project, status=project.statuses.get(name=name), title=name)
        spec = my_spec('group=category&category=backlog&category=unstarted'
                       '&category=started&category=completed&sort=title')
        assert titles(Task.objects.ordered_for(spec)) == ['Backlog', 'To Do', 'Review', 'Done']

    def test_counts_by_project(self):
        one, two = ProjectFactory(), ProjectFactory()
        TaskFactory.create_batch(2, project=one)
        TaskFactory(project=two)
        assert Task.objects.group_counts(my_spec()) == {one.pk: 2, two.pk: 1}

    def test_counts_by_status_type_respect_the_filters(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='In Progress'))
        TaskFactory(project=project, status=project.statuses.get(name='Review'))
        TaskFactory(project=project, status=project.statuses.get(name='Done'))
        assert Task.objects.group_counts(my_spec('group=category')) == {'started': 2}
        everything = my_spec('group=category&category=started&category=completed')
        assert Task.objects.group_counts(everything) == {'started': 2, 'completed': 1}
