import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.clients.models import Client
from apps.crm.models import Currency


def _currency(code, symbol, name):
    currency, _created = Currency.objects.get_or_create(
        code=code,
        defaults={'name': name, 'symbol': symbol},
    )
    return currency


@pytest.mark.django_db
class TestClientCurrency:
    def test_first_save_stores_the_currency_and_a_second_save_cannot_change_it(self, client):
        usd = _currency('USD', '$', 'US Dollar')
        eur = _currency('EUR', '€', 'Euro')
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('client_create'), {
            'name': 'Locked Client',
            'email': 'locked@client.test',
            'phone': '',
            'address': '',
            'notes': '',
            'billing_name': '',
            'billing_email': '',
            'tax_id': '',
            'currency': usd.pk,
        })
        assert created.status_code == 302
        saved = Client.objects.get(name='Locked Client')
        assert saved.currency_id == usd.pk

        edit_html = client.get(reverse('client_edit', args=[saved.pk])).content.decode()
        assert 'name="currency"' not in edit_html
        assert 'USD $' in edit_html

        changed = client.post(reverse('client_edit', args=[saved.pk]), {
            'name': 'Locked Client',
            'email': 'locked@client.test',
            'phone': '',
            'address': '',
            'notes': '',
            'billing_name': '',
            'billing_email': '',
            'tax_id': '',
            'currency': eur.pk,
        })
        assert changed.status_code == 302
        saved.refresh_from_db()
        assert saved.currency_id == usd.pk

        drawer_html = client.get(reverse('client_edit_drawer', args=[saved.pk])).content.decode()
        assert 'name="currency"' not in drawer_html
        assert 'USD $' in drawer_html
        drawer = client.post(reverse('client_edit_drawer', args=[saved.pk]), {
            'name': 'Locked Client',
            'email': 'locked@client.test',
            'phone': '',
            'address': '',
            'billing_name': '',
            'billing_email': '',
            'tax_id': '',
            'currency': eur.pk,
        })
        assert drawer.status_code == 200
        saved.refresh_from_db()
        assert saved.currency_id == usd.pk

        profile = client.get(reverse('client_detail_profile', args=[saved.pk])).content.decode()
        billing = profile.split('>Billing</h2>', 1)[1].split('>Notes</h2>', 1)[0]
        assert 'USD $' in billing

    def test_an_existing_client_without_a_currency_can_choose_one(self, client):
        usd = _currency('USD', '$', 'US Dollar')
        admin = AdminUserFactory()
        existing = ClientFactory(name='Waiting Client')
        client.force_login(admin)

        edit_html = client.get(reverse('client_edit', args=[existing.pk])).content.decode()
        drawer_html = client.get(
            reverse('client_edit_drawer', args=[existing.pk])
        ).content.decode()
        create_html = client.get(reverse('client_create')).content.decode()
        assert 'name="currency"' in edit_html
        assert 'name="currency"' in drawer_html
        assert 'name="currency"' in create_html
        assert 'USD' in create_html

        chosen = client.post(reverse('client_edit_drawer', args=[existing.pk]), {
            'name': 'Waiting Client',
            'email': '',
            'phone': '',
            'address': '',
            'billing_name': '',
            'billing_email': '',
            'tax_id': '',
            'currency': usd.pk,
        })
        assert chosen.status_code == 200
        existing.refresh_from_db()
        assert existing.currency_id == usd.pk
        assert existing.currency.code == 'USD'
        assert existing.currency.symbol == '$'
