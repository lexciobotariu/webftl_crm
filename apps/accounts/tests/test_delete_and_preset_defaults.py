"""People with logged time are kept, and new presets start without money modules."""
import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import User
from apps.accounts.permissions import PermissionPreset
from apps.tasks.factories import TimeEntryFactory


@pytest.mark.django_db
class TestDeleteWithLoggedTime:
    def test_a_user_with_logged_time_is_not_deleted(self, client):
        admin = AdminUserFactory()
        worker = UserFactory()
        TimeEntryFactory(user=worker)
        client.force_login(admin)

        confirm = client.get(reverse('user_delete_confirm', args=[worker.pk])).content.decode()
        assert 'has logged time' in confirm
        assert '1 time entry logged' in confirm
        assert reverse('user_delete', args=[worker.pk]) not in confirm

        response = client.post(reverse('user_delete', args=[worker.pk]))
        assert response.status_code == 400
        assert 'Deactivate' in response.content.decode()
        assert User.objects.filter(pk=worker.pk).exists()

    def test_a_user_without_logged_time_is_still_deleted(self, client):
        admin = AdminUserFactory()
        worker = UserFactory()
        client.force_login(admin)

        confirm = client.get(reverse('user_delete_confirm', args=[worker.pk])).content.decode()
        assert reverse('user_delete', args=[worker.pk]) in confirm
        assert client.post(reverse('user_delete', args=[worker.pk])).status_code == 200
        assert not User.objects.filter(pk=worker.pk).exists()

    def test_the_database_protects_logged_time(self):
        from django.db.models import ProtectedError

        entry = TimeEntryFactory()
        with pytest.raises(ProtectedError):
            entry.user.delete()


@pytest.mark.django_db
class TestPresetDefaults:
    def test_a_new_preset_has_no_salaries_or_invoices(self):
        preset = PermissionPreset.objects.create(name='Fresh')
        assert preset.access_salaries is False
        assert preset.access_invoices is False

    def test_existing_presets_keep_what_they_had(self):
        preset = PermissionPreset.objects.create(name='Old', access_salaries=True, access_invoices=True)
        preset.refresh_from_db()
        assert preset.access_salaries is True
        assert preset.access_invoices is True
