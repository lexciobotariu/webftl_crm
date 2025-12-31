import pytest
import json
import hashlib
import hmac
from django.urls import reverse
from django.test import override_settings
from apps.projects.factories import ProjectFactory
from apps.accounts.factories import UserFactory


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate GitHub webhook signature."""
    return 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


@pytest.mark.django_db
@pytest.mark.security
class TestGitHubWebhook:
    def test_webhook_rejects_invalid_signature(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        with override_settings(GITHUB_WEBHOOK_SECRET='secret'):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256='sha256=invalid',
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 401

    def test_webhook_accepts_valid_signature(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'},
            'commits': []
        }).encode()
        secret = 'test-secret'
        signature = generate_signature(payload, secret)
        with override_settings(GITHUB_WEBHOOK_SECRET=secret):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 200

    def test_webhook_rejects_invalid_json(self, client):
        response = client.post(
            reverse('github_webhook'),
            'not json',
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 400

    def test_webhook_requires_repository_url(self, client):
        payload = json.dumps({'repository': {}}).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 400

    def test_webhook_404_for_unknown_repo(self, client):
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/unknown/repo'}
        }).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 404

    def test_webhook_404_for_disabled_sync(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=False
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestGitHubSync:
    def test_sync_requires_login(self, client):
        project = ProjectFactory()
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 302

    def test_sync_requires_github_repo(self, client):
        user = UserFactory()
        project = ProjectFactory(github_repo_url='')
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'No GitHub repo' in response.json()['error']

    def test_sync_requires_github_token(self, client):
        user = UserFactory(github_token='')
        project = ProjectFactory(github_repo_url='https://github.com/test/repo')
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'token' in response.json()['error'].lower()
