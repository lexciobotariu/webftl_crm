from allauth.mfa.totp.forms import ActivateTOTPForm
from allauth.mfa.totp.internal import auth
from django import forms


class StableActivateTOTPForm(ActivateTOTPForm):
    """Keep the same key for the whole setup.

    allauth makes a new key on every load of the setup page, so a refresh, a second
    tab or a browser preload after the QR code was scanned leaves the phone with a
    key the server no longer has, and every code is "incorrect". Here the key stays
    in the session from the first load until setup succeeds.
    """

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        forms.Form.__init__(self, *args, **kwargs)
        self.secret = auth.get_totp_secret(regenerate=False)
