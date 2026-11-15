import pytest
from django.urls import reverse

PAGES = (
    ('settings', 'Company details'),
    ('settings_appearance', 'Appearance'),
    ('settings_bank_accounts', 'Bank accounts'),
    ('settings_currencies', 'Currencies'),
    ('settings_storage', 'File storage'),
)


def _nav(html):
    start = html.index('data-settings-nav')
    return html[start:html.index('</nav>', start)]


@pytest.mark.django_db
class TestSettingsPages:
    def test_every_section_has_its_page_with_the_grouped_sub_nav(self, client, admin_user):
        client.force_login(admin_user)
        for name, label in PAGES:
            page = client.get(reverse(name))
            assert page.status_code == 200, name
            html = page.content.decode()
            assert f"<title>{label} - WebFTL CRM</title>" in page.content.decode(), name
            nav = _nav(html)
            for group in ('Company', 'Billing', 'Integrations'):
                assert f'>{group}<' in nav
            for other, _ in PAGES:
                assert f'href="{reverse(other)}"' in nav
            current = nav[nav.index('aria-current="page"') - 400:nav.index('aria-current="page"')]
            assert f'href="{reverse(name)}"' in current, name
            # Settings stays highlighted in the main sidebar on every sub-page.
            sidebar = html[html.index('href="/settings/"'):]
            assert 'bg-elevated' in sidebar[:300]

    def test_bank_account_form_sits_in_the_billing_section(self, client, admin_user):
        client.force_login(admin_user)
        nav = _nav(client.get(reverse('bank_account_add')).content.decode())
        current = nav[nav.index('aria-current="page"') - 400:nav.index('aria-current="page"')]
        assert f'href="{reverse("settings_bank_accounts")}"' in current

    def test_saving_shows_a_saved_message_once(self, client, admin_user):
        client.force_login(admin_user)
        saved = client.post(reverse('settings_appearance'), {'theme': 'light'}, follow=True)
        assert 'Appearance saved.' in saved.content.decode()
        assert 'Appearance saved.' not in client.get(reverse('settings_appearance')).content.decode()

    def test_old_single_page_anchors_point_to_the_new_pages(self, client, admin_user):
        client.force_login(admin_user)
        html = client.get(reverse('settings')).content.decode()
        assert f"'#storage': '{reverse('settings_storage')}'" in html
        assert f"'#bank-accounts': '{reverse('settings_bank_accounts')}'" in html

    def test_members_get_403_on_every_page(self, client, user):
        client.force_login(user)
        for name, _ in PAGES:
            assert client.get(reverse(name)).status_code == 403, name
