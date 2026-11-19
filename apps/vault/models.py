"""The Vault: a client's logins and private notes (hosting, social media, API keys, ...).

Username, password and notes are encrypted with the app's Fernet key
(FERNET_KEY), so a database dump alone reveals nothing. Passwords and notes
are shown only when someone asks, and each time is logged (``VaultAccess``).
Seen by presets with the Vault permission. Never shown in search, MCP,
the client portal or emails.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models

from apps.accounts.fields import EncryptedCharField


def safe_link(url):
    """``url`` as a link when it is http(s) (adding https:// to a bare host), else ''."""
    url = (url or '').strip()
    if not url or url.lower().startswith(('javascript:', 'data:', 'vbscript:')):
        return ''
    if '://' not in url:
        url = f'https://{url}'
    return url if urlsplit(url).scheme in ('http', 'https') else ''


class VaultEntry(models.Model):
    LOGIN = 'login'
    NOTE = 'note'
    KIND_CHOICES = [(LOGIN, 'Login'), (NOTE, 'Note')]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='vault_entries')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=LOGIN)
    title = models.CharField(max_length=200)
    url = models.CharField(max_length=500, blank=True)
    # Sizes are for the encrypted text; the form limits what is typed.
    username = EncryptedCharField(max_length=1000, blank=True)
    password = EncryptedCharField(max_length=1000, blank=True)
    notes = EncryptedCharField(max_length=20000, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'pk']
        verbose_name_plural = 'vault entries'

    def __str__(self):
        return self.title

    @property
    def link(self):
        return safe_link(self.url)

    @property
    def has_secret(self):
        return bool(self.password or self.notes)


class VaultAccess(models.Model):
    """Someone showed or copied an entry's password or notes."""

    SHOW = 'show'
    COPY = 'copy'
    ACTION_CHOICES = [(SHOW, 'Showed'), (COPY, 'Copied the password')]

    entry = models.ForeignKey(VaultEntry, on_delete=models.CASCADE, related_name='accesses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-pk']
