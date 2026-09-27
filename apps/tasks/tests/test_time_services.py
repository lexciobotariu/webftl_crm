from datetime import datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectMemberFactory
from apps.tasks import services
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import TimeEntry


def _member(role='editor'):
    user = UserFactory()
    task = TaskFactory(time_estimate=5)
    ProjectMemberFactory(project=task.project, user=user, role=role)
    return user, task


def _at(hours_ago):
    return timezone.now() - timedelta(hours=hours_ago)


@pytest.mark.django_db
class TestTimerRules:
    def test_start_creates_one_open_timer(self):
        user, task = _member()

        entry = services.start_timer(task, user)

        assert entry.ended_at is None
        assert entry.user == user
        assert entry.task == task
        assert TimeEntry.objects.filter(user=user, ended_at__isnull=True).count() == 1

    def test_one_open_timer_per_user(self):
        user, task = _member()
        TimeEntryFactory(user=user, task=task, running=True)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                TimeEntryFactory(user=user, task=task, running=True)

    def test_other_users_may_each_have_an_open_timer(self):
        _, task = _member()
        TimeEntryFactory(task=task, running=True)
        TimeEntryFactory(task=task, running=True)
        assert TimeEntry.objects.filter(ended_at__isnull=True).count() == 2

    def test_start_on_another_task_closes_the_previous_at_now(self):
        user, task = _member()
        other = TaskFactory(project=task.project, status=task.status)
        before = timezone.now()
        first = services.start_timer(task, user)

        second = services.start_timer(other, user)
        after = timezone.now()

        first.refresh_from_db()
        assert first.ended_at is not None
        assert before <= first.ended_at <= after
        assert second.ended_at is None
        assert TimeEntry.objects.filter(user=user, ended_at__isnull=True).count() == 1

    def test_start_closes_an_expired_timer_at_the_twelve_hour_mark(self):
        user, task = _member()
        other = TaskFactory(project=task.project, status=task.status)
        started = _at(15)
        previous = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)

        services.start_timer(other, user)

        previous.refresh_from_db()
        assert previous.ended_at == started + timedelta(hours=12)
        assert TimeEntry.objects.filter(user=user, ended_at__isnull=True).count() == 1

    def test_stop_sets_ended_at_to_now(self):
        user, task = _member()
        services.start_timer(task, user)
        before = timezone.now()

        entry = services.stop_timer(user)
        after = timezone.now()

        assert before <= entry.ended_at <= after
        assert services.stop_timer(user) is None

    def test_stop_of_an_expired_timer_uses_the_twelve_hour_mark(self):
        user, task = _member()
        started = _at(13)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)

        stopped = services.stop_timer(user)

        assert stopped.pk == entry.pk
        assert stopped.ended_at == started + timedelta(hours=12)

    def test_logging_time_does_not_change_the_estimate(self):
        user, task = _member()
        services.log_manual(task, user, _at(2), _at(1), '')
        task.refresh_from_db()
        assert task.time_estimate == 5


@pytest.mark.django_db
class TestTwelveHourClose:
    def test_close_sets_end_to_start_plus_twelve_hours(self):
        user, task = _member()
        started = _at(15)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)
        fresh = TimeEntryFactory(
            user=UserFactory(),
            task=task,
            started_at=_at(2),
            ended_at=None,
        )

        closed = services.close_expired_timers()

        entry.refresh_from_db()
        fresh.refresh_from_db()
        assert closed == 1
        assert entry.ended_at == started + timedelta(hours=12)
        assert fresh.ended_at is None

    def test_close_at_exactly_twelve_hours(self):
        user, task = _member()
        started = _at(12)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)

        services.close_expired_timers(now=started + timedelta(hours=12))

        entry.refresh_from_db()
        assert entry.ended_at == started + timedelta(hours=12)

    def test_close_leaves_a_shorter_timer_running(self):
        user, task = _member()
        started = _at(12)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)

        services.close_expired_timers(now=started + timedelta(hours=12) - timedelta(seconds=1))

        entry.refresh_from_db()
        assert entry.ended_at is None

    def test_close_does_not_shorten_a_long_manual_entry(self):
        user, task = _member()
        now = timezone.now()
        started = now - timedelta(hours=30)
        ended = now - timedelta(hours=1)
        entry = services.log_manual(task, user, started, ended, 'long')

        services.close_expired_timers()

        entry.refresh_from_db()
        assert entry.ended_at == ended
        assert entry.duration == timedelta(hours=29)


@pytest.mark.django_db
class TestLoggedSeconds:
    def test_two_closed_entries_sum_including_another_person(self):
        user, task = _member()
        other = UserFactory()
        now = timezone.now()
        TimeEntryFactory(
            user=user, task=task,
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=1),
        )
        TimeEntryFactory(
            user=other, task=task,
            started_at=now - timedelta(hours=2, minutes=5),
            ended_at=now - timedelta(hours=1),
        )
        elsewhere = TaskFactory(project=task.project, status=task.status)
        TimeEntryFactory(
            user=user, task=elsewhere,
            started_at=now - timedelta(hours=8),
            ended_at=now - timedelta(hours=4),
        )

        assert services.logged_seconds_on_task(task, now=now) == (2 * 3600) + (3600 + 5 * 60)

    def test_a_closed_entry_longer_than_twelve_hours_counts_in_full(self):
        user, task = _member()
        now = timezone.now()
        TimeEntryFactory(
            user=user, task=task,
            started_at=now - timedelta(hours=30),
            ended_at=now - timedelta(hours=1),
        )

        assert services.logged_seconds_on_task(task, now=now) == 29 * 3600

    def test_running_timer_counts_elapsed_and_not_past_twelve_hours(self):
        user, task = _member()
        now = timezone.now()
        TimeEntryFactory(
            user=user, task=task,
            started_at=now - timedelta(hours=2, minutes=5),
            ended_at=None,
        )

        assert services.logged_seconds_on_task(task, now=now) == 2 * 3600 + 5 * 60

        long_start = now - timedelta(hours=15)
        TimeEntryFactory(
            user=UserFactory(), task=task,
            started_at=long_start, ended_at=None,
        )

        assert services.logged_seconds_on_task(task, now=now) == (2 * 3600 + 5 * 60) + 12 * 3600

    def test_no_entries_is_zero(self):
        _, task = _member()
        assert services.logged_seconds_on_task(task) == 0


@pytest.mark.django_db
class TestManualValidation:
    def test_manual_entry_may_exceed_twelve_hours(self):
        user, task = _member()
        now = timezone.now()
        entry = services.log_manual(
            task, user, now - timedelta(hours=20), now - timedelta(hours=1), 'deep work'
        )
        assert entry.duration == timedelta(hours=19)
        assert entry.note == 'deep work'
        assert entry.user == user

    def test_end_must_be_after_start(self):
        user, task = _member()
        start = _at(1)
        with pytest.raises(services.TimeEntryValidationError, match='after start'):
            services.log_manual(task, user, start, start - timedelta(minutes=1), '')

    def test_end_equal_to_start_is_rejected(self):
        user, task = _member()
        start = _at(1)
        with pytest.raises(services.TimeEntryValidationError, match='after start'):
            services.log_manual(task, user, start, start, '')

    def test_end_cannot_be_in_the_future(self):
        user, task = _member()
        with pytest.raises(services.TimeEntryValidationError, match='future'):
            services.log_manual(task, user, _at(1), timezone.now() + timedelta(minutes=5), '')


@pytest.mark.django_db
class TestTimePermissions:
    def test_viewer_cannot_log_time(self):
        user, task = _member('viewer')
        with pytest.raises(PermissionDenied):
            services.start_timer(task, user)
        with pytest.raises(PermissionDenied):
            services.log_manual(task, user, _at(2), _at(1), '')

    def test_editor_can_log_and_edit_own_entry(self):
        user, task = _member('editor')
        entry = services.log_manual(task, user, _at(3), _at(2), 'first')

        updated = services.update_entry(
            entry, user, started_at=_at(4), ended_at=_at(2), note='revised'
        )

        assert updated.note == 'revised'
        services.delete_entry(entry, user)
        assert not TimeEntry.objects.filter(pk=entry.pk).exists()

    def test_editor_cannot_change_someone_elses_entry(self):
        owner, task = _member('editor')
        other = UserFactory()
        ProjectMemberFactory(project=task.project, user=other, role='editor')
        entry = services.log_manual(task, owner, _at(3), _at(1), 'mine')

        with pytest.raises(PermissionDenied):
            services.update_entry(entry, other, started_at=_at(3), ended_at=_at(1), note='nope')
        with pytest.raises(PermissionDenied):
            services.delete_entry(entry, other)

        entry.refresh_from_db()
        assert entry.note == 'mine'

    def test_manager_cannot_edit_someone_elses_entry(self):
        owner, task = _member('editor')
        manager = UserFactory()
        ProjectMemberFactory(project=task.project, user=manager, role='manager')
        entry = services.log_manual(task, owner, _at(3), _at(1), 'mine')

        with pytest.raises(PermissionDenied):
            services.update_entry(
                entry, manager, started_at=_at(3), ended_at=_at(1), note='nope'
            )
        with pytest.raises(PermissionDenied):
            services.delete_entry(entry, manager)

    def test_manager_can_edit_own_entry(self):
        manager, task = _member('manager')
        entry = services.log_manual(task, manager, _at(2), _at(1), 'own')
        services.update_entry(entry, manager, started_at=_at(2), ended_at=_at(1), note='edited')
        entry.refresh_from_db()
        assert entry.note == 'edited'

    def test_admin_can_change_any_entry(self):
        owner, task = _member('editor')
        admin = AdminUserFactory()
        entry = services.log_manual(task, owner, _at(3), _at(1), 'mine')

        services.update_entry(entry, admin, started_at=_at(3), ended_at=_at(1), note='admin')
        entry.refresh_from_db()
        assert entry.note == 'admin'
        services.delete_entry(entry, admin)
        assert not TimeEntry.objects.filter(pk=entry.pk).exists()

    def test_owner_who_is_only_a_viewer_cannot_edit(self):
        user, task = _member('viewer')
        entry = TimeEntryFactory(user=user, task=task, started_at=_at(2), ended_at=_at(1))

        with pytest.raises(PermissionDenied):
            services.update_entry(entry, user, started_at=_at(2), ended_at=_at(1), note='no')
        with pytest.raises(PermissionDenied):
            services.delete_entry(entry, user)

    def test_update_rejects_a_future_end_and_an_end_before_start(self):
        user, task = _member()
        entry = services.log_manual(task, user, _at(3), _at(1), '')
        with pytest.raises(services.TimeEntryValidationError, match='future'):
            services.update_entry(
                entry, user,
                started_at=_at(1),
                ended_at=timezone.now() + timedelta(minutes=5),
                note='',
            )
        with pytest.raises(services.TimeEntryValidationError, match='after start'):
            services.update_entry(entry, user, started_at=_at(1), ended_at=_at(2), note='')


def _monday_start():
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    return monday, timezone.make_aware(datetime.combine(monday, time.min))


@pytest.mark.django_db
class TestWeekQuery:
    def test_week_and_project_filters(self):
        user, task = _member()
        monday, week_start = _monday_start()
        this_week = TimeEntryFactory(
            user=user, task=task,
            started_at=week_start + timedelta(hours=10),
            ended_at=week_start + timedelta(hours=11),
        )
        last_week = TimeEntryFactory(
            user=user, task=task,
            started_at=week_start - timedelta(hours=5),
            ended_at=week_start - timedelta(hours=4),
        )
        other_task = TaskFactory()
        ProjectMemberFactory(project=other_task.project, user=user, role='editor')
        other_project = TimeEntryFactory(
            user=user, task=other_task,
            started_at=week_start + timedelta(hours=12),
            ended_at=week_start + timedelta(hours=13),
        )

        week = list(services.entries_for_week(user, monday))
        assert this_week in week
        assert other_project in week
        assert last_week not in week

        on_project = list(services.entries_for_week(user, monday, project=task.project))
        assert this_week in on_project
        assert other_project not in on_project

    def test_manager_sees_everyone_on_the_project_and_not_on_their_own_week(self):
        owner, task = _member('editor')
        manager = UserFactory()
        editor = UserFactory()
        ProjectMemberFactory(project=task.project, user=manager, role='manager')
        ProjectMemberFactory(project=task.project, user=editor, role='editor')
        monday, week_start = _monday_start()
        theirs = TimeEntryFactory(
            user=owner, task=task,
            started_at=week_start + timedelta(hours=2),
            ended_at=week_start + timedelta(hours=3),
        )

        assert theirs in list(services.entries_for_week(manager, monday, project=task.project))
        assert theirs not in list(services.entries_for_week(manager, monday))
        assert theirs in list(services.entries_for_week(owner, monday, project=task.project))
        assert theirs not in list(services.entries_for_week(editor, monday, project=task.project))

    def test_admin_sees_everyone_on_the_project(self):
        owner, task = _member()
        admin = AdminUserFactory()
        monday, week_start = _monday_start()
        entry = TimeEntryFactory(
            user=owner, task=task,
            started_at=week_start + timedelta(hours=4),
            ended_at=week_start + timedelta(hours=5),
        )
        assert entry in list(services.entries_for_week(admin, monday, project=task.project))
        assert entry not in list(services.entries_for_week(admin, monday))
