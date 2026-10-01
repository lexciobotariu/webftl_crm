import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectAccessFactory
from apps.tasks.factories import TaskFactory
from apps.tasks.forms import TaskForm
from apps.tasks.models import Task

HTMX = {'HTTP_HX_REQUEST': 'true'}


@pytest.fixture
def editor(client):
    user = UserFactory()
    task = TaskFactory()
    ProjectAccessFactory(project=task.project, user=user)
    client.force_login(user)
    return user, task


def _post_form(task, **overrides):
    data = {
        'title': task.title,
        'description': task.description or '',
        'priority': task.priority,
        'estimate': '',
    }
    data.update(overrides)
    return TaskForm(task.project, data, instance=task)


@pytest.mark.django_db
class TestTaskFormEstimate:
    def test_it_shows_the_stored_minutes_as_text(self):
        task = TaskFactory(estimate_minutes=240)
        assert TaskForm(task.project, instance=task)['estimate'].value() == '4h'

    def test_saving_the_untouched_form_keeps_the_estimate(self):
        task = TaskFactory(estimate_minutes=240)
        shown = TaskForm(task.project, instance=task)['estimate'].value()

        form = _post_form(task, estimate=shown)
        assert form.is_valid(), form.errors
        form.save()

        task.refresh_from_db()
        assert task.estimate_minutes == 240

    @pytest.mark.parametrize('text, minutes', [('1h 30m', 90), ('2', 120), ('0:45', 45), ('', None)])
    def test_it_parses_what_was_typed(self, text, minutes):
        task = TaskFactory(estimate_minutes=30)
        form = _post_form(task, estimate=text)
        assert form.is_valid(), form.errors
        form.save()
        task.refresh_from_db()
        assert task.estimate_minutes == minutes

    def test_it_refuses_nonsense_and_names_the_field(self):
        task = TaskFactory(estimate_minutes=30)
        form = _post_form(task, estimate='soon')
        assert not form.is_valid()
        assert 'estimate' in form.errors


@pytest.mark.django_db
class TestUpdateEstimateView:
    def _post(self, client, task, value):
        return client.post(reverse('task_update_estimate', args=[task.pk]), {'estimate': value}, **HTMX)

    def test_it_stores_minutes_and_shows_the_new_label(self, client, editor):
        _, task = editor
        response = self._post(client, task, '1h 30m')

        task.refresh_from_db()
        assert task.estimate_minutes == 90
        assert response.status_code == 200
        assert '1h 30m' in response.content.decode()
        assert 'activityUpdated' in response['HX-Trigger']

    def test_a_bare_number_is_hours(self, client, editor):
        _, task = editor
        self._post(client, task, '4')
        task.refresh_from_db()
        assert task.estimate_minutes == 240

    def test_an_empty_value_clears_it(self, client, editor):
        _, task = editor
        Task.objects.filter(pk=task.pk).update(estimate_minutes=60)
        self._post(client, task, '')
        task.refresh_from_db()
        assert task.estimate_minutes is None

    def test_a_wrong_value_keeps_the_old_one_and_gets_a_message_with_the_popover_open(self, client, editor):
        _, task = editor
        Task.objects.filter(pk=task.pk).update(estimate_minutes=60)

        response = self._post(client, task, '1d')

        task.refresh_from_db()
        assert task.estimate_minutes == 60
        assert response.status_code == 200
        html = response.content.decode()
        assert 'Use hours and minutes' in html
        assert 'x-init="open = true"' in html
        assert 'HX-Trigger' not in response

    def test_the_activity_row_uses_the_duration_format(self, client, editor):
        _, task = editor
        self._post(client, task, '90m')
        row = task.activities.get(activity_type='estimate_change')
        assert (row.old_value, row.new_value) == ('', '1h 30m')
        assert row.content == 'set the estimate to 1h 30m'


@pytest.mark.django_db
class TestCreateDrawerEstimate:
    def _url(self, task):
        return reverse('task_create', args=[task.project.pk])

    def test_the_drawer_creates_a_task_with_the_typed_estimate(self, client, editor):
        _, task = editor
        client.post(self._url(task), {'title': 'New one', 'estimate': '45m'}, **HTMX)
        assert Task.objects.get(title='New one').estimate_minutes == 45

    def test_a_wrong_estimate_shows_its_error_in_the_drawer(self, client, editor):
        _, task = editor
        response = client.post(self._url(task), {'title': 'New one', 'estimate': '??'}, **HTMX)
        assert not Task.objects.filter(title='New one').exists()
        assert 'Use hours and minutes' in response.content.decode()

    def test_the_typed_value_comes_back_without_going_through_a_js_string(self, client, editor):
        _, task = editor
        response = client.post(
            self._url(task), {'title': 'New one', 'estimate': "x'};alert(1)//"}, **HTMX
        )
        html = response.content.decode()
        # The value lives in an escaped input, not in an x-data string.
        assert "x'};alert(1)//" not in html
        assert 'estimate:' not in html
        assert 'x-data="dropdown"' in html
