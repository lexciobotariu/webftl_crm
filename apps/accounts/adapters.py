from allauth.account.adapter import DefaultAccountAdapter


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable open self-registration; admins create users via the team UI."""

    def is_open_for_signup(self, request):
        return False
