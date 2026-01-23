# apps/tasks/tests/test_services.py
import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory
from apps.tasks import services


@pytest.mark.django_db
class TestPermissions:
    def test_require_access_raises_for_non_member(self):
        user = UserFactory()
        project = ProjectFactory()
        # No membership created

        with pytest.raises(PermissionDenied) as exc_info:
            services.require_access(user, project, 'editor')

        assert 'Editor access required' in str(exc_info.value)

    def test_require_access_passes_for_editor(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')

        # Should not raise
        services.require_access(user, project, 'editor')

    def test_require_access_passes_for_admin(self):
        from apps.accounts.factories import AdminUserFactory
        admin = AdminUserFactory()
        project = ProjectFactory()
        # No membership needed for admin

        # Should not raise
        services.require_access(admin, project, 'manager')
