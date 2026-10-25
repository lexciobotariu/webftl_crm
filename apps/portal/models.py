from django.db import models
from django.utils import timezone


class PortalLink(models.Model):
    """A one-time sign-in link emailed to a client contact.

    Only a hash of the token is stored, so the database alone cannot sign anyone in.
    """

    contact = models.ForeignKey('clients.ClientContact', on_delete=models.CASCADE, related_name='portal_links')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Portal link for {self.contact}'

    @property
    def usable(self):
        return self.used_at is None and self.expires_at > timezone.now()
