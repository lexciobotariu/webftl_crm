import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate GitHub webhook signature."""
    return 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


WEBHOOK_SECRET = 'test-webhook-secret'


@pytest.mark.django_db
@pytest.mark.security
class TestGitHubWebhook:
    def test_webhook_rejects_invalid_signature(self, client):
        ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256='sha256=invalid',
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 401

    def test_webhook_accepts_valid_signature(self, client):
        ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'},
            'commits': []
        }).encode()
        signature = generate_signature(payload, WEBHOOK_SECRET)
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 200

    def test_webhook_rejects_invalid_json(self, client):
        payload = b'not json'
        signature = generate_signature(payload, WEBHOOK_SECRET)
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 400

    def test_webhook_requires_repository_url(self, client):
        payload = json.dumps({'repository': {}}).encode()
        signature = generate_signature(payload, WEBHOOK_SECRET)
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 400

    def test_webhook_404_for_unknown_repo(self, client):
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/unknown/repo'}
        }).encode()
        signature = generate_signature(payload, WEBHOOK_SECRET)
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 404

    def test_webhook_404_for_disabled_sync(self, client):
        ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=False
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        signature = generate_signature(payload, WEBHOOK_SECRET)
        with override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 404

    def test_webhook_requires_secret(self, client):
        """Webhook secret must be configured — no DEBUG bypass."""
        with override_settings(GITHUB_WEBHOOK_SECRET=''):
            response = client.post(
                reverse('github_webhook'),
                '{}',
                content_type='application/json',
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 500
        assert 'secret not configured' in response.content.decode().lower()


@pytest.mark.django_db
class TestGitHubSync:
    def test_sync_requires_login(self, client):
        project = ProjectFactory()
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 302

    def test_sync_requires_access_projects(self, client):
        preset = PermissionPreset.objects.create(name='NoProjects', access_projects=False)
        user = UserFactory(permission_preset=preset, github_token='gh-token')
        project = ProjectFactory(github_repo_url='https://github.com/test/repo')
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 403

    def test_sync_requires_manager_access(self, client):
        user = UserFactory(github_token='gh-token')
        project = ProjectFactory(github_repo_url='https://github.com/test/repo')
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 403

    def test_sync_requires_github_repo(self, client):
        admin = AdminUserFactory(github_token='gh-token')
        project = ProjectFactory(github_repo_url='')
        client.force_login(admin)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'No GitHub repo' in response.json()['error']

    def test_sync_requires_github_token(self, client):
        admin = AdminUserFactory(github_token='')
        project = ProjectFactory(github_repo_url='https://github.com/test/repo')
        client.force_login(admin)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'token' in response.json()['error'].lower()


@pytest.mark.django_db
class TestIssueClosedWebhook:
    def _payload(self, task):
        return {'action': 'closed', 'issue': {'id': task.github_issue_id}}

    def test_closed_issue_moves_task_to_completed_status(self):
        from apps.integrations.github import process_webhook_issue
        from apps.tasks.factories import TaskFactory

        project = ProjectFactory()
        task = TaskFactory(project=project, github_issue_id=42)
        assert task.status.category == 'backlog'
        process_webhook_issue(self._payload(task), project)
        task.refresh_from_db()
        assert task.status.category == 'completed'

    def test_closed_issue_ignores_canceled_statuses(self):
        from apps.integrations.github import process_webhook_issue
        from apps.projects.factories import StatusFactory
        from apps.tasks.factories import TaskFactory

        project = ProjectFactory()
        project.statuses.filter(category='completed').delete()
        StatusFactory(project=project, name='Wontfix', category='canceled')
        task = TaskFactory(project=project, github_issue_id=43)
        original = task.status
        process_webhook_issue(self._payload(task), project)
        task.refresh_from_db()
        assert task.status == original
