from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .fields import EncryptedCharField
from .managers import UserManager
from .permissions import PermissionPreset  # noqa: F401 — required for Django model discovery


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    permission_preset = models.ForeignKey(
        'accounts.PermissionPreset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    github_token = EncryptedCharField(max_length=512, blank=True, help_text="Encrypted at rest")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == 'admin'

    def has_app_permission(self, key):
        """Check if user has the given app-level permission.
        Named has_app_permission to avoid clash with Django's has_perm system.
        """
        if self.is_admin:
            return True
        if not self.permission_preset:
            # Users without a preset only get dashboard access
            return key == 'access_dashboard'
        return self.permission_preset.has_permission(key)
