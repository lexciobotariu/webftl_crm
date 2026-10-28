"""The create drawer: the status is a property and the description has Write / Preview."""
import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory
from apps.projects.factories import ProjectFactory
from apps.tasks.models import Task


@pytest.mark.django_db
class TestCreateDrawerLayout:
    def _drawer(self, client, project):
        client.force_login(AdminUserFactory())
        status = project.statuses.order_by('order').first()
        response = client.get(reverse('task_create', args=[project.pk]), {'status': status.pk},
                              HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        return response.content.decode()

    def test_the_status_is_the_first_property_not_in_the_header(self, client):
        project = ProjectFactory()
        html = self._drawer(client, project)
        header, rest = html.split('New task', 1)[1].split('Properties', 1)
        assert 'name="status_id"' not in header
        assert 'name="status_id"' in rest
        assert rest.index('State') < rest.index('Priority')

    def test_the_description_has_preview_and_says_markdown_works(self, client):
        html = self._drawer(client, ProjectFactory())
        assert 'Preview' in html
        assert 'Markdown supported' in html
        assert 'name="description"' in html

    def test_creating_keeps_the_description_and_the_chosen_status(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        status = project.statuses.order_by('order').last()
        client.post(reverse('task_create', args=[project.pk]), {
            'title': 'With text', 'description': '**bold**', 'status_id': status.pk, 'priority': '',
        }, HTTP_HX_REQUEST='true')
        task = Task.objects.get(project=project, title='With text')
        assert task.description == '**bold**'
        assert task.status == status

    def test_the_preview_pane_starts_hidden_without_alpine(self, client):
        # "Create more" swaps in a fresh drawer and htmx's settle step puts back the new
        # pane's own style after Alpine has hidden it: the pane must be hidden by itself.
        html = self._drawer(client, ProjectFactory())
        pane = html.split('id="task-form-description-preview"', 1)[1].split('>', 1)[0]
        assert 'style="display: none"' in pane
