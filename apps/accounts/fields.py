"""
Custom encrypted field for storing sensitive data like API tokens.
Uses Fernet symmetric encryption (AES-128-CBC with HMAC).
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class EncryptedCharField(models.CharField):
    """
    A CharField that encrypts its value before storing in the database.
    Decrypts automatically when retrieving.

    Requires FERNET_KEYS setting with at least one valid Fernet key.
    """

    description = "An encrypted string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _get_fernet(self):
        """Get Fernet instance using the first key from settings."""
        keys = getattr(settings, 'FERNET_KEYS', [])
        if not keys:
            raise ValueError("FERNET_KEYS setting is required for EncryptedCharField")
        return Fernet(keys[0].encode() if isinstance(keys[0], str) else keys[0])

    def get_prep_value(self, value):
        """Encrypt the value before saving to database."""
        if value is None or value == '':
            return value

        # Don't re-encrypt if already encrypted
        if value.startswith('gAAAAA'):
            return value

        fernet = self._get_fernet()
        encrypted = fernet.encrypt(value.encode())
        return encrypted.decode()

    def from_db_value(self, value, expression, connection):
        """Decrypt the value when reading from database."""
        if value is None or value == '':
            return value

        # Handle unencrypted legacy values gracefully
        if not value.startswith('gAAAAA'):
            return value

        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(value.encode())
            return decrypted.decode()
        except InvalidToken:
            # If decryption fails, return empty string for safety
            return ''

    def to_python(self, value):
        """Convert value to Python string (handles form input)."""
        if value is None:
            return value
        return str(value)

    def deconstruct(self):
        """Support migrations by returning field constructor args."""
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs
