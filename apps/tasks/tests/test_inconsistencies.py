"""Inconsistencies from the 2026-10-07 review of the tasks implementation (release 0.20.0)."""
import pytest
from django.http import QueryDict
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectFactory
from apps.tasks import services
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory
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


# --- Linear suggestions (0.20.0, second round) ---------------------------------


@pytest.mark.django_db
class TestQuickMenus:
    def test_labels_and_due_menus_for_an_editor(self, client):
        project = ProjectFactory()
        task = TaskFactory(project=project, due_date=None)
        bug = LabelFactory(project=project, name='Bug')
        task.labels.add(bug)
        LabelFactory(project=project, name='Docs')
        client.force_login(_user('MenuEditors', tasks_view_all=True, tasks_edit_all=True))

        labels = client.get(reverse('task_quick_menu', args=[task.pk, 'labels'])).content.decode()
        assert 'menuitemcheckbox' in labels
        assert labels.index('Bug') < labels.index('Docs')
        assert labels.count('aria-checked="true"') == 1

        due = client.get(reverse('task_quick_menu', args=[task.pk, 'due'])).content.decode()
        assert 'Tomorrow' in due and 'data-quick-date' in due
        assert 'No due date' not in due

    def test_a_viewer_gets_no_menu(self, client):
        task = TaskFactory()
        client.force_login(_user('MenuViewers', tasks_view_all=True))
        assert client.get(reverse('task_quick_menu', args=[task.pk, 'labels'])).status_code == 403

    def test_next_week_is_the_coming_monday(self):
        from datetime import date

        from apps.tasks.views import due_date_presets

        presets = dict(due_date_presets(date(2026, 10, 8)))  # a Thursday
        assert presets['Tomorrow'] == date(2026, 10, 9)
        assert presets['Next week'] == date(2026, 10, 12)

    def test_the_page_carries_what_the_new_keys_need(self, client):
        project = ProjectFactory()
        task = TaskFactory(project=project)
        user = _user('KeyEditors', tasks_view_all=True, tasks_edit_all=True)
        client.force_login(user)

        html = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list').content.decode()

        assert f'data-me="{user.pk}"' in html
        assert f'data-identifier="{task.identifier}"' in html
        assert reverse('task_full_page', args=[project.pk, task.pk]) in html
        assert 'Assign to me' in html


@pytest.mark.django_db
class TestRowRefresh:
    def test_the_row_comes_alone_with_its_place(self, client):
        project = ProjectFactory()
        task = TaskFactory(project=project, title='Only me')
        TaskFactory(project=project, title='Someone else')
        client.force_login(_user('RowViewers', tasks_view_all=True))
        base = reverse('project_tasks', args=[project.pk])

        response = client.get(f'{base}?layout=list&row={task.pk}')

        html = response.content.decode()
        assert response.status_code == 200
        assert 'Only me' in html and 'Someone else' not in html
        assert f'data-keys="{task.status_id}|{task.status_id}:{task.order}"' in html

    def test_a_row_that_left_the_filter_answers_204(self, client):
        project = ProjectFactory()
        task = TaskFactory(project=project, priority='low')
        client.force_login(_user('RowFilterViewers', tasks_view_all=True))
        base = reverse('project_tasks', args=[project.pk])

        assert client.get(f'{base}?layout=list&priority=urgent&row={task.pk}').status_code == 204

    def test_the_board_card_and_my_tasks_row(self, client):
        project = ProjectFactory()
        user = _user('RowAssignees', tasks_view_all=True, tasks_edit_all=True)
        task = TaskFactory(project=project, assignee=user, title='Card me')
        client.force_login(user)

        card = client.get(reverse('project_tasks', args=[project.pk]) + f'?layout=board&row={task.pk}')
        assert 'x-sort:item' in card.content.decode()
        assert f'data-keys="{task.status_id}"' in card.content.decode()

        row = client.get(reverse('my_tasks') + f'?layout=list&row={task.pk}')
        assert 'Card me' in row.content.decode()


class TestColumns:
    OPTIONS = TaskViewOptions(status_ids=frozenset({1}))

    def parse(self, query):
        return TaskViewSpec.from_params(QueryDict(query), self.OPTIONS)

    def test_defaults_and_the_url(self):
        assert self.parse('').columns == {'id', 'labels', 'due'}
        spec = self.parse('cols=1&col=id&col=estimate')
        assert spec.columns == {'id', 'estimate'}
        assert spec.to_params()['col'] == ['id', 'estimate']
        assert self.parse('cols=1').to_params()['col'] == ['none']
        assert self.parse('col=none').columns == frozenset()
        assert 'col' not in self.parse('cols=1&col=id&col=labels&col=due').to_params()

    @pytest.mark.django_db
    def test_a_hidden_column_leaves_the_row(self, client):
        project = ProjectFactory(key='COLS')
        TaskFactory(project=project, estimate_minutes=90)
        client.force_login(_user('ColumnViewers', tasks_view_all=True))
        base = reverse('project_tasks', args=[project.pk])

        default = client.get(f'{base}?layout=list').content.decode()
        assert 'COLS-1</span>' in default
        assert '1h 30m' not in default

        chosen = client.get(f'{base}?layout=list&col=estimate').content.decode()
        assert 'COLS-1</span>' not in chosen
        assert '1h 30m' in chosen


@pytest.mark.django_db
class TestSubscriptions:
    def test_unsubscribing_stops_comment_notifications_but_not_mentions(self, client):
        from apps.notifications.models import Notification

        task = TaskFactory()
        assignee = _user('Assignees', tasks_view_all=True)
        task.assignee = assignee
        task.save()
        client.force_login(assignee)

        response = client.post(reverse('task_subscription', args=[task.pk]), {'subscribed': '0'})
        assert response.status_code == 200
        assert 'Subscribe' in response.content.decode()

        author = _user('CommentAuthors', tasks_view_all=True)
        services.add_comment(task, 'Ping', author)
        assert not Notification.objects.filter(recipient=assignee).exists()

        assignee.name = 'Ana Assignee'
        assignee.save()
        services.add_comment(task, 'Hey @Ana Assignee', author, mentions=[assignee.pk])
        assert Notification.objects.filter(recipient=assignee, kind=Notification.MENTIONED).exists()

    def test_subscribing_to_a_task_you_have_no_part_in(self, client):
        from apps.notifications.models import Notification
        from apps.notifications.services import is_following

        task = TaskFactory()
        watcher = _user('Watchers', tasks_view_all=True)
        client.force_login(watcher)
        assert 'Subscribe' in client.get(reverse('task_detail', args=[task.pk])).content.decode()

        client.post(reverse('task_subscription', args=[task.pk]), {'subscribed': '1'})

        assert is_following(watcher, task)
        services.add_comment(task, 'News', _user('Talkers', tasks_view_all=True))
        assert Notification.objects.filter(recipient=watcher, kind=Notification.COMMENTED).exists()

    def test_someone_who_cannot_see_the_task_cannot_subscribe(self, client):
        task = TaskFactory()
        client.force_login(_user('NoSight'))
        assert client.post(reverse('task_subscription', args=[task.pk]), {'subscribed': '1'}).status_code == 403


@pytest.mark.django_db
class TestSubtaskEditing:
    def test_rename_and_reorder(self, client):
        task = TaskFactory()
        first, second, third = (SubtaskFactory(task=task, title=t, order=i) for i, t in enumerate('abc'))
        client.force_login(_user('SubtaskRenamers', tasks_view_all=True, tasks_edit_all=True))

        response = client.post(reverse('subtask_rename', args=[task.pk, first.pk]), {'title': 'Renamed'})
        assert response.status_code == 200
        first.refresh_from_db()
        assert first.title == 'Renamed'
        assert client.post(reverse('subtask_rename', args=[task.pk, first.pk]), {'title': ''}).status_code == 400

        response = client.post(
            reverse('subtask_reorder', args=[task.pk]), {'ids': [third.pk, first.pk, 'junk']},
        )
        assert response.status_code == 204
        assert list(task.subtasks.values_list('pk', flat=True)) == [third.pk, first.pk, second.pk]

    def test_a_viewer_can_neither_rename_nor_reorder(self, client):
        task = TaskFactory()
        subtask = SubtaskFactory(task=task, title='Keep')
        client.force_login(_user('SubtaskViewers', tasks_view_all=True))

        assert client.post(reverse('subtask_rename', args=[task.pk, subtask.pk]), {'title': 'No'}).status_code == 403
        assert client.post(reverse('subtask_reorder', args=[task.pk]), {'ids': [subtask.pk]}).status_code == 403
        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert reverse('subtask_reorder', args=[task.pk]) not in html
