import re

import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import TaskFactory


def _viewer():
    preset = PermissionPreset.objects.create(
        name='Viewer',
        access_dashboard=True,
        access_projects=True,
        access_tasks=True,
        tasks_view_all=True,
    )
    return UserFactory(permission_preset=preset)


# With DEBUG off the static file gets a content hash in its name.
TASK_VIEW_SCRIPT = re.compile(r'js/task-view(\.[0-9a-f]+)?\.js')


def _page(client, user, project, layout='list'):
    client.force_login(user)
    return client.get(reverse('project_tasks', args=[project.pk]) + f'?layout={layout}').content.decode()


@pytest.mark.django_db
class TestShortcutsMarkup:
    def test_an_editor_gets_the_script_the_help_and_every_shortcut(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project)

        content = _page(client, user, project)

        assert TASK_VIEW_SCRIPT.search(content)
        assert content.count('id="shortcuts"') == 1
        for what in ('Change status', 'Change priority', 'Change assignee', 'New task', 'Search'):
            assert what in content
        assert 'id="task-new"' in content
        assert 'title="New task (C)"' in content and 'title="Search (/)"' in content

    def test_a_viewer_gets_the_list_but_no_edit_controls(self, client):
        viewer = _viewer()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=viewer)
        TaskFactory(project=project)

        content = _page(client, viewer, project)

        assert TASK_VIEW_SCRIPT.search(content)
        # The list is the same for everyone and says the editing keys need edit rights.
        assert 'id="shortcuts"' in content
        assert 'Move the selection' in content
        assert 'work for people who can edit the task' in content
        assert 'id="task-new"' not in content
        assert 'id="task-quick-menu"' not in content

    def test_my_tasks_has_the_help_but_no_create_shortcut(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, assignee=user)
        client.force_login(user)

        content = client.get(reverse('my_tasks') + '?group=none').content.decode()

        assert 'id="shortcuts"' in content
        assert 'Change status' in content
        assert 'id="task-new"' not in content

    def test_cards_and_rows_carry_what_the_keys_need(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project)

        board = _page(client, user, project, layout='board')
        rows = _page(client, user, project, layout='list')

        detail = reverse('task_detail', args=[task.pk])
        assert f'data-task-row data-detail-url="{detail}"' in board
        assert f'hx-get="{detail}"' in rows
        assert 'id="kanban-board-content"' in board


@pytest.mark.django_db
class TestShortcutsEverywhere:
    def test_every_signed_in_page_has_the_one_list_and_the_sidebar_button(self, client):
        user = UserFactory()
        client.force_login(user)
        for name in ('dashboard', 'inbox'):
            html = client.get(reverse(name)).content.decode()
            assert html.count('id="shortcuts"') == 1, name
            assert 'window.showShortcuts()' in html, name
            for scope in ('tasks', 'inbox', 'writing', 'everywhere'):
                assert f'data-shortcuts-scope="{scope}"' in html, name

    def test_the_login_page_has_none(self, client):
        html = client.get(reverse('account_login')).content.decode()
        assert 'id="shortcuts"' not in html
