from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.models import Authenticator
from django.conf import settings


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable open self-registration; admins create users via the team UI."""

    def is_open_for_signup(self, request):
        return False


class AgencyMFAAdapter(DefaultMFAAdapter):
    """Admins cannot turn off their authenticator app while it is required."""

    def can_delete_authenticator(self, authenticator):
        if (
            settings.REQUIRE_ADMIN_2FA
            and authenticator.type == Authenticator.Type.TOTP
            and authenticator.user.is_admin
        ):
            return False
        return super().can_delete_authenticator(authenticator)
