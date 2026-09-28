import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.clients.factories import ClientFactory
from apps.crm.models import Company, Currency


@pytest.mark.django_db
class TestSettingsAccess:
    def test_member_cannot_open_settings_and_admin_can_save_company_and_currency(
        self, client, user, admin_user
    ):
        client.force_login(user)
        assert client.get(reverse('settings')).status_code == 403
        assert client.post(reverse('settings'), {'legal_name': 'Nope'}).status_code == 403
        assert client.post(reverse('currency_add'), {
            'code': 'EUR',
            'name': 'Euro',
            'symbol': '€',
        }).status_code == 403
        member_home = client.get(reverse('dashboard')).content.decode()
        assert 'href="/settings/"' not in member_home
        assert Company.objects.count() == 0
        assert Currency.objects.count() == 0

        client.force_login(admin_user)
        admin_home = client.get(reverse('dashboard')).content.decode()
        assert 'href="/settings/"' in admin_home

        page = client.get(reverse('settings'))
        assert page.status_code == 200
        assert Company.objects.count() == 1
        assert Company.load().legal_name == ''

        saved = client.post(reverse('settings'), {
            'legal_name': 'Harbor Studio LLC',
            'address': '4 Quay Street',
            'email': 'billing@harbor.test',
            'phone': '555-0100',
            'tax_id': 'VAT-1',
        })
        assert saved.status_code == 302
        assert saved.url == reverse('settings')
        company = Company.load()
        assert company.legal_name == 'Harbor Studio LLC'
        assert company.address == '4 Quay Street'
        assert company.email == 'billing@harbor.test'
        assert company.phone == '555-0100'
        assert company.tax_id == 'VAT-1'
        assert Company.objects.count() == 1

        added = client.post(reverse('currency_add'), {
            'code': 'eur',
            'name': 'Euro',
            'symbol': '€',
        })
        assert added.status_code == 302
        currency = Currency.objects.get()
        assert currency.code == 'EUR'
        assert currency.name == 'Euro'
        assert currency.symbol == '€'

        listed = client.get(reverse('settings')).content.decode()
        assert 'Harbor Studio LLC' in listed
        assert 'EUR' in listed
        assert 'Euro' in listed


@pytest.mark.django_db
class TestCurrencyDelete:
    def test_a_used_currency_cannot_be_deleted_and_an_unused_one_can(self, client, admin_user):
        used = Currency.objects.create(code='USD', name='US Dollar', symbol='$')
        unused = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        ClientFactory(currency=used)
        client.force_login(admin_user)

        refused = client.post(reverse('currency_delete', args=[used.pk]))
        assert refused.status_code == 400
        assert 'used by a client' in refused.content.decode()
        assert Currency.objects.filter(pk=used.pk).exists()

        removed = client.post(reverse('currency_delete', args=[unused.pk]))
        assert removed.status_code == 302
        assert not Currency.objects.filter(pk=unused.pk).exists()
        assert Currency.objects.filter(pk=used.pk).exists()


@pytest.mark.django_db
class TestCurrencyCode:
    def test_code_is_three_letters_and_cannot_change(self):
        currency = Currency.objects.create(code='usd', name='US Dollar', symbol='$')
        assert currency.code == 'USD'

        with pytest.raises(ValidationError):
            Currency.objects.create(code='US', name='Short', symbol='$')
        with pytest.raises(ValidationError):
            Currency.objects.create(code='US1', name='Digits', symbol='$')

        currency.code = 'EUR'
        with pytest.raises(ValidationError):
            currency.save()
        currency.refresh_from_db()
        assert currency.code == 'USD'

        currency.name = 'Dollar'
        currency.symbol = 'US$'
        currency.save()
        currency.refresh_from_db()
        assert currency.code == 'USD'
        assert currency.name == 'Dollar'
        assert currency.symbol == 'US$'
