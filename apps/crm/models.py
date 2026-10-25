from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.fields import EncryptedCharField


class Company(models.Model):
    """The single company these invoices are sent from.

    Fields stay blank until an admin fills them in. There is one row.
    """

    THEME_DARK = 'dark'
    THEME_LIGHT = 'light'
    THEME_CHOICES = [
        (THEME_DARK, 'Dark'),
        (THEME_LIGHT, 'Light'),
    ]

    legal_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    theme = models.CharField(max_length=5, choices=THEME_CHOICES, default=THEME_DARK)

    # Where uploaded files go. See apps/crm/storage.py.
    STORAGE_DISK = 'disk'
    STORAGE_S3 = 's3'
    STORAGE_CHOICES = [
        (STORAGE_DISK, 'Server disk'),
        (STORAGE_S3, 'S3-compatible bucket'),
    ]
    storage_backend = models.CharField(
        max_length=4, choices=STORAGE_CHOICES, default=STORAGE_DISK
    )
    s3_endpoint_url = models.URLField(blank=True)
    s3_region = models.CharField(max_length=64, blank=True)
    s3_bucket = models.CharField(max_length=255, blank=True)
    s3_access_key = models.CharField(max_length=255, blank=True)
    s3_secret_key = EncryptedCharField(max_length=512, blank=True)
    s3_prefix = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = 'company'

    def __str__(self):
        return self.legal_name or 'Company'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @property
    def uses_s3(self):
        return self.storage_backend == self.STORAGE_S3 and bool(self.s3_bucket)

    @classmethod
    def load(cls):
        company, _created = cls.objects.get_or_create(pk=1)
        return company


class Currency(models.Model):
    """A currency an admin allows on clients.

    ``code`` is three letters, unique, and stays as it was created.
    ``symbol_before`` chooses which side of the amount the symbol sits on.
    It defaults to before the amount.
    """

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=16)
    symbol_before = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'currencies'

    def __str__(self):
        return f'{self.code} {self.symbol}'

    def clean(self):
        code = (self.code or '').strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValidationError({'code': 'Enter a 3-letter code.'})
        if self.pk:
            original = (
                Currency.objects.filter(pk=self.pk).values_list('code', flat=True).first()
            )
            if original and original != code:
                raise ValidationError({'code': 'The code cannot be changed.'})
        self.code = code
        self.name = (self.name or '').strip()
        self.symbol = (self.symbol or '').strip()
        errors = {}
        if not self.name:
            errors['name'] = 'Enter a name.'
        if not self.symbol:
            errors['symbol'] = 'Enter a symbol.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
