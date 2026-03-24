from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class ChangelogViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@test.com', password='test', name='Test User', role='member'
        )

    def test_requires_login(self):
        response = self.client.get('/changelog/')
        self.assertEqual(response.status_code, 302)

    def test_returns_200_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        self.assertEqual(response.status_code, 200)

    def test_contains_version_entries(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        # The real CHANGELOG.md has at least v0.1.0
        self.assertContains(response, '0.1.0')

    def test_uses_correct_template(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        self.assertTemplateUsed(response, 'changelog.html')
