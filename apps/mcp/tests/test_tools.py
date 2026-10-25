"""Each tool, called through /mcp the way Claude calls it."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory, TimeEntryFactory
from apps.tasks.models import Task, TaskActivity, TimeEntry

from .conftest import McpClient, make_token

pytestmark = pytest.mark.django_db


def ok(result):
    assert result['isError'] is False, result['content'][0]['text']
    return result['structuredContent']


def refused(result):
    assert result['isError'] is True
    return result['content'][0]['text']


class TestReading:
    def test_list_projects_shows_only_mine_and_open(self, mcp, project, member):
        ProjectFactory(name='Someone else')
        finished = ProjectFactory(status=Project.FINISHED)
        ProjectAccessFactory(project=finished, user=member)

        keys = [row['key'] for row in ok(mcp.call('list_projects'))['projects']]
        assert keys == [project.key]
        keys = [row['key'] for row in ok(mcp.call('list_projects', include_closed=True))['projects']]
        assert set(keys) == {project.key, finished.key}

    def test_get_project_lists_statuses_labels_people(self, mcp, project, member):
        LabelFactory(project=project, name='Bug')
        data = ok(mcp.call('get_project', project=project.key.lower()))
        assert [s['name'] for s in data['statuses']][:3] == ['Backlog', 'To Do', 'In Progress']
        assert data['labels'] == [{'name': 'Bug', 'color': '#6366f1'}]
        assert member.email in [p['email'] for p in data['people']]

    def test_project_i_cannot_see_is_refused(self, mcp):
        assert 'No project' in refused(mcp.call('get_project', project=ProjectFactory().key))

    def test_search_tasks(self, mcp, project, member):
        mine = TaskFactory(project=project, title='Fix the login form', assignee=member)
        TaskFactory(project=project, title='Write docs')
        done = TaskFactory(project=project, title='Fix logo', status=project.statuses.get(name='Done'))
        TaskFactory(title='Fix invisible')  # another project

        ids = [t['id'] for t in ok(mcp.call('search_tasks', text='fix'))['tasks']]
        assert ids == [mine.identifier]
        ids = {t['id'] for t in ok(mcp.call('search_tasks', text='fix', include_closed=True))['tasks']}
        assert ids == {mine.identifier, done.identifier}
        ids = [t['id'] for t in ok(mcp.call('search_tasks', assignee='me'))['tasks']]
        assert ids == [mine.identifier]

    def test_search_limit_and_more(self, mcp, project):
        for _ in range(3):
            TaskFactory(project=project)
        data = ok(mcp.call('search_tasks', limit=2))
        assert len(data['tasks']) == 2 and data['more'] is True

    def test_get_task(self, mcp, project, member):
        task = TaskFactory(project=project, estimate_minutes=90)
        SubtaskFactory(task=task, title='Step one')
        TaskActivity.objects.create(task=task, user=member, activity_type='comment', content='Looks good')

        data = ok(mcp.call('get_task', task=task.identifier))
        assert data['id'] == task.identifier
        assert data['estimate'] == '1h 30m'
        assert data['subtasks'][0]['title'] == 'Step one'
        assert data['recent_comments'][-1]['text'] == 'Looks good'
        assert data['url'].endswith(f'/tasks/project/{project.pk}/{task.pk}/')

    def test_get_task_i_cannot_see(self, mcp):
        assert 'No task' in refused(mcp.call('get_task', task=TaskFactory().identifier))

    def test_my_timer(self, mcp, project, member):
        task = TaskFactory(project=project)
        TimeEntryFactory(task=task, user=member, running=True)
        data = ok(mcp.call('my_timer'))
        assert data['running']['task'] == task.identifier


class TestWriting:
    def test_create_task_with_everything(self, mcp, project, member):
        LabelFactory(project=project, name='Bug')
        data = ok(mcp.call(
            'create_task', project=project.key, title='New thing', status='In Progress',
            assignee='me', priority='high', due_date='2026-12-01', estimate='2h',
            billable=False, labels=['bug'], description='**Bold**',
        ))
        task = Task.objects.get(project=project, number=int(data['id'].split('-')[1]))
        assert (task.status.name, task.assignee, task.priority) == ('In Progress', member, 'high')
        assert task.estimate_minutes == 120 and task.billable is False
        assert [label.name for label in task.labels.all()] == ['Bug']

    def test_create_task_with_unknown_label_explains(self, mcp, project):
        text = refused(mcp.call('create_task', project=project.key, title='x', labels=['Nope']))
        assert 'create_label' in text
        assert not Task.objects.filter(project=project).exists()

    def test_bad_arguments_are_explained(self, mcp, project):
        assert 'required' in refused(mcp.call('create_task', project=project.key))
        assert 'date' in refused(mcp.call('create_task', project=project.key, title='x', due_date='tomorrow'))
        assert 'Unknown argument' in refused(mcp.call('create_task', project=project.key, title='x', colour='red'))
        assert 'one of' in refused(mcp.call('create_task', project=project.key, title='x', priority='asap'))

    def test_update_task_and_clear_fields(self, mcp, project, member):
        task = TaskFactory(project=project, assignee=member, billable=True)
        ok(mcp.call('update_task', task=task.identifier, billable=False, assignee=None, due_date='2026-11-30'))
        task.refresh_from_db()
        assert (task.billable, task.assignee, str(task.due_date)) == (False, None, '2026-11-30')

    def test_update_with_nothing_is_refused(self, mcp, project):
        assert 'Nothing to change' in refused(mcp.call('update_task', task=TaskFactory(project=project).identifier))

    def test_move_task(self, mcp, project):
        task = TaskFactory(project=project)
        assert ok(mcp.call('move_task', task=task.identifier, status='review'))['status'] == 'Review'
        assert 'statuses' in refused(mcp.call('move_task', task=task.identifier, status='Nowhere'))

    def test_labels(self, mcp, project):
        task = TaskFactory(project=project)
        LabelFactory(project=project, name='Bug')
        assert ok(mcp.call('add_label', task=task.identifier, label='Bug'))['labels'] == ['Bug']
        assert ok(mcp.call('add_label', task=task.identifier, label='Bug'))['labels'] == ['Bug']
        assert ok(mcp.call('remove_label', task=task.identifier, label='bug'))['labels'] == []

    def test_create_label_needs_project_edit(self, mcp, project):
        assert 'edit this project' in refused(mcp.call('create_label', project=project.key, name='Urgent'))

    def test_admin_creates_label(self, client, project):
        admin = AdminUserFactory()
        data = ok(McpClient(client, make_token(admin)).call('create_label', project=project.key, name='Urgent', color='#ef4444'))
        assert data == {'project': project.key, 'name': 'Urgent', 'color': '#ef4444'}

    def test_comment_and_subtasks(self, mcp, project, member):
        task = TaskFactory(project=project)
        ok(mcp.call('add_comment', task=task.identifier, text='On it'))
        subtask = ok(mcp.call('add_subtask', task=task.identifier, title='Check mobile'))['subtask']
        assert ok(mcp.call('complete_subtask', task=task.identifier, subtask_id=subtask['id']))['subtask']['done'] is True
        assert ok(mcp.call('complete_subtask', task=task.identifier, subtask_id=subtask['id']))['subtask']['done'] is True
        assert task.subtasks.get().completed is True
        assert TaskActivity.objects.filter(task=task, activity_type='comment', user=member, content='On it').exists()

    def test_reader_without_edit_cannot_write(self, client, mcp_preset):
        mcp_preset.tasks_edit_own = False
        mcp_preset.save()
        user = UserFactory(permission_preset=mcp_preset)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project)
        text = refused(McpClient(client, make_token(user)).call('move_task', task=task.identifier, status='Done'))
        assert 'cannot edit' in text


class TestTime:
    def test_start_and_stop_timer(self, mcp, project, member):
        task = TaskFactory(project=project)
        assert ok(mcp.call('start_timer', task=task.identifier))['running']['task'] == task.identifier
        assert ok(mcp.call('stop_timer'))['stopped']['task'] == task.identifier
        assert ok(mcp.call('stop_timer'))['stopped'] is None

    def test_log_time(self, mcp, project, member):
        task = TaskFactory(project=project)
        day = (timezone.localdate() - timedelta(days=1)).isoformat()
        data = ok(mcp.call('log_time', task=task.identifier, duration='1h 15m', day=day, note='Calls'))
        assert data['logged'] == {'task': task.identifier, 'duration': '1h 15m', 'day': day, 'note': 'Calls'}
        assert 'unit' in refused(mcp.call('log_time', task=task.identifier, duration='15'))

    def test_start_and_finish_work(self, mcp, project, member):
        task = TaskFactory(project=project, status=project.statuses.get(name='To Do'))
        data = ok(mcp.call('start_work', task=task.identifier))
        assert data['task']['status'] == 'In Progress' and data['task']['assignee'] == member.email
        assert data['running']['task'] == task.identifier

        data = ok(mcp.call('finish_work', task=task.identifier))
        assert data['task']['status'] == 'Done'
        assert data['stopped']['task'] == task.identifier
        assert not TimeEntry.objects.filter(user=member, ended_at__isnull=True).exists()


class TestViaClaude:
    def test_changes_are_marked(self, mcp, project, member):
        task = TaskFactory(project=project)
        TaskActivity.objects.filter(task=task).delete()
        ok(mcp.call('start_work', task=task.identifier))
        assert set(TaskActivity.objects.filter(task=task).values_list('source', flat=True)) == {'claude'}
        assert TimeEntry.objects.get(task=task).source == 'claude'

    def test_screen_changes_are_not(self, project, member):
        from apps.tasks import services

        task = TaskFactory(project=project)
        services.update_task(task, member, priority='urgent')
        assert TaskActivity.objects.filter(task=task, activity_type='priority_change').get().source == ''

