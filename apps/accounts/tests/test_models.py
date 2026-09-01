import pytest

from apps.accounts.factories import AdminUserFactory, UserFactory


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = UserFactory()
        assert user.email is not None
        assert user.role == 'member'
        assert user.is_admin is False

    def test_create_admin_user(self):
        admin = AdminUserFactory()
        assert admin.role == 'admin'
        assert admin.is_admin is True

    def test_user_str(self):
        user = UserFactory(email='test@example.com')
        assert str(user) == 'test@example.com'

    def test_is_admin_property(self):
        member = UserFactory(role='member')
        admin = UserFactory(role='admin')
        assert member.is_admin is False
        assert admin.is_admin is True
