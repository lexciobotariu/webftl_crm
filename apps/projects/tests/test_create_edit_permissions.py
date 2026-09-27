from datetime import datetime, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project, ProjectAccess
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import TaskActivity
from apps.tasks.services import entries_for_week, entries_on_task


def _preset(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'access_tasks': True,
        'clients_view_all': True,
        'projects_view_all': False,
        'projects_create': False,
        'projects_edit_own': False,
        'projects_edit_all': False,
    }
    fields.update(overrides)
    return PermissionPreset.objects.create(name=name, **fields)


def _user(name, **overrides):
    return UserFactory(permission_preset=_preset(name, **overrides))


def _monday():
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    return monday, timezone.make_aware(datetime.combine(monday, time.min))


@pytest.mark.django_db
class TestCreateFlag:
    def test_off_forbids_create_and_hides_the_buttons(self, client):
        user = _user('NoCreate')
        client_obj = ClientFactory(name='Button Client')
        project = ProjectFactory(client=client_obj, name='Visible Project')
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)

        listing = client.get(reverse('project_list'))
        assert listing.status_code == 200
        list_html = listing.content.decode()
        assert 'Add Project' not in list_html
        assert reverse('project_create') not in list_html

        on_client = client.get(reverse('client_detail_projects', args=[client_obj.pk]))
        assert on_client.status_code == 200
        client_html = on_client.content.decode()
        assert 'Add Project' not in client_html
        assert reverse('client_create_project', args=[client_obj.pk]) not in client_html

        assert client.get(reverse('project_create')).status_code == 403
        assert client.post(reverse('project_create'), {
            'client': client_obj.pk,
            'name': 'Should Not Land',
            'description': '',
            'github_repo_url': '',
        }).status_code == 403
        assert client.post(reverse('client_create_project', args=[client_obj.pk]), {
            'name': 'Should Not Land',
            'description': '',
            'github_repo_url': '',
        }).status_code == 403
        assert not Project.objects.filter(name='Should Not Land').exists()

    def test_on_creates_and_the_row_does_not_grant_settings(self, client):
        user = _user('Creators', projects_create=True)
        client_obj = ClientFactory()
        client.force_login(user)

        created = client.post(reverse('project_create'), {
            'client': client_obj.pk,
            'name': 'From List',
            'description': 'Listed',
            'github_repo_url': '',
        })
        assert created.status_code == 302
        listed = Project.objects.get(name='From List')
        assert ProjectAccess.objects.filter(project=listed, user=user).exists()

        from_client = client.post(reverse('client_create_project', args=[client_obj.pk]), {
            'name': 'From Client',
            'description': '',
            'github_repo_url': '',
        })
        assert from_client.status_code == 200
        made = Project.objects.get(name='From Client')
        assert ProjectAccess.objects.filter(project=made, user=user).exists()

        list_html = client.get(reverse('project_list')).content.decode()
        assert 'Add Project' in list_html
        client_html = client.get(
            reverse('client_detail_projects', args=[client_obj.pk])
        ).content.decode()
        assert 'Add Project' in client_html

        assert client.get(reverse('project_settings', args=[listed.pk])).status_code == 403
        assert client.post(reverse('project_settings_update', args=[listed.pk]), {
            'name': 'Renamed',
            'description': '',
            'github_repo_url': '',
        }).status_code == 403
        board = client.get(reverse('project_board', args=[listed.pk])).content.decode()
        detail = client.get(reverse('project_detail', args=[listed.pk])).content.decode()
        settings_url = reverse('project_settings', args=[listed.pk])
        assert settings_url not in board
        assert settings_url not in detail
        listed.refresh_from_db()
        assert listed.name == 'From List'


@pytest.mark.django_db
class TestEditFlags:
    def test_edit_own_covers_accessible_projects_only(self, client):
        user = _user('EditOwn', projects_edit_own=True, projects_edit_all=False)
        mine = ProjectFactory(name='Mine Settings')
        other = ProjectFactory(name='Other Settings')
        ProjectAccessFactory(project=mine, user=user)
        client.force_login(user)

        assert client.get(reverse('project_settings', args=[mine.pk])).status_code == 200
        updated = client.post(reverse('project_settings_update', args=[mine.pk]), {
            'name': 'Mine Renamed',
            'description': 'Updated',
            'github_repo_url': '',
        })
        assert updated.status_code == 200
        mine.refresh_from_db()
        assert mine.name == 'Mine Renamed'

        status = client.post(reverse('status_create', args=[mine.pk]), {'name': 'Queued'})
        assert status.status_code == 200
        assert mine.statuses.filter(name='Queued').exists()

        label = client.post(reverse('label_create', args=[mine.pk]), {
            'name': 'Bug',
            'color': '#ff0000',
        })
        assert label.status_code == 200
        assert mine.labels.filter(name='Bug').exists()

        settings_url = reverse('project_settings', args=[mine.pk])
        assert settings_url in client.get(reverse('project_board', args=[mine.pk])).content.decode()
        assert settings_url in client.get(reverse('project_detail', args=[mine.pk])).content.decode()
        form = client.get(reverse('project_settings', args=[mine.pk])).content.decode()
        assert 'name="name"' in form

        assert client.get(reverse('project_settings', args=[other.pk])).status_code == 403
        assert client.post(reverse('project_settings_update', args=[other.pk]), {
            'name': 'Hijacked',
            'description': '',
            'github_repo_url': '',
        }).status_code == 403
        assert client.post(reverse('status_create', args=[other.pk]), {'name': 'Nope'}).status_code == 403
        assert client.post(reverse('label_create', args=[other.pk]), {
            'name': 'Nope',
            'color': '#000000',
        }).status_code == 403
        other.refresh_from_db()
        assert other.name == 'Other Settings'
        assert not other.statuses.filter(name='Nope').exists()

    def test_edit_all_opens_and_edits_without_a_row(self, client):
        user = _user('EditAll', projects_edit_all=True, projects_edit_own=False)
        project = ProjectFactory(name='Unassigned')
        assert not ProjectAccess.objects.filter(project=project, user=user).exists()
        client.force_login(user)

        assert client.get(reverse('project_board', args=[project.pk])).status_code == 200
        assert client.get(reverse('project_detail', args=[project.pk])).status_code == 200
        assert client.get(reverse('project_settings', args=[project.pk])).status_code == 200
        updated = client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': 'Edited From Afar',
            'description': '',
            'github_repo_url': '',
        })
        assert updated.status_code == 200
        project.refresh_from_db()
        assert project.name == 'Edited From Afar'
        assert not ProjectAccess.objects.filter(project=project, user=user).exists()

    def test_view_all_opens_without_edit(self, client):
        user = _user('ViewAll', projects_view_all=True)
        project = ProjectFactory(name='Read Only')
        client.force_login(user)

        assert client.get(reverse('project_board', args=[project.pk])).status_code == 200
        assert client.get(reverse('project_detail', args=[project.pk])).status_code == 200
        assert client.get(reverse('project_settings', args=[project.pk])).status_code == 403
        assert client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': 'Changed',
            'description': '',
            'github_repo_url': '',
        }).status_code == 403
        detail = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert reverse('project_settings', args=[project.pk]) not in detail
        project.refresh_from_db()
        assert project.name == 'Read Only'

    def test_delete_stays_admin_only(self, client):
        user = _user(
            'CannotDelete',
            projects_edit_own=True,
            projects_edit_all=True,
            projects_create=True,
        )
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)

        assert client.post(reverse('project_delete', args=[project.pk])).status_code == 403
        assert Project.objects.filter(pk=project.pk).exists()
        settings = client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert 'Delete Project' not in settings
        assert reverse('project_delete', args=[project.pk]) not in settings


@pytest.mark.django_db
class TestProjectWorkStaysWithTheRow:
    def test_row_can_create_a_task_and_comment_view_all_cannot(self, client):
        worker = _user('Worker', tasks_create=True, tasks_edit_own=True)
        watcher = _user('Watcher', projects_view_all=True)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=worker)
        task = TaskFactory(project=project, title='Existing')

        client.force_login(worker)
        created = client.post(reverse('task_create', args=[project.pk]), {
            'title': 'New Task',
            'description': 'From the row',
        })
        assert created.status_code == 302
        assert project.tasks.filter(title='New Task').exists()
        comment = client.post(reverse('comment_create', args=[task.pk]), {'content': 'Still here'})
        assert comment.status_code == 200
        assert task.activities.filter(activity_type='comment', content='Still here').exists()

        client.force_login(watcher)
        denied_task = client.post(reverse('task_create', args=[project.pk]), {
            'title': 'Watcher Task',
            'description': '',
        })
        assert denied_task.status_code == 403
        denied_comment = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'Should not land'},
        )
        assert denied_comment.status_code == 403
        assert not project.tasks.filter(title='Watcher Task').exists()
        assert not TaskActivity.objects.filter(content='Should not land').exists()
        assert client.get(reverse('project_board', args=[project.pk])).status_code == 200


@pytest.mark.django_db
class TestTimeVisibility:
    def test_only_admin_sees_everyones_entries(self, client):
        owner = _user('Owner')
        colleague = _user('Colleague')
        admin = AdminUserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=owner)
        ProjectAccessFactory(project=project, user=colleague)
        task = TaskFactory(project=project, title='Shared Task')
        monday, week_start = _monday()
        from datetime import timedelta

        theirs = TimeEntryFactory(
            user=owner,
            task=task,
            note='owner-note',
            started_at=week_start + timedelta(hours=2),
            ended_at=week_start + timedelta(hours=3),
        )

        assert theirs not in list(entries_for_week(colleague, monday, project=project))
        assert theirs not in list(entries_on_task(colleague, task))
        assert theirs in list(entries_for_week(admin, monday, project=project))
        assert theirs in list(entries_on_task(admin, task))
        assert admin.role == 'admin'
        assert colleague.role != 'admin'

        client.force_login(colleague)
        week = client.get(reverse('time_week'), {'project': project.pk}).content.decode()
        assert 'owner-note' not in week
        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'owner-note' not in detail

        client.force_login(admin)
        admin_week = client.get(reverse('time_week'), {'project': project.pk}).content.decode()
        assert 'owner-note' in admin_week
        admin_detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'owner-note' in admin_detail
