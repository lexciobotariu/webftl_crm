import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
    yield_hotp_counters_from_time,
)
from django.core.management import call_command
from django.urls import reverse


def _code(secret):
    return format_hotp_value(hotp_value(secret, next(yield_hotp_counters_from_time())))


def _sign_in(client, person):
    """A real password sign-in, so the two-factor pages see a recent login."""
    client.post(reverse('account_login'), {'login': person.email, 'password': 'testpass123'})


@pytest.fixture
def required(settings):
    settings.REQUIRE_ADMIN_2FA = True


@pytest.mark.django_db
class TestAdminsNeedTwoFactor:
    def test_admin_without_an_app_is_sent_to_set_one_up(self, client, admin_user, required):
        _sign_in(client, admin_user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert response.url == reverse('mfa_activate_totp')

        htmx = client.get(reverse('settings'), HTTP_HX_REQUEST='true')
        assert htmx['HX-Redirect'] == reverse('mfa_activate_totp')

        page = client.get(reverse('mfa_activate_totp'))
        assert page.status_code == 200
        html = page.content.decode()
        assert 'Admins need two-factor sign-in' in html
        assert 'data:image/svg+xml;base64,' in html

        secret = client.session[SECRET_SESSION_KEY]
        response = client.post(reverse('mfa_activate_totp'), {'code': _code(secret)})
        assert response.status_code == 302
        assert response.url == reverse('mfa_view_recovery_codes')
        assert Authenticator.objects.filter(
            user=admin_user, type=Authenticator.Type.TOTP
        ).exists()
        assert Authenticator.objects.filter(
            user=admin_user, type=Authenticator.Type.RECOVERY_CODES
        ).exists()
        assert client.get(reverse('dashboard')).status_code == 200

    def test_the_key_stays_the_same_until_setup_succeeds(self, client, admin_user, required):
        _sign_in(client, admin_user)
        client.get(reverse('mfa_activate_totp'))
        secret = client.session[SECRET_SESSION_KEY]
        # A refresh, a second tab, a wrong code: the phone's key still works.
        page = client.get(reverse('mfa_activate_totp')).content.decode()
        assert secret in page
        client.post(reverse('mfa_activate_totp'), {'code': '000000'})
        assert client.session[SECRET_SESSION_KEY] == secret
        response = client.post(reverse('mfa_activate_totp'), {'code': _code(secret)})
        assert response.status_code == 302
        assert Authenticator.objects.filter(user=admin_user).exists()

    def test_the_menu_is_hidden_until_setup(self, client, admin_user, required):
        _sign_in(client, admin_user)
        page = client.get(reverse('mfa_activate_totp')).content.decode()
        assert f'href="{reverse("client_list")}"' not in page
        assert f'href="{reverse("mfa_index")}"' in page
        TOTP.activate(admin_user, generate_totp_secret())
        page = client.get(reverse('mfa_index')).content.decode()
        assert f'href="{reverse("client_list")}"' in page

    def test_a_wrong_code_turns_nothing_on(self, client, admin_user, required):
        _sign_in(client, admin_user)
        client.get(reverse('mfa_activate_totp'))
        response = client.post(reverse('mfa_activate_totp'), {'code': '000000'})
        assert response.status_code == 200
        assert not Authenticator.objects.filter(user=admin_user).exists()

    def test_members_may_skip_it(self, client, user, required):
        client.force_login(user)
        assert client.get(reverse('dashboard')).status_code == 200
        page = client.get(reverse('mfa_index')).content.decode()
        assert 'Turn on' in page

    def test_admins_cannot_turn_it_off(self, client, admin_user, user, required):
        from allauth.mfa.adapter import get_adapter

        admin_app = TOTP.activate(admin_user, generate_totp_secret()).instance
        member_app = TOTP.activate(user, generate_totp_secret()).instance
        assert get_adapter().can_delete_authenticator(admin_app) is False
        assert get_adapter().can_delete_authenticator(member_app) is True
        client.force_login(admin_user)
        assert 'Admins must keep it on.' in client.get(reverse('mfa_index')).content.decode()
        session = client.session
        session['account_authentication_records'] = []
        session.save()
        client.post(reverse('mfa_deactivate_totp'))
        assert Authenticator.objects.filter(
            user=admin_user, type=Authenticator.Type.TOTP
        ).exists()

    def test_the_rule_can_be_switched_off(self, client, admin_user, settings):
        settings.REQUIRE_ADMIN_2FA = False
        client.force_login(admin_user)
        assert client.get(reverse('dashboard')).status_code == 200


@pytest.mark.django_db
class TestSignInWithACode:
    def test_password_then_code(self, client, user):
        secret = generate_totp_secret()
        TOTP.activate(user, secret)
        response = client.post(reverse('account_login'), {
            'login': user.email, 'password': 'testpass123',
        })
        assert response.status_code == 302
        assert response.url == reverse('mfa_authenticate')
        # Not signed in yet.
        assert client.get(reverse('dashboard')).status_code == 302

        page = client.get(reverse('mfa_authenticate')).content.decode()
        assert 'Enter your code' in page
        response = client.post(reverse('mfa_authenticate'), {'code': _code(secret)})
        assert response.status_code == 302
        assert client.get(reverse('dashboard')).status_code == 200

    def test_reset_command_removes_the_app_and_codes(self, user):
        TOTP.activate(user, generate_totp_secret())
        call_command('reset_two_factor', user.email.upper())
        assert not Authenticator.objects.filter(user=user).exists()
