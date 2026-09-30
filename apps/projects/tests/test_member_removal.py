from datetime import datetime, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.notes.models import Note, can_modify_note
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import TimeEntry


def _monday_start():
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    return timezone.make_aware(datetime.combine(monday, time.min))


@pytest.mark.django_db
class TestMemberRemoval:
    def test_removal_clears_assignee_and_keeps_history(self, client):
        user = UserFactory(name='Former Member')
        other = UserFactory(name='Other Logger')
        project = ProjectFactory(name='Acme Build')
        status = project.statuses.first()
        status.name = 'Ship It'
        status.save()
        task = TaskFactory(
            project=project,
            status=status,
            assignee=user,
            title='Design the logo',
            description='Secret brief',
        )
        membership = ProjectAccessFactory(project=project, user=user)
        ProjectAccessFactory(project=project, user=other)

        kept_project = ProjectFactory()
        kept = TaskFactory(project=kept_project, assignee=user, title='Still mine')
        ProjectAccessFactory(project=kept_project, user=user)

        week_start = _monday_start()
        entry = TimeEntryFactory(
            user=user,
            task=task,
            started_at=week_start + timedelta(hours=9),
            ended_at=week_start + timedelta(hours=11),
        )
        TimeEntryFactory(
            user=other,
            task=task,
            started_at=week_start + timedelta(hours=12),
            ended_at=week_start + timedelta(hours=13),
        )
        running = TimeEntryFactory(user=user, task=task, running=True)

        note = Note.objects.create(
            project=project,
            title='Keep me',
            description='still here',
            created_by=user,
        )
        assert can_modify_note(user, note) is True

        membership.delete()

        task.refresh_from_db()
        running.refresh_from_db()
        assert task.assignee_id is None
        assert TimeEntry.objects.filter(pk=entry.pk).exists()
        assert TimeEntry.objects.filter(pk=running.pk).exists()
        assert running.ended_at is not None
        assert Note.objects.filter(pk=note.pk).exists()
        assert can_modify_note(user, note) is False
        note.refresh_from_db()
        assert note.title == 'Keep me'

        client.force_login(user)
        assert client.get(reverse('task_full_page', args=[project.pk, task.pk])).status_code == 403
        assert client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board').status_code == 403
        assert client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'still here'},
        ).status_code == 403
        assert client.post(reverse('timer_start', args=[task.pk])).status_code == 403
        assert client.post(
            reverse('note_edit_drawer', args=[note.pk]),
            {'title': 'Hacked', 'description': ''},
        ).status_code == 403

        my_tasks = client.get(reverse('my_tasks'), {'layout': 'list'}).content.decode()
        assert 'Design the logo' not in my_tasks
        assert 'Still mine' in my_tasks

        week = client.get(reverse('time_week')).content.decode()
        assert 'Design the logo' in week
        assert 'Acme Build' in week
        assert '2h 00m' in week
        assert 'Secret brief' not in week
        assert 'Ship It' not in week
        assert 'Other Logger' not in week
        assert reverse('task_full_page', args=[project.pk, task.pk]) not in week
        kept.refresh_from_db()
        assert kept.assignee_id == user.id
