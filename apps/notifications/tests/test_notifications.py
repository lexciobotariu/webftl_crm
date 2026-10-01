import json
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.notifications.models import Notification
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

    def test_an_item_opens_the_task_drawer_and_links_the_full_page(self, client):
        project = ProjectFactory()
        me = _member(project)
        task = TaskFactory(project=project)
        note = self._note(me, task)
        client.force_login(me)

        html = client.get(reverse('inbox')).content.decode()

        assert f'hx-get="{reverse("task_detail", args=[task.pk])}"' in html
        assert f'href="{reverse("task_full_page", args=[project.pk, task.pk])}"' in html
        assert reverse('notification_read', args=[note.pk]) in html
        assert task.identifier in html

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
