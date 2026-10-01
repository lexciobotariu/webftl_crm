from datetime import UTC, date, datetime
from unittest import mock

import pytest
from django.conf import settings
from django.utils import timezone

from apps.tasks.factories import TaskFactory
from apps.tasks.models import Task

# 01:30 on 2 June in Bucharest (UTC+3 in summer), still 1 June in UTC.
LATE_EVENING_UTC = datetime(2026, 6, 1, 22, 30, tzinfo=UTC)


def test_app_time_zone_defaults_to_bucharest():
    assert settings.TIME_ZONE == 'Europe/Bucharest'


@pytest.mark.django_db
class TestTodayFollowsAppTimeZone:
    def test_task_due_today_in_utc_is_overdue_after_local_midnight(self):
        task = TaskFactory(due_date=date(2026, 6, 1))
        with mock.patch('django.utils.timezone.now', return_value=LATE_EVENING_UTC):
            assert timezone.localdate() == date(2026, 6, 2)
            assert task.is_overdue is True
            assert list(Task.objects.overdue()) == [task]

    def test_task_due_on_local_today_is_not_overdue(self):
        task = TaskFactory(due_date=date(2026, 6, 2))
        with mock.patch('django.utils.timezone.now', return_value=LATE_EVENING_UTC):
            assert task.is_overdue is False
            assert list(Task.objects.overdue()) == []
