from cryptography.fernet import Fernet


def test_fernet_keys_are_valid(settings):
    """Every configured Fernet key must construct a Fernet instance."""
    for key in settings.FERNET_KEYS:
        Fernet(key.encode())
