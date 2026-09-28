import importlib

import pytest
from django.apps import apps as django_apps
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
        company = Company.objects.get()
        assert company.legal_name == ''
        assert company.theme == 'dark'
        assert Currency.objects.count() == 4

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
            'code': 'chf',
            'name': 'Swiss Franc',
            'symbol': 'Fr',
            'symbol_before': 'before',
        })
        assert added.status_code == 302
        currency = Currency.objects.get(code='CHF')
        assert currency.name == 'Swiss Franc'
        assert currency.symbol == 'Fr'
        assert currency.symbol_before is True

        listed = client.get(reverse('settings')).content.decode()
        assert 'Harbor Studio LLC' in listed
        assert 'CHF' in listed
        assert 'Swiss Franc' in listed
        assert 'EUR' in listed
        assert 'Euro' in listed


@pytest.mark.django_db
class TestCurrencyDelete:
    def test_a_used_currency_cannot_be_deleted_and_an_unused_one_can(self, client, admin_user):
        used = Currency.objects.get(code='USD')
        unused = Currency.objects.get(code='EUR')
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
        currency = Currency.objects.create(code='cad', name='Canadian Dollar', symbol='CA$')
        assert currency.code == 'CAD'

        with pytest.raises(ValidationError):
            Currency.objects.create(code='US', name='Short', symbol='$')
        with pytest.raises(ValidationError):
            Currency.objects.create(code='US1', name='Digits', symbol='$')

        currency.code = 'EUR'
        with pytest.raises(ValidationError):
            currency.save()
        currency.refresh_from_db()
        assert currency.code == 'CAD'

        currency.name = 'Dollar'
        currency.symbol = 'CA$'
        currency.save()
        currency.refresh_from_db()
        assert currency.code == 'CAD'
        assert currency.name == 'Dollar'
        assert currency.symbol == 'CA$'


def _seed_currencies():
    migration = importlib.import_module('apps.crm.migrations.0002_currency_symbol_before')
    migration.seed_currencies(django_apps, None)


def _form_around(html, marker):
    start = html.rfind('<form', 0, html.index(marker))
    return html[start:html.index('</form>', start)]


def _currency_row(html, code):
    marker = f'>{code}<'
    for row in html.split('<tr'):
        if marker in row:
            return row
    raise AssertionError(f'{code} is not listed')


@pytest.mark.django_db
class TestCurrencySeed:
    def test_the_four_seeds_exist_once_when_the_migration_runs_twice(self):
        Currency.objects.all().delete()
        _seed_currencies()
        _seed_currencies()

        assert Currency.objects.count() == 4
        expected = {
            'EUR': ('Euro', '€', False),
            'GBP': ('British Pound', '£', True),
            'USD': ('US Dollar', '$', True),
            'RON': ('Romanian Leu', 'lei', False),
        }
        for code, (name, symbol, symbol_before) in expected.items():
            currency = Currency.objects.get(code=code)
            assert currency.name == name
            assert currency.symbol == symbol
            assert currency.symbol_before is symbol_before

        euro = Currency.objects.get(code='EUR')
        euro.name = 'Old Euro'
        euro.symbol = 'E'
        euro.symbol_before = True
        euro.save()
        _seed_currencies()
        euro.refresh_from_db()
        assert Currency.objects.filter(code='EUR').count() == 1
        assert euro.name == 'Old Euro'
        assert euro.symbol == 'E'
        assert euro.symbol_before is True
        assert Currency.objects.count() == 4


@pytest.mark.django_db
class TestCurrencySymbolPosition:
    def test_the_add_form_chooses_before_or_after_and_seeds_show_theirs(
        self, client, admin_user
    ):
        client.force_login(admin_user)
        page = client.get(reverse('settings')).content.decode()
        assert 'name="symbol_before"' in page
        assert 'Before the amount' in page
        assert 'After the amount' in page
        assert '>After<' in _currency_row(page, 'EUR')
        assert '>After<' in _currency_row(page, 'RON')
        assert '>Before<' in _currency_row(page, 'GBP')
        assert '>Before<' in _currency_row(page, 'USD')

        added = client.post(reverse('currency_add'), {
            'code': 'chf',
            'name': 'Swiss Franc',
            'symbol': 'Fr',
            'symbol_before': 'after',
        })
        assert added.status_code == 302
        franc = Currency.objects.get(code='CHF')
        assert franc.symbol_before is False

        listed = client.get(reverse('settings')).content.decode()
        assert '>After<' in _currency_row(listed, 'CHF')


@pytest.mark.django_db
class TestTheme:
    def test_default_theme_is_dark_including_logged_out_login(self, client):
        assert Company.load().theme == 'dark'
        login = client.get(reverse('account_login'))
        assert login.status_code == 200
        assert 'class="dark h-full"' in login.content.decode()

    def test_admin_saves_light_and_later_pages_including_login_use_it(
        self, client, admin_user
    ):
        company = Company.load()
        company.legal_name = 'Harbor Studio LLC'
        company.save(update_fields=['legal_name'])
        client.force_login(admin_user)

        page = client.get(reverse('settings'))
        html = page.content.decode()
        assert page.status_code == 200
        assert 'Appearance' in html
        assert 'value="dark"' in html
        assert 'value="light"' in html
        assert 'class="dark h-full"' in html
        company_form = _form_around(html, 'Save company')
        appearance_form = _form_around(html, 'Save appearance')
        assert 'name="legal_name"' in company_form
        assert 'name="theme"' not in company_form
        assert 'name="theme"' in appearance_form
        assert 'name="legal_name"' not in appearance_form

        saved = client.post(reverse('settings'), {'theme': 'light'})
        assert saved.status_code == 302
        assert saved.url == reverse('settings')
        company.refresh_from_db()
        assert company.theme == 'light'
        assert company.legal_name == 'Harbor Studio LLC'

        again = client.get(reverse('dashboard'))
        assert 'class="light h-full"' in again.content.decode()

        client.logout()
        login = client.get(reverse('account_login'))
        assert login.status_code == 200
        assert 'class="light h-full"' in login.content.decode()

    def test_member_gets_403_on_settings(self, client, user):
        client.force_login(user)
        assert client.get(reverse('settings')).status_code == 403
        refused = client.post(reverse('settings'), {'theme': 'light'})
        assert refused.status_code == 403
        assert not Company.objects.filter(theme='light').exists()

    def test_saving_the_company_does_not_change_the_theme(self, client, admin_user):
        company = Company.load()
        company.theme = 'light'
        company.save(update_fields=['theme'])
        client.force_login(admin_user)

        saved = client.post(reverse('settings'), {
            'legal_name': 'Harbor Studio LLC',
            'address': '4 Quay Street',
            'email': 'billing@harbor.test',
            'phone': '555-0100',
            'tax_id': 'VAT-1',
        })
        assert saved.status_code == 302
        company.refresh_from_db()
        assert company.legal_name == 'Harbor Studio LLC'
        assert company.address == '4 Quay Street'
        assert company.email == 'billing@harbor.test'
        assert company.phone == '555-0100'
        assert company.tax_id == 'VAT-1'
        assert company.theme == 'light'
