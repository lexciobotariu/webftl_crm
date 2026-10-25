from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def has_two_factor(user):
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


class RequireAdminTwoFactorMiddleware:
    """Send an admin without an authenticator app to set one up before anything else.

    Admins see salaries, invoices and every setting, so a password alone is not
    enough for them. Sign-in pages, the two-factor pages and sign-out stay open
    (all under /accounts/), so the setup itself can be reached.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            settings.REQUIRE_ADMIN_2FA
            and user is not None
            and user.is_authenticated
            and user.is_admin
            and not request.path.startswith(('/accounts/', f'/{settings.STATIC_URL}'))
            and not has_two_factor(user)
        ):
            target = reverse('mfa_activate_totp')
            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = target
                return response
            return redirect(target)
        return self.get_response(request)
