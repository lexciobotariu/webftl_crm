import json
import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.notifications.models import Notification
from apps.notifications.templatetags.notification_tags import short_age
from apps.notifications.views import group_by_day
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks import services as task_services
from apps.tasks.factories import TaskFactory


def _member(project=None, name=None, **flags):
    preset = PermissionPreset.objects.create(
        name=f'n{PermissionPreset.objects.count()}',
        access_projects=True, access_tasks=True, tasks_edit_own=True, tasks_create=True, **flags,
    )
    kwargs = {'permission_preset': preset}
    if name:
        kwargs['name'] = name
    user = UserFactory(**kwargs)
    if project is not None:
        ProjectAccessFactory(project=project, user=user)
    return user


def _kinds(user):
    """Unread notifications of ``user``, by kind."""
    return sorted(Notification.objects.filter(recipient=user, read_at__isnull=True).values_list('kind', flat=True))


def _assign(task, assignee, by):
    task_services.update_task_field(task, 'assignee', assignee, by)


@pytest.mark.django_db
class TestAssigned:
    def test_assigning_someone_else_notifies_them(self):
        project = ProjectFactory()
        boss, worker = _member(project), _member(project)
        task = TaskFactory(project=project)

        _assign(task, worker, boss)

        note = Notification.objects.get(recipient=worker)
        assert (note.kind, note.actor, note.task) == ('assigned', boss, task)
        assert note.read_at is None

    def test_assigning_yourself_notifies_nobody(self):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)

        _assign(task, me, me)

        assert not Notification.objects.exists()

    def test_creating_a_task_for_someone_notifies_them(self, client):
        project = ProjectFactory()
        boss, worker = _member(project), _member(project)
        client.force_login(boss)

        client.post(reverse('task_create', args=[project.pk]), {'title': 'Do it', 'assignee': worker.pk})

        assert _kinds(worker) == ['assigned']
        assert not Notification.objects.filter(recipient=boss).exists()

    def test_a_save_without_an_author_notifies_nobody(self):
        project = ProjectFactory()
        worker = _member(project)

        TaskFactory(project=project, assignee=worker)
        task = TaskFactory(project=project)
        task.assignee = worker
        task.save()

        assert not Notification.objects.exists()

    def test_a_second_assignment_while_unread_keeps_one_row(self):
        project = ProjectFactory()
        boss, other, worker = _member(project), _member(project), _member(project)
        task = TaskFactory(project=project)

        _assign(task, worker, boss)
        _assign(task, None, boss)
        _assign(task, worker, other)

        note = Notification.objects.get(recipient=worker)
        assert note.actor == other


@pytest.mark.django_db
class TestCommented:
    def _setup(self):
        project = ProjectFactory()
        creator, assignee, earlier, outsider, author = (_member(project) for _ in range(5))
        task = TaskFactory(project=project)
        task.activities.filter(activity_type='created').update(user=creator)
        task.assignee = assignee
        task.save()
        task_services.add_comment(task, 'first', earlier)
        # Everyone has seen what happened so far.
        Notification.objects.update(read_at='2026-01-01T00:00:00Z')
        return task, creator, assignee, earlier, outsider, author

    def test_followers_hear_about_a_comment_and_the_author_does_not(self):
        task, creator, assignee, earlier, outsider, author = self._setup()

        task_services.add_comment(task, 'hello', author)

        for follower in (creator, assignee, earlier):
            assert _kinds(follower) == ['commented']
        assert _kinds(outsider) == []
        assert _kinds(author) == []
        note = Notification.objects.get(recipient=creator, read_at__isnull=True)
        assert note.activity.content == 'hello' and note.actor == author

    def test_your_own_comment_on_your_task_notifies_the_others_only(self):
        task, creator, assignee, earlier, _outsider, _author = self._setup()

        task_services.add_comment(task, 'note to self', assignee)

        assert _kinds(assignee) == []
        assert _kinds(creator) == ['commented'] and _kinds(earlier) == ['commented']

    def test_a_mention_beats_commented_and_reaches_outsiders(self):
        task, creator, assignee, earlier, outsider, author = self._setup()
        outsider.name = 'Olga Out'
        outsider.save()
        creator.name = 'Cara Creator'
        creator.save()

        task_services.add_comment(task, 'ping @Olga Out and @Cara Creator', author, mentions=[outsider.pk, creator.pk])

        assert _kinds(outsider) == ['mentioned']
        assert _kinds(creator) == ['mentioned']
        assert _kinds(assignee) == ['commented']

    def test_a_mention_of_someone_who_cannot_see_the_task_is_dropped(self):
        task, *_rest, author = self._setup()
        stranger = _member(ProjectFactory(), name='Sam Stranger')

        task_services.add_comment(task, 'hey @Sam Stranger', author, mentions=[stranger.pk])

        assert _kinds(stranger) == []

    def test_a_mention_whose_name_left_the_text_is_dropped(self):
        task, *_rest, outsider, author = self._setup()

        task_services.add_comment(task, 'no names here', author, mentions=[outsider.pk])

        assert _kinds(outsider) == []

    def test_garbage_mention_ids_are_ignored(self):
        task, *_rest, author = self._setup()

        task_services.add_comment(task, 'x', author, mentions=['abc', None, 999999])

        assert not Notification.objects.filter(kind='mentioned').exists()

    def test_comments_while_unread_keep_one_row_with_the_latest(self):
        task, creator, *_rest, author = self._setup()
        other = _member(task.project)

        task_services.add_comment(task, 'one', author)
        task_services.add_comment(task, 'two', other)

        notes = Notification.objects.filter(recipient=creator, kind='commented', read_at__isnull=True)
        assert notes.count() == 1
        assert notes.get().actor == other and notes.get().activity.content == 'two'

    def test_a_read_notification_gets_a_new_row_next_time(self):
        task, creator, *_rest, author = self._setup()

        before = Notification.objects.filter(recipient=creator).count()
        task_services.add_comment(task, 'one', author)
        Notification.objects.filter(recipient=creator).update(read_at='2026-01-01T00:00:00Z')
        task_services.add_comment(task, 'two', author)

        assert Notification.objects.filter(recipient=creator).count() == before + 2

    def test_deleting_the_comment_removes_its_notification(self):
        task, creator, *_rest, author = self._setup()

        comment = task_services.add_comment(task, 'oops', author)
        task_services.delete_comment(comment, author)

        assert _kinds(creator) == []

    def test_the_comment_view_passes_the_chosen_mentions(self, client):
        task, *_rest, outsider, author = self._setup()
        outsider.name = 'Olga Out'
        outsider.save()
        client.force_login(author)

        client.post(reverse('comment_create', args=[task.pk]), {'content': 'hi @Olga Out', 'mentions': [outsider.pk]})

        assert _kinds(outsider) == ['mentioned']


@pytest.mark.django_db
class TestInbox:
    def _note(self, recipient, task=None, kind='assigned'):
        task = task or TaskFactory()
        return Notification.objects.create(recipient=recipient, actor=UserFactory(), task=task, kind=kind)

    def test_unread_first_then_earlier(self, client):
        project = ProjectFactory()
        me = _member(project)
        old = self._note(me, TaskFactory(project=project, title='Old one'))
        old.read_at = '2026-01-01T00:00:00Z'
        old.save()
        self._note(me, TaskFactory(project=project, title='Fresh one'))
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert html.index('Fresh one') < html.index('Old one')
        assert 'Mark all read' in html

    def test_only_tasks_you_can_still_see_and_the_count_follows(self, client):
        project, gone = ProjectFactory(), ProjectFactory()
        me = _member(project)
        ProjectAccessFactory(project=gone, user=me)
        self._note(me, TaskFactory(project=project, title='Still mine'))
        self._note(me, TaskFactory(project=gone, title='Lost access'))
        me.project_access.filter(project=gone).delete()
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()
        count = client.get(reverse('inbox_count')).content.decode()

        assert 'Still mine' in html and 'Lost access' not in html
        assert count.strip() == '1'

    def test_someone_elses_notifications_are_not_listed_or_readable(self, client):
        project = ProjectFactory()
        me, them = _member(project), _member(project)
        theirs = self._note(them, TaskFactory(project=project, title='Theirs'))
        client.force_login(me)

        assert 'Theirs' not in client.get(reverse('inbox')).content.decode()
        assert client.post(reverse('notification_read', args=[theirs.pk])).status_code == 404
        theirs.refresh_from_db()
        assert theirs.read_at is None

    def test_opening_one_marks_it_read(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = self._note(me, TaskFactory(project=project))
        client.force_login(me)

        response = client.post(reverse('notification_read', args=[note.pk]))

        assert response.status_code == 200
        note.refresh_from_db()
        assert note.read_at is not None
        assert 'notificationsChanged' in response['HX-Trigger']

    def test_mark_all_read(self, client):
        project = ProjectFactory()
        me, them = _member(project), _member(project)
        for _ in range(3):
            self._note(me, TaskFactory(project=project))
        theirs = self._note(them, TaskFactory(project=project))
        client.force_login(me)

        response = client.post(reverse('notification_read_all'))

        assert response.status_code == 200
        assert not Notification.objects.filter(recipient=me, read_at__isnull=True).exists()
        theirs.refresh_from_db()
        assert theirs.read_at is None

    def test_it_needs_the_tasks_module(self, client):
        preset = PermissionPreset.objects.create(name='no tasks', access_dashboard=True, access_tasks=False)
        client.force_login(UserFactory(permission_preset=preset))

        assert client.get(reverse('inbox')).status_code == 403
        assert client.get(reverse('inbox_count')).status_code == 403

    def test_an_item_opens_in_the_pane_and_is_a_real_link(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        note = self._note(me, task)
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        url = reverse('notification_open', args=[note.pk])
        assert f'data-open-url="{url}?show=all"' in html
        assert 'id="inbox-pane"' in html
        # Ctrl/Cmd-click and a reload open it through the address.
        assert f'href="?show=all&amp;n={note.pk}"' in html
        assert task.identifier in html
        assert 'Select a notification' in html

    def test_the_inbox_page_does_not_query_per_item(self, client):
        project = ProjectFactory()
        me = _member(project)
        self._note(me, TaskFactory(project=project))
        client.force_login(me)
        client.get(reverse('inbox'))
        with CaptureQueriesContext(connection) as one:
            client.get(reverse('inbox'))
        for _ in range(5):
            self._note(me, TaskFactory(project=project), kind='commented')
        with CaptureQueriesContext(connection) as six:
            client.get(reverse('inbox'))

        assert len(six) == len(one)


@pytest.mark.django_db
class TestBadge:
    def test_the_sidebar_shows_the_unread_count(self, client):
        project = ProjectFactory()
        me = _member(project)
        for _ in range(2):
            Notification.objects.create(recipient=me, task=TaskFactory(project=project), kind='assigned')
        client.force_login(me)

        html = client.get(reverse('changelog')).content.decode()
        sidebar = re.search(r'<aside.*?</aside>', html, re.S).group(0)

        assert reverse('inbox') in sidebar
        assert re.search(r'data-inbox-badge[^>]*>\s*2\s*<', sidebar)

    def test_a_fragment_does_not_count_notifications(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())

        with CaptureQueriesContext(connection) as queries:
            client.get(reverse('task_activity_list', args=[task.pk]))

        assert not any('notifications_notification' in q['sql'] for q in queries)

    def test_no_tasks_module_means_no_inbox_link(self, client):
        preset = PermissionPreset.objects.create(name='dash only', access_dashboard=True, access_tasks=False)
        client.force_login(UserFactory(permission_preset=preset))

        html = client.get(reverse('changelog')).content.decode()

        assert reverse('inbox') not in html


@pytest.mark.django_db
class TestMentionMenu:
    def test_the_comment_box_lists_the_people_who_can_see_the_task(self, client):
        project = ProjectFactory()
        me = _member(project, name='Me Myself')
        _member(project, name='Ana Team')
        _member(ProjectFactory(), name='Zed Elsewhere')
        no_tasks = UserFactory(name='Nora NoTasks', permission_preset=PermissionPreset.objects.create(name='np', access_projects=True, access_tasks=False))
        ProjectAccessFactory(project=project, user=no_tasks)
        task = TaskFactory(project=project)
        client.force_login(me)

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        pattern = rf'<script id="mention-people-{task.pk}" type="application/json">(.*?)</script>'
        data = re.search(pattern, html, re.S)
        names = {person['name'] for person in json.loads(data.group(1))}
        assert 'Ana Team' in names and 'Me Myself' not in names
        assert 'Zed Elsewhere' not in names and 'Nora NoTasks' not in names
        assert 'role="listbox"' in html


@pytest.mark.django_db
class TestReviewFixes:
    def test_deleting_the_latest_comment_keeps_the_notice_for_an_earlier_one(self):
        project = ProjectFactory()
        follower, alice, carol = _member(project), _member(project), _member(project)
        task = TaskFactory(project=project)
        task.activities.filter(activity_type='created').update(user=follower)

        first = task_services.add_comment(task, 'A', alice)
        latest = task_services.add_comment(task, 'C', carol)
        task_services.delete_comment(latest, carol)

        note = Notification.objects.get(recipient=follower, kind='commented')
        assert note.activity == first and note.actor == alice

    def test_deleting_the_only_unread_comment_removes_the_notice(self):
        project = ProjectFactory()
        follower, alice = _member(project), _member(project)
        task = TaskFactory(project=project)
        task.activities.filter(activity_type='created').update(user=follower)
        old = task_services.add_comment(task, 'seen already', alice)
        Notification.objects.update(read_at='2026-01-01T00:00:00Z')

        latest = task_services.add_comment(task, 'new', alice)
        task_services.delete_comment(latest, alice)

        assert not Notification.objects.filter(recipient=follower, read_at__isnull=True).exists()
        assert old.pk

    def test_deleting_a_later_mention_keeps_an_earlier_mention(self):
        project = ProjectFactory()
        target = _member(project, name='Tia Target')
        alice, carol = _member(project), _member(project)
        task = TaskFactory(project=project)

        first = task_services.add_comment(task, 'hi @Tia Target', alice, mentions=[target.pk])
        latest = task_services.add_comment(task, 'again @Tia Target', carol, mentions=[target.pk])
        task_services.delete_comment(latest, carol)

        note = Notification.objects.get(recipient=target, kind='mentioned')
        assert note.activity == first

    def test_reassigning_withdraws_the_unread_assigned_notice(self):
        project = ProjectFactory()
        boss, first, second = _member(project), _member(project), _member(project)
        task = TaskFactory(project=project)

        _assign(task, first, boss)
        _assign(task, second, boss)

        assert _kinds(first) == []
        assert _kinds(second) == ['assigned']

    def test_reassigning_keeps_a_read_assigned_notice(self):
        project = ProjectFactory()
        boss, first, second = _member(project), _member(project), _member(project)
        task = TaskFactory(project=project)
        _assign(task, first, boss)
        Notification.objects.update(read_at='2026-01-01T00:00:00Z')

        _assign(task, second, boss)

        assert Notification.objects.filter(recipient=first, kind='assigned', read_at__isnull=False).exists()

    def test_the_mention_menu_is_found_next_to_its_textarea(self):
        from pathlib import Path

        script = Path('static/js/mentions.js').read_text()

        # A task open on its full page and in the drawer repeats the menu id.
        assert "getElementById(textarea.getAttribute('aria-controls'))" not in script


@pytest.mark.django_db
class TestMentionNamesAndAccess:
    def test_a_mention_is_the_longest_name_after_the_at(self):
        # "@Alex Pop" names Alex Pop. Alex was picked earlier and his hidden id is
        # still posted, but nothing in the text names him.
        project = ProjectFactory()
        author = _member(project)
        alex, alex_pop = _member(project, name='Alex'), _member(project, name='Alex Pop')
        task = TaskFactory(project=project)

        task_services.add_comment(task, 'over to @Alex Pop', author, mentions=[alex.pk, alex_pop.pk])

        assert _kinds(alex_pop) == ['mentioned']
        assert _kinds(alex) == []

    def test_both_are_mentioned_when_both_are_named(self):
        project = ProjectFactory()
        author = _member(project)
        alex, alex_pop = _member(project, name='Alex'), _member(project, name='Alex Pop')
        task = TaskFactory(project=project)

        task_services.add_comment(task, '@Alex and @Alex Pop', author, mentions=[alex.pk, alex_pop.pk])

        assert _kinds(alex) == ['mentioned']
        assert _kinds(alex_pop) == ['mentioned']

    def test_losing_access_withdraws_an_unread_assignment(self):
        from apps.projects.models import ProjectAccess

        project = ProjectFactory()
        boss, worker = _member(project), _member(project)
        task = TaskFactory(project=project)
        _assign(task, worker, boss)
        assert _kinds(worker) == ['assigned']

        ProjectAccess.objects.get(project=project, user=worker).delete()
        ProjectAccessFactory(project=project, user=worker)

        task.refresh_from_db()
        assert task.assignee is None
        assert _kinds(worker) == []


@pytest.mark.django_db
class TestMentionRuleOnDelete:
    def test_names_mentioned_takes_the_longest_name(self):
        from apps.notifications.services import names_mentioned

        names = {'Alex', 'Alex Pop', 'Bo'}

        assert names_mentioned('over to @Alex Pop', names) == {'Alex Pop'}
        assert names_mentioned('@Alex and @Alex Pop, cc @Bo', names) == {'Alex', 'Alex Pop', 'Bo'}
        assert names_mentioned('mail alex@example.com', names) == set()

    def test_a_deleted_mention_does_not_fall_back_to_a_comment_naming_someone_else(self):
        # Comment A names Alex Pop, comment B names Alex. Deleting B must not leave
        # Alex with a "mentioned you" pointing at A.
        project = ProjectFactory()
        author = _member(project)
        alex, alex_pop = _member(project, name='Alex'), _member(project, name='Alex Pop')
        task = TaskFactory(project=project)
        task_services.add_comment(task, 'over to @Alex Pop', author, mentions=[alex_pop.pk])
        second = task_services.add_comment(task, 'and @Alex too', author, mentions=[alex.pk])
        assert Notification.objects.filter(recipient=alex, kind='mentioned', read_at__isnull=True).exists()

        task_services.delete_comment(second, author)

        assert not Notification.objects.filter(recipient=alex, kind='mentioned').exists()


def _note(recipient, task, kind='assigned', **fields):
    return Notification.objects.create(recipient=recipient, actor=UserFactory(), task=task, kind=kind, **fields)


def _at(*args):
    return datetime(*args, tzinfo=ZoneInfo('Europe/Bucharest'))


@pytest.mark.django_db
class TestInboxTabs:
    def test_each_tab_lists_its_own_notifications(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project, title='Unread assigned'))
        _note(me, TaskFactory(project=project, title='Read comment'), kind='commented', read_at=timezone.now())
        _note(me, TaskFactory(project=project, title='Unread mention'), kind='mentioned')
        client.force_login(me)

        def titles(show):
            html = client.get(reverse('inbox'), {'show': show}).content.decode()
            return {t for t in ('Unread assigned', 'Read comment', 'Unread mention') if t in html}

        assert titles('all') == {'Unread assigned', 'Read comment', 'Unread mention'}
        assert titles('unread') == {'Unread assigned', 'Unread mention'}
        assert titles('mentions') == {'Unread mention'}
        assert titles('nonsense') == titles('all')

    def test_each_tab_has_its_empty_state(self, client):
        me = _member()
        client.force_login(me)

        def page(show):
            return client.get(reverse('inbox'), {'show': show}).content.decode()

        assert 'You are all caught up' in page('all')
        assert 'No unread notifications' in page('unread')
        assert 'No mentions yet' in page('mentions')

    def test_the_unread_tab_carries_the_count_and_the_list_is_grouped_by_day(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project))
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert re.search(r'id="inbox-unread-count"[^>]*>1<', html)
        assert 'Today' in html

    def test_show_more_pages_in_fifties(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        for kind in ('assigned', 'mentioned', 'commented'):
            for _ in range(20):
                _note(me, task, kind=kind, read_at=timezone.now())
        client.force_login(me)

        first = client.get(reverse('inbox')).content.decode()
        second = client.get(reverse('inbox'), {'limit': 100}).content.decode()

        def rows(html):
            return len(re.findall(r'\sdata-notification[\s>]', html))

        assert rows(first) == 50
        assert 'id="inbox-more"' in first and 'limit=100' in first and 'show=all' in first
        assert rows(second) == 60
        assert 'id="inbox-more"' not in second

    def test_the_query_count_does_not_grow_with_the_rows(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project))
        client.force_login(me)
        client.get(reverse('inbox'))
        with CaptureQueriesContext(connection) as one:
            client.get(reverse('inbox'))
        for _ in range(29):
            _note(me, TaskFactory(project=project), kind='commented')
        with CaptureQueriesContext(connection) as thirty:
            client.get(reverse('inbox'))

        assert len(thirty) == len(one)

    def test_a_row_has_the_attributes_the_keyboard_needs(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project, title='Fix login'))
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert f'id="notification-{note.pk}" role="option" data-notification' in html
        assert 'role="listbox"' in html and 'Fix login' in html
        assert 'data-unread="1"' in html
        assert f'data-read-url="{reverse("notification_read", args=[note.pk])}"' in html
        assert f'data-delete-url="{reverse("notification_delete", args=[note.pk])}"' in html


class TestGroupByDay:
    def _note(self, when):
        return SimpleNamespace(created_at=when)

    def _labels(self, today, *whens):
        groups = group_by_day([self._note(w) for w in whens], today)
        return [(group['label'], group['count']) for group in groups]

    def test_midnight_splits_today_from_yesterday(self):
        today = date(2026, 9, 30)  # a Wednesday

        assert self._labels(today, _at(2026, 9, 30, 0, 0), _at(2026, 9, 29, 23, 59, 59)) == [
            ('Today', 1), ('Yesterday', 1),
        ]

    def test_this_week_starts_on_monday(self):
        today = date(2026, 9, 30)

        assert self._labels(today, _at(2026, 9, 28, 0, 0), _at(2026, 9, 27, 23, 59)) == [
            ('This week', 1), ('Older', 1),
        ]

    def test_on_a_monday_yesterday_is_last_weeks_sunday_and_there_is_no_this_week(self):
        today = date(2026, 9, 28)

        assert self._labels(today, _at(2026, 9, 27, 12, 0), _at(2026, 9, 26, 12, 0)) == [
            ('Yesterday', 1), ('Older', 1),
        ]

    def test_empty_groups_are_left_out_and_order_is_kept(self):
        today = date(2026, 9, 30)
        groups = group_by_day([self._note(_at(2026, 9, 30, 9, 0)), self._note(_at(2026, 9, 30, 8, 0))], today)

        assert [group['key'] for group in groups] == ['today']
        assert [note.created_at.hour for note in groups[0]['rows']] == [9, 8]

    def test_the_day_is_the_local_one(self):
        # 22:30 UTC on the 29th is 01:30 on the 30th in Bucharest.
        when = datetime(2026, 9, 29, 22, 30, tzinfo=ZoneInfo('UTC'))

        assert self._labels(date(2026, 9, 30), when) == [('Today', 1)]


class TestShortAge:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=ZoneInfo('Europe/Bucharest'))

    def age(self, **delta):
        return short_age(self.now - timedelta(**delta), self.now)

    def test_minutes_hours_and_days(self):
        assert self.age(seconds=20) == 'now'
        assert self.age(minutes=5) == '5m'
        assert self.age(hours=3, minutes=30) == '3h'
        assert self.age(days=2, hours=5) == '2d'

    def test_a_week_or_more_is_a_date(self):
        assert self.age(days=7) == 'Sep 23'
        assert short_age(_at(2026, 1, 5, 10, 0), self.now) == 'Jan 5'

    def test_another_year_shows_the_year(self):
        assert short_age(_at(2025, 9, 12, 10, 0), self.now) == 'Sep 12, 2025'

    def test_a_time_in_the_future_is_now(self):
        assert short_age(self.now + timedelta(minutes=3), self.now) == 'now'


@pytest.mark.django_db
class TestNotificationOpen:
    def test_it_marks_read_fills_the_pane_and_updates_the_row_count_and_address(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project, title='Open me')
        note = _note(me, task)
        _note(me, TaskFactory(project=project), kind='commented')
        client.force_login(me)

        response = client.post(reverse('notification_open', args=[note.pk]))
        html = response.content.decode()

        assert response.status_code == 200
        note.refresh_from_db()
        assert note.read_at is not None
        assert 'Open me' in html and reverse('task_full_page', args=[project.pk, task.pk]) in html
        # The drawer's content, embedded: it does not open the slide-over or offer to close it.
        assert f'data-pane-for="{note.pk}"' in html
        assert 'openSlideOver();' not in html and 'onclick="closeSlideOver()"' not in html
        assert f'id="notification-{note.pk}"' in html and 'hx-swap-oob="true"' in html
        assert re.search(r'id="inbox-unread-count"[^>]*>1<', html)
        assert 'notificationsChanged' in response['HX-Trigger']
        assert response['HX-Replace-Url'] == f"{reverse('inbox')}?show=all&n={note.pk}"

    def test_someone_elses_notification_is_a_404_and_stays_unread(self, client):
        project = ProjectFactory()
        me, them = _member(project), _member(project)
        theirs = _note(them, TaskFactory(project=project))
        client.force_login(me)

        assert client.post(reverse('notification_open', args=[theirs.pk])).status_code == 404
        theirs.refresh_from_db()
        assert theirs.read_at is None

    def test_a_task_you_can_no_longer_see_is_a_404_and_stays_unread(self, client):
        project, gone = ProjectFactory(), ProjectFactory()
        me = _member(project)
        ProjectAccessFactory(project=gone, user=me)
        note = _note(me, TaskFactory(project=gone))
        me.project_access.filter(project=gone).delete()
        client.force_login(me)

        assert client.post(reverse('notification_open', args=[note.pk])).status_code == 404
        note.refresh_from_db()
        assert note.read_at is None

    def test_it_only_accepts_post(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project))
        client.force_login(me)

        assert client.get(reverse('notification_open', args=[note.pk])).status_code == 405


@pytest.mark.django_db
class TestUnreadAndDelete:
    def test_mark_unread_brings_a_read_row_back_and_the_count_follows(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project), read_at=timezone.now())
        client.force_login(me)

        response = client.post(reverse('notification_unread', args=[note.pk]))
        html = response.content.decode()

        note.refresh_from_db()
        assert note.read_at is None
        assert re.search(r'id="inbox-unread-count"[^>]*>1<', html)
        assert f'id="notification-{note.pk}"' in html and 'data-unread="1"' in html
        assert 'notificationsChanged' in response['HX-Trigger']

    def test_mark_unread_changes_nothing_when_an_unread_one_of_that_kind_exists(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        read = _note(me, task, read_at=timezone.now())
        _note(me, task)
        client.force_login(me)

        response = client.post(reverse('notification_unread', args=[read.pk]))

        assert response.status_code == 200
        read.refresh_from_db()
        assert read.read_at is not None
        assert 'data-unread="0"' in response.content.decode()

    def test_that_row_says_it_cannot_be_marked_unread(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        _note(me, task, read_at=timezone.now())
        _note(me, task)
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert 'data-unread="0"' in html and 'data-can-unread="0"' in html

    def test_delete_removes_the_row_and_updates_the_count(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project))
        keep = _note(me, TaskFactory(project=project))
        client.force_login(me)

        response = client.post(reverse('notification_delete', args=[note.pk]))

        assert not Notification.objects.filter(pk=note.pk).exists()
        assert Notification.objects.filter(pk=keep.pk).exists()
        html = response.content.decode()
        assert f'<div id="notification-{note.pk}" hx-swap-oob="delete"></div>' in html
        assert re.search(r'id="inbox-unread-count"[^>]*>1<', html)
        assert 'notificationsChanged' in response['HX-Trigger']
        assert f'"notificationDeleted": {{"id": {note.pk}}}' in response['HX-Trigger']

    @pytest.mark.parametrize('name', ['notification_unread', 'notification_delete', 'notification_read'])
    def test_nobody_else_can_change_a_notification(self, client, name):
        project = ProjectFactory()
        me, them = _member(project), _member(project)
        theirs = _note(them, TaskFactory(project=project), read_at=timezone.now())
        client.force_login(me)

        assert client.post(reverse(name, args=[theirs.pk])).status_code == 404
        theirs.refresh_from_db()
        assert theirs.read_at is not None

    @pytest.mark.parametrize('name', ['notification_unread', 'notification_delete'])
    def test_these_need_post(self, client, name):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project))
        client.force_login(me)

        assert client.get(reverse(name, args=[note.pk])).status_code == 405
        assert Notification.objects.filter(pk=note.pk).exists()

    def test_mark_all_read_keeps_the_tab_and_updates_the_count(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project, title='Mention'), kind='mentioned')
        _note(me, TaskFactory(project=project, title='Assigned'))
        client.force_login(me)

        response = client.post(reverse('notification_read_all') + '?show=mentions')
        html = response.content.decode()

        assert 'Mention' in html and 'Assigned' not in html
        assert not Notification.objects.filter(recipient=me, read_at__isnull=True).exists()
        assert re.search(r'id="inbox-unread-count"[^>]*>0<', html)


@pytest.mark.django_db
class TestPane:
    def test_a_link_with_n_shows_that_notification_without_marking_it_read(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project, title='Linked task'))
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': note.pk}).content.decode()

        note.refresh_from_db()
        assert note.read_at is None
        assert f'data-pane-for="{note.pk}"' in html and 'Select a notification</p>' not in html.split('id="inbox-pane"')[1].split('</section>')[0]
        assert f'data-selected="{note.pk}"' in html
        # The pane marks it read itself, with a POST, once it has loaded.
        assert f'hx-post="{reverse("notification_read", args=[note.pk])}?show=all" hx-trigger="load"' in html

    def test_a_read_notification_in_the_link_does_not_post_again(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project), read_at=timezone.now())
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': note.pk}).content.decode()

        assert f'data-pane-for="{note.pk}"' in html
        assert 'hx-trigger="load"' not in html

    @pytest.mark.parametrize('raw', ['999999', 'abc', ''])
    def test_an_unknown_n_shows_the_empty_pane(self, client, raw):
        me = _member()
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': raw}).content.decode()

        assert 'data-pane-for' not in html
        assert 'Select a notification' in html
        assert 'data-selected=' not in html

    def test_someone_elses_notification_in_the_link_is_not_shown(self, client):
        project = ProjectFactory()
        me, them = _member(project), _member(project)
        theirs = _note(them, TaskFactory(project=project, title='Not yours'))
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': theirs.pk}).content.decode()

        assert 'Not yours' not in html and 'data-pane-for' not in html

    def test_a_comment_notification_points_at_its_comment_and_an_assignment_does_not(self, client):
        from apps.tasks.factories import TaskActivityFactory

        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        comment = TaskActivityFactory(task=task, activity_type='comment', content='Look here')
        commented = Notification.objects.create(
            recipient=me, actor=comment.user, task=task, kind='commented', activity=comment
        )
        assigned = _note(me, TaskFactory(project=project))
        client.force_login(me)

        commented_pane = client.post(reverse('notification_open', args=[commented.pk])).content.decode()
        assigned_pane = client.post(reverse('notification_open', args=[assigned.pk])).content.decode()

        assert f'data-activity="{comment.pk}"' in commented_pane
        assert f'id="activity-{comment.pk}"' in commented_pane
        assert 'data-activity=' not in assigned_pane

    def test_the_tab_is_kept_in_the_address_and_the_rows(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project), kind='mentioned')
        client.force_login(me)

        response = client.post(reverse('notification_open', args=[note.pk]) + '?show=mentions')

        assert response['HX-Replace-Url'].endswith(f'?show=mentions&n={note.pk}')
        assert f'href="?show=mentions&amp;n={note.pk}"' in response.content.decode()

    def test_the_drawer_itself_is_unchanged(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        client.force_login(me)

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        assert 'openSlideOver();' in html
        assert 'onclick="closeSlideOver()"' in html

    def test_the_page_is_the_split_view(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project))
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert 'id="inbox"' in html and 'id="inbox-list"' in html and 'id="inbox-pane"' in html
        assert 'id="task-view"' not in html and 'data-task-row' not in html
        assert 'id="task-shortcuts"' in html and 'Delete and open the next' in html


@pytest.mark.django_db
class TestSplitViewReviewFixes:
    def test_delete_task_in_the_pane_does_not_need_a_task_row(self, client):
        project = ProjectFactory()
        admin = AdminUserFactory()
        task = TaskFactory(project=project)
        note = Notification.objects.create(recipient=admin, task=task, kind='assigned', actor=UserFactory())
        client.force_login(admin)

        pane = client.post(reverse('notification_open', args=[note.pk])).content.decode()
        drawer = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        delete_url = re.escape(reverse('task_delete', args=[task.pk]))
        delete = re.search(rf'<button hx-post="{delete_url}"[^>]*>', pane).group(0)
        assert 'hx-swap="none"' in delete and 'hx-target' not in delete
        assert f'hx-target="#task-{task.pk}"' in drawer

    def test_a_row_is_a_plain_link_the_script_opens(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project))
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()
        row = re.search(rf'<a id="notification-{note.pk}"[^>]*>', html, re.S).group(0)

        # No htmx on the row: htmx would cancel a Ctrl/Cmd-click before its filter ran.
        assert 'hx-post' not in row and 'hx-trigger' not in row
        assert f'data-open-url="{reverse("notification_open", args=[note.pk])}?show=all"' in row
        assert 'tabindex="-1"' in row

    def test_a_non_ascii_digit_in_n_is_the_empty_pane(self, client):
        client.force_login(_member())

        response = client.get(reverse('inbox'), {'n': '²'})

        assert response.status_code == 200
        assert 'Select a notification' in response.content.decode()

    def test_the_read_on_load_keeps_the_tab(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project), kind='mentioned')
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': note.pk, 'show': 'mentions'}).content.decode()

        assert f'hx-post="{reverse("notification_read", args=[note.pk])}?show=mentions" hx-trigger="load"' in html

    def test_the_selected_row_is_marked_on_the_row(self, client):
        project = ProjectFactory()
        me = _member(project)
        note = _note(me, TaskFactory(project=project))
        other = _note(me, TaskFactory(project=project), kind='commented')
        client.force_login(me)

        html = client.get(reverse('inbox'), {'n': note.pk}).content.decode()

        assert re.search(rf'<a id="notification-{note.pk}"[^>]*aria-selected="true"', html, re.S)
        assert re.search(rf'<a id="notification-{other.pk}"[^>]*aria-selected="false"', html, re.S)

    def test_the_list_carries_its_own_refresh_and_page_size(self, client):
        project = ProjectFactory()
        me = _member(project)
        _note(me, TaskFactory(project=project))
        client.force_login(me)

        html = client.get(reverse('inbox'), {'limit': 100}).content.decode()
        listing = html.split('id="inbox-list"')[1].split('id="inbox-pane"')[0]

        assert 'data-limit="100"' in html
        assert 'taskChanged from:body' in listing and 'limit=100' in listing

    def test_mark_all_read_keeps_the_page_size_sent_with_it(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        for kind in ('assigned', 'mentioned', 'commented'):
            for _ in range(20):
                _note(me, task, kind=kind, read_at=timezone.now())
        client.force_login(me)

        html = client.post(reverse('notification_read_all') + '?show=all', {'limit': 100}).content.decode()

        assert len(re.findall(r'\sdata-notification[\s>]', html)) == 60

    def test_the_page_is_kept_out_of_the_history_cache_and_the_pane_is_not_live(self, client):
        client.force_login(_member())

        html = client.get(reverse('inbox')).content.decode()

        assert re.search(r'id="inbox"[^>]*hx-history="false"', html)
        pane = re.search(r'<section id="inbox-pane"[^>]*>', html).group(0)
        assert 'aria-live' not in pane


@pytest.mark.django_db
class TestSecondReviewOfTheSplitView:
    def test_the_open_notification_stays_on_the_unread_tab_once_read(self, client):
        # Opening marks it read. Without this the next refresh drops its row while the
        # pane still shows it, and the pane's buttons have nothing to act on.
        project = ProjectFactory()
        user = _member(project)
        task = TaskFactory(project=project)
        opened = _note(user, task, read_at=timezone.now())
        other_read = _note(user, TaskFactory(project=project), read_at=timezone.now())
        unread = _note(user, TaskFactory(project=project))
        client.force_login(user)

        html = client.get(reverse('inbox'), {'show': 'unread', 'n': opened.pk, 'list': '1'}).content.decode()

        assert f'id="notification-{opened.pk}"' in html
        assert f'id="notification-{unread.pk}"' in html
        assert f'id="notification-{other_read.pk}"' not in html
        # Without a notification open, the tab is only what is unread.
        plain = client.get(reverse('inbox'), {'show': 'unread'}).content.decode()
        assert f'id="notification-{opened.pk}"' not in plain

    def test_a_list_refresh_does_not_render_the_pane(self, client):
        project = ProjectFactory()
        user = _member(project)
        note = _note(user, TaskFactory(project=project, title='Whole task in the pane'))
        client.force_login(user)

        refresh = client.get(reverse('inbox'), {'show': 'all', 'n': note.pk, 'list': '1'})
        page = client.get(reverse('inbox'), {'show': 'all', 'n': note.pk})

        assert 'data-pane-for' not in refresh.content.decode()
        assert f'data-pane-for="{note.pk}"' in page.content.decode()

    def test_no_show_more_once_the_list_is_at_its_limit(self):
        from apps.notifications import views

        user = UserFactory()
        task = TaskFactory()
        Notification.objects.bulk_create(
            Notification(recipient=user, actor=None, task=task, kind='commented', read_at=timezone.now())
            for _ in range(60)
        )
        ProjectAccessFactory(project=task.project, user=user)

        assert views._list_context(user, 'all', limit=50)['more_url'] is not None
        # 60 rows, pretend the limit is the ceiling: the button would ask for a page that never comes.
        original = views.MAX_LIMIT
        views.MAX_LIMIT = 50
        try:
            assert views._list_context(user, 'all', limit=50)['more_url'] is None
        finally:
            views.MAX_LIMIT = original

    def test_the_drawer_names_its_lists_per_task(self, client):
        # The Inbox pane embeds a task in the page; a drawer opened over it for another
        # task must not share element ids with it, or its sub-tasks land in the pane.
        project = ProjectFactory()
        user = _member(project)
        task = TaskFactory(project=project)
        client.force_login(user)

        html = client.get(reverse('task_detail', args=[task.pk]), HTTP_HX_REQUEST='true').content.decode()

        assert f'id="subtask-list-{task.pk}"' in html
        assert f'hx-target="#subtask-list-{task.pk}"' in html
        assert f'id="attachment-list-{task.pk}"' in html
        assert 'id="subtask-list"' not in html and 'id="attachment-list"' not in html
