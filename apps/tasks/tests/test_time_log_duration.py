from datetime import UTC, date, datetime, time, timedelta
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectAccessFactory
from apps.tasks import services
from apps.tasks.factories import TaskFactory, TimeEntryFactory

# 00:30 on 2 June in Bucharest (UTC+3), still the evening of 1 June in UTC.
EARLY_MORNING = datetime(2026, 6, 1, 21, 30, tzinfo=UTC)
TODAY = date(2026, 6, 2)


def _member():
    user = UserFactory()
    task = TaskFactory()
    ProjectAccessFactory(project=task.project, user=user)
    return user, task


def _midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


@pytest.fixture
def early_morning():
    with mock.patch('django.utils.timezone.now', return_value=EARLY_MORNING):
        yield


@pytest.mark.django_db
class TestLogDuration:
    def test_it_logs_a_closed_entry_at_local_midnight_of_the_day(self, early_morning):
        user, task = _member()

        entry = services.log_duration(task, user, 90, date(2026, 6, 1), 'review')

        assert entry.started_at == _midnight(date(2026, 6, 1))
        assert entry.ended_at == entry.started_at + timedelta(minutes=90)
        assert (entry.user, entry.task, entry.note) == (user, task, 'review')
        assert timezone.localtime(entry.started_at).time() == time.min

    def test_a_long_log_early_in_the_morning_is_fine(self, early_morning):
        # The end lands after "now", which the start/end form used to refuse.
        user, task = _member()
        entry = services.log_duration(task, user, 8 * 60, TODAY)
        assert entry.ended_at > timezone.now()

    def test_a_day_in_the_future_is_refused(self, early_morning):
        user, task = _member()
        with pytest.raises(services.TimeEntryValidationError, match='future'):
            services.log_duration(task, user, 30, TODAY + timedelta(days=1))

    def test_today_in_the_app_zone_counts_as_today_even_when_utc_is_yesterday(self, early_morning):
        user, task = _member()
        assert services.log_duration(task, user, 30, TODAY).pk

    @pytest.mark.parametrize('minutes', [0, -5, 24 * 60 + 1, None])
    def test_the_duration_must_be_between_a_minute_and_a_day(self, early_morning, minutes):
        user, task = _member()
        with pytest.raises(services.TimeEntryValidationError):
            services.log_duration(task, user, minutes, TODAY)

    def test_a_full_day_is_allowed(self, early_morning):
        user, task = _member()
        assert services.log_duration(task, user, 24 * 60, TODAY).pk

    def test_a_missing_day_is_refused(self):
        user, task = _member()
        with pytest.raises(services.TimeEntryValidationError):
            services.log_duration(task, user, 30, None)

    def test_a_viewer_cannot_log(self):
        task = TaskFactory()
        with pytest.raises(PermissionDenied):
            services.log_duration(task, UserFactory(), 30, timezone.localdate())


@pytest.mark.django_db
class TestUpdateEntryByDuration:
    def test_a_timer_keeps_its_real_start_and_the_end_follows_the_duration(self):
        user, task = _member()
        started = timezone.now().replace(hour=9, minute=15, second=0, microsecond=0) - timedelta(days=1)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=started + timedelta(hours=2))

        services.update_entry(entry, user, minutes=45, day=timezone.localdate(started), note='shorter')

        entry.refresh_from_db()
        assert entry.started_at == started
        assert entry.ended_at == started + timedelta(minutes=45)
        assert entry.note == 'shorter'

    def test_changing_the_day_moves_the_start_to_that_days_midnight(self):
        user, task = _member()
        entry = services.log_duration(task, user, 60, timezone.localdate() - timedelta(days=3))
        new_day = timezone.localdate() - timedelta(days=1)

        services.update_entry(entry, user, minutes=120, day=new_day, note='')

        entry.refresh_from_db()
        assert entry.started_at == _midnight(new_day)
        assert entry.ended_at == entry.started_at + timedelta(hours=2)

    def test_the_same_rules_as_logging(self):
        user, task = _member()
        entry = services.log_duration(task, user, 60, timezone.localdate())
        with pytest.raises(services.TimeEntryValidationError, match='future'):
            services.update_entry(entry, user, minutes=60, day=timezone.localdate() + timedelta(days=1), note='')
        with pytest.raises(services.TimeEntryValidationError):
            services.update_entry(entry, user, minutes=0, day=timezone.localdate(), note='')

    def test_a_running_timer_cannot_be_edited(self):
        user, task = _member()
        running = TimeEntryFactory(user=user, task=task, running=True)
        with pytest.raises(services.TimeEntryValidationError, match='running'):
            services.update_entry(running, user, minutes=30, day=timezone.localdate(), note='')

    def test_an_admin_may_edit_anyones_entry(self):
        user, task = _member()
        entry = services.log_duration(task, user, 60, timezone.localdate())
        services.update_entry(entry, AdminUserFactory(), minutes=30, day=timezone.localdate(), note='x')
        entry.refresh_from_db()
        assert entry.ended_at - entry.started_at == timedelta(minutes=30)

    def test_someone_else_cannot(self):
        user, task = _member()
        entry = services.log_duration(task, user, 60, timezone.localdate())
        other = UserFactory()
        ProjectAccessFactory(project=task.project, user=other)
        with pytest.raises(PermissionDenied):
            services.update_entry(entry, other, minutes=30, day=timezone.localdate(), note='')


@pytest.mark.django_db
class TestSameDayOrder:
    def test_entries_from_one_day_keep_a_stable_order_by_pk(self):
        user, task = _member()
        day = timezone.localdate()
        first = services.log_duration(task, user, 30, day, 'a')
        second = services.log_duration(task, user, 30, day, 'b')
        third = services.log_duration(task, user, 30, day, 'c')

        assert list(services.entries_on_task(user, task)) == [third, second, first]
        week = services.entries_for_week(user, day)
        assert list(week) == [first, second, third]
