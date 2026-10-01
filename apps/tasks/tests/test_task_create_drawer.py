import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.models import Task, TaskActivity

HTMX = {'HTTP_HX_REQUEST': 'true'}


@pytest.fixture
def setup(client):
    user = UserFactory(name='Ada Lovelace')
    project = ProjectFactory()
    ProjectAccessFactory(project=project, user=user)
    client.force_login(user)
    return user, project


def _open(client, project, query=''):
    url = reverse('task_create', args=[project.pk])
    return client.get(f'{url}?{query}' if query else url, **HTMX)


def _post(client, project, data):
    return client.post(reverse('task_create', args=[project.pk]), data, **HTMX)


@pytest.mark.django_db
class TestOpeningTheDrawer:
    def test_it_offers_every_status_with_the_opened_one_selected(self, client, setup):
        _, project = setup
        review = project.statuses.get(name='Review')

        response = _open(client, project, f'status={review.pk}')

        content = response.content.decode()
        assert response.status_code == 200
        assert response.context['selected_status'] == review
        assert f"selected: '{review.pk}'" in content
        for status in project.statuses.all():
            assert f"selected = '{status.pk}'" in content
        assert 'name="status_id"' in content

    def test_a_status_that_is_not_a_number_is_ignored(self, client, setup):
        _, project = setup

        response = _open(client, project, 'status=abc')

        assert response.status_code == 200
        assert response.context['selected_status'] == project.statuses.filter(visible_on_board=True).first()

    def test_a_status_from_another_project_is_not_found(self, client, setup):
        _, project = setup
        foreign = ProjectFactory().statuses.first()

        assert _open(client, project, f'status={foreign.pk}').status_code == 404

    def test_assignee_and_priority_prefill_the_form(self, client, setup):
        user, project = setup

        response = _open(client, project, f'assignee={user.pk}&priority=high')

        content = response.content.decode()
        assert response.context['form']['assignee'].value() == user.pk
        assert response.context['form']['priority'].value() == 'high'
        assert response.context['selected_assignee'] == user
        assert "selectedName: 'Ada Lovelace'" in content
        assert "selected: 'high'" in content

    def test_a_bad_assignee_or_priority_is_ignored(self, client, setup):
        _, project = setup
        outsider = UserFactory()

        for query in (
            'assignee=abc&priority=whenever',
            f'assignee={outsider.pk}&priority=',
            'assignee=999999',
        ):
            response = _open(client, project, query)
            assert response.status_code == 200
            assert response.context['form']['assignee'].value() is None
            assert not response.context['form']['priority'].value()
            assert response.context['selected_assignee'] is None

    def test_the_drawer_has_the_fast_entry_hooks(self, client, setup):
        _, project = setup

        content = _open(client, project).content.decode()

        assert 'hx-sync="this:drop"' in content
        assert '@keydown.ctrl.enter' in content
        assert '@keydown.meta.enter' in content
        assert 'name="create_more"' in content
        assert "localStorage.getItem('taskCreateMore')" in content
        assert 'input[name="title"]' in content

    def test_someone_who_cannot_create_gets_403(self, client):
        preset = PermissionPreset.objects.create(
            name='NoCreate', access_dashboard=True, access_projects=True, access_tasks=True,
        )
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)

        assert _open(client, project).status_code == 403


@pytest.mark.django_db
class TestSubmitting:
    def test_the_chosen_status_is_used(self, client, setup):
        _, project = setup
        review = project.statuses.get(name='Review')

        response = _post(client, project, {'title': 'Ship it', 'status_id': review.pk})

        assert response.status_code == 200
        assert Task.objects.get(title='Ship it').status == review
        assert 'closeSlideOver' in response['HX-Trigger']

    def test_a_status_id_that_is_not_a_number_is_a_400_not_a_crash(self, client, setup):
        _, project = setup

        response = _post(client, project, {'title': 'Nope', 'status_id': 'abc'})

        assert response.status_code == 400
        assert not Task.objects.filter(title='Nope').exists()

    def test_create_more_keeps_the_drawer_open_on_a_fresh_form(self, client, setup):
        user, project = setup
        review = project.statuses.get(name='Review')

        response = _post(client, project, {
            'title': 'First', 'status_id': review.pk, 'priority': 'high', 'create_more': '1',
        })

        content = response.content.decode()
        assert response.status_code == 200
        assert response['HX-Trigger'] == 'taskStatusChanged'
        assert 'closeSlideOver' not in response['HX-Trigger']
        assert 'Created' in content and 'First' in content
        assert response.context['selected_status'] == review
        assert not response.context['form'].is_bound
        assert Task.objects.get(title='First').priority == 'high'
        assert TaskActivity.objects.filter(task__title='First', user=user).exists()

    def test_create_more_escapes_the_title_it_echoes(self, client, setup):
        _, project = setup

        content = _post(client, project, {
            'title': '<script>alert(1)</script>', 'create_more': '1',
        }).content.decode()

        assert '<script>alert(1)</script>' not in content
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in content

    def test_an_invalid_form_keeps_the_choices_and_creates_nothing(self, client, setup):
        user, project = setup
        review = project.statuses.get(name='Review')

        response = _post(client, project, {
            'title': '', 'status_id': review.pk, 'assignee': user.pk, 'create_more': '1',
        })

        assert response.status_code == 200
        assert Task.objects.count() == 0
        assert response.context['selected_status'] == review
        assert response.context['selected_assignee'] == user


@pytest.mark.django_db
class TestGroupPlus:
    def _page(self, client, project, group):
        url = reverse('project_tasks', args=[project.pk]) + f'?layout=list&group={group}'
        return client.get(url).content.decode()

    def test_status_groups_open_the_drawer_in_that_status(self, client, setup):
        from apps.tasks.factories import TaskFactory

        _, project = setup
        status = project.statuses.get(name='Review')
        TaskFactory(project=project, status=status)
        create = reverse('task_create', args=[project.pk])

        content = self._page(client, project, 'status')

        assert f'hx-get="{create}?status={status.pk}"' in content

    def test_priority_and_assignee_groups_carry_their_value(self, client, setup):
        from apps.tasks.factories import TaskFactory

        user, project = setup
        TaskFactory(project=project, priority='urgent', assignee=user)
        TaskFactory(project=project, priority='', assignee=None)
        create = reverse('task_create', args=[project.pk])

        by_priority = self._page(client, project, 'priority')
        by_assignee = self._page(client, project, 'assignee')

        assert f'hx-get="{create}?priority=urgent"' in by_priority
        assert f'hx-get="{create}"' in by_priority  # the "no priority" group has no value to carry
        assert f'hx-get="{create}?assignee={user.pk}"' in by_assignee
        assert f'hx-get="{create}"' in by_assignee

    def test_ungrouped_lists_and_viewers_get_no_plus(self, client, setup):
        from apps.tasks.factories import TaskFactory

        user, project = setup
        TaskFactory(project=project, assignee=user)

        # "New Task" in the page header also opens the drawer; the group "+" is titled.
        assert 'title="Add task' not in self._page(client, project, 'none')

        viewer = UserFactory(permission_preset=PermissionPreset.objects.create(
            name='Viewer', access_dashboard=True, access_projects=True,
            access_tasks=True, tasks_view_all=True,
        ))
        ProjectAccessFactory(project=project, user=viewer)
        client.force_login(viewer)
        assert 'title="Add task' not in self._page(client, project, 'status')

    def test_my_tasks_groups_have_no_plus(self, client, setup):
        from apps.tasks.factories import TaskFactory

        user, project = setup
        TaskFactory(project=project, assignee=user)

        content = client.get(reverse('my_tasks') + '?group=status').content.decode()

        assert 'title="Add task' not in content
