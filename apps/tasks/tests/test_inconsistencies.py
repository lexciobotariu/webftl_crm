"""Inconsistencies from the 2026-10-07 review of the tasks implementation (release 0.20.0)."""
import pytest
from django.http import QueryDict
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectFactory
from apps.tasks import services
from apps.tasks.factories import TaskFactory
from apps.tasks.listview import build_groups, group_slots, project_assignees
from apps.tasks.models import Task
from apps.tasks.viewspec import SORTS, TaskViewOptions, TaskViewSpec, sort_choices


def _user(name, **flags):
    fields = {
        'access_dashboard': True,
        'access_projects': True,
        'access_tasks': True,
        'projects_view_all': True,
        'tasks_view_all': False,
        'tasks_create': False,
        'tasks_edit_own': False,
        'tasks_edit_all': False,
    }
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


def _options(project):
    return TaskViewOptions(
        status_ids=frozenset(project.statuses.values_list('pk', flat=True)),
        assignee_ids=frozenset(),
        label_ids=frozenset(),
    )


def _spec(project, query=''):
    return TaskViewSpec.from_params(QueryDict(query), _options(project))


def _groups(project, spec):
    tasks = Task.objects.filter(project=project)
    page = tasks.matching(spec).ordered_for(spec).select_related('project', 'status', 'assignee')
    slots = group_slots(spec, list(project.statuses.all()), list(project_assignees(project)))
    return build_groups(page, spec, tasks.group_counts(spec), slots)


class TestManualSortSpec:
    OPTIONS = TaskViewOptions(status_ids=frozenset({1}))

    def parse(self, query, options=OPTIONS):
        return TaskViewSpec.from_params(QueryDict(query), options)

    def test_manual_is_the_default_by_status_and_priority_otherwise(self):
        assert self.parse('').sort == 'manual'
        assert self.parse('group=assignee').sort == 'priority'
        assert self.parse('group=assignee').to_params() == {'layout': 'list', 'group': 'assignee'}

    def test_a_sort_away_from_the_grouping_default_is_kept_in_the_url(self):
        assert self.parse('sort=priority').to_params()['sort'] == 'priority'
        assert self.parse('group=assignee&sort=manual').to_params()['sort'] == 'manual'
        assert 'sort' not in self.parse('sort=manual').to_params()

    def test_a_page_without_manual_ignores_it(self):
        options = TaskViewOptions(
            groups=('project', 'none'), default_group='project',
            sorts=tuple(value for value in SORTS if value != 'manual'),
        )
        assert self.parse('sort=manual', options).sort == 'priority'
        assert 'manual' not in [value for value, *_ in sort_choices(options)]
        assert sort_choices()[0][0] == 'manual'


@pytest.mark.django_db
class TestManualSortOrder:
    def test_the_list_follows_the_board_order(self):
        project = ProjectFactory()
        todo = project.statuses.get(name='To Do')
        first = TaskFactory(project=project, status=todo, order=0, priority='low', title='First')
        second = TaskFactory(project=project, status=todo, order=1, priority='urgent', title='Second')

        spec = _spec(project)
        assert list(Task.objects.matching(spec).ordered_for(spec)) == [first, second]

        reversed_spec = _spec(project, 'dir=desc')
        assert list(Task.objects.matching(reversed_spec).ordered_for(reversed_spec)) == [second, first]

    def test_the_page_offers_manual_and_my_tasks_does_not(self, client):
        project = ProjectFactory()
        client.force_login(_user('ManualViewers', tasks_view_all=True))

        project_html = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list').content.decode()
        assert 'value="manual"' in project_html

        my_html = client.get(reverse('my_tasks') + '?layout=list').content.decode()
        assert 'value="manual"' not in my_html


@pytest.mark.django_db
class TestSearchById:
    def test_key_number_and_bare_number_match(self):
        project = ProjectFactory(key='CUST')
        target = TaskFactory(project=project, title='Fix the invoice')
        other = TaskFactory(project=project, title='Something else')

        for text in (f'CUST-{target.number}', f'cust-{target.number}', str(target.number), f'#{target.number}'):
            found = list(Task.objects.matching(_spec(project, f'q={text}')))
            assert found == [target], text
        assert other not in Task.objects.matching(_spec(project, f'q=OTHER-{target.number}'))

    def test_the_title_still_matches_and_a_long_number_does_not_error(self):
        project = ProjectFactory()
        task = TaskFactory(project=project, title='Release 2027 plan')
        assert list(Task.objects.matching(_spec(project, 'q=2027'))) == [task]
        assert list(Task.objects.matching(_spec(project, 'q=' + '9' * 30))) == []


@pytest.mark.django_db
class TestEmptyGroups:
    def test_every_status_is_listed_by_default(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='In Progress'))

        groups = _groups(project, _spec(project))

        assert [(g['label'], g['count']) for g in groups] == [
            ('Backlog', 0), ('To Do', 0), ('In Progress', 1), ('Review', 0), ('Done', 0),
        ]
        assert groups[0]['create_query'] == f'status={project.statuses.get(name="Backlog").pk}'

    def test_switching_it_off_and_hidden_statuses(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='In Progress'))
        done = project.statuses.get(name='Done')

        assert [g['label'] for g in _groups(project, _spec(project, 'empty=0'))] == ['In Progress']
        hidden = _groups(project, _spec(project, f'hide_status={done.pk}'))
        assert 'Done' not in [g['label'] for g in hidden]
        assert _spec(project, 'empty=0').to_params()['empty'] == '0'

    def test_other_groupings_are_off_by_default_and_can_be_switched_on(self):
        project = ProjectFactory()
        TaskFactory(project=project, priority='high')

        assert [g['label'] for g in _groups(project, _spec(project, 'group=priority'))] == ['High']
        labels = [g['label'] for g in _groups(project, _spec(project, 'group=priority&empty=1'))]
        assert labels == ['Urgent', 'High', 'Medium', 'Low', 'No priority']

    def test_a_partial_page_leaves_out_empty_groups_after_the_last_loaded_one(self):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='To Do'))
        TaskFactory(project=project, status=project.statuses.get(name='Review'))
        spec = _spec(project)
        tasks = Task.objects.filter(project=project)
        page = list(tasks.matching(spec).ordered_for(spec).select_related('project', 'status'))[:1]

        groups = build_groups(page, spec, tasks.group_counts(spec), group_slots(spec, list(project.statuses.all())))

        assert [g['label'] for g in groups] == ['Backlog', 'To Do']

    def test_the_list_page_shows_the_switch_and_empty_headers(self, client):
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.get(name='To Do'))
        client.force_login(_user('EmptyViewers', tasks_view_all=True))

        html = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list').content.decode()

        assert 'Show empty groups' in html
        assert 'Review' in html


@pytest.mark.django_db
class TestComments:
    def test_a_viewer_may_comment_and_change_their_own_comment(self, client):
        task = TaskFactory()
        viewer = _user('Commenters', tasks_view_all=True)
        client.force_login(viewer)

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert reverse('comment_create', args=[task.pk]) in html

        response = client.post(reverse('comment_create', args=[task.pk]), {'content': 'Looks good'})
        assert response.status_code == 200
        comment = task.activities.get(activity_type='comment')
        assert comment.user == viewer

        response = client.post(
            reverse('comment_edit', args=[task.pk, comment.pk]), {'content': 'Looks great'},
        )
        assert response.status_code == 200

    def test_someone_who_cannot_see_the_task_may_not_comment(self, client):
        task = TaskFactory()
        client.force_login(_user('Outsiders'))

        response = client.post(reverse('comment_create', args=[task.pk]), {'content': 'Hi'})

        assert response.status_code == 403
        assert not task.activities.filter(activity_type='comment').exists()

    def test_an_editor_may_not_change_someone_elses_comment(self, client):
        task = TaskFactory()
        author = _user('Authors', tasks_view_all=True)
        comment = services.add_comment(task, 'Mine', author)
        client.force_login(_user('OtherEditors', tasks_view_all=True, tasks_edit_all=True))

        response = client.post(reverse('comment_delete', args=[task.pk, comment.pk]))

        assert response.status_code == 403


@pytest.mark.django_db
class TestBoard:
    def test_a_status_change_from_the_drawer_lands_at_the_top(self, client):
        project = ProjectFactory()
        todo, doing = project.statuses.get(name='To Do'), project.statuses.get(name='In Progress')
        existing = TaskFactory(project=project, status=doing, order=0)
        moved = TaskFactory(project=project, status=todo)
        client.force_login(_user('StatusEditors', tasks_view_all=True, tasks_edit_all=True))

        response = client.post(reverse('task_update_status', args=[moved.pk]), {'status_id': doing.pk})

        assert response.status_code == 200
        moved.refresh_from_db()
        existing.refresh_from_db()
        assert (moved.status, moved.order, existing.order) == (doing, 0, 1)

    def test_column_headers_show_the_status_icon(self, client):
        project = ProjectFactory()
        client.force_login(_user('BoardIconViewers', tasks_view_all=True))

        html = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board').content.decode()
        header = html.split(f'id="column-{project.statuses.get(name="Done").pk}"', 1)[1].split('</h3>', 1)[0]

        assert 'text-accent' in header
