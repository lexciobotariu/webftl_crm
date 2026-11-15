import re

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


def _compact(value):
    return ''.join((value or '').split()).replace('-', '').upper()


def iban_is_valid(iban):
    """ISO 13616: two letters, two check digits, then the account; mod 97 equals 1."""
    if not re.fullmatch(r'[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}', iban or ''):
        return False
    moved = iban[4:] + iban[:4]
    digits = ''.join(str(int(char, 36)) for char in moved)
    return int(digits) % 97 == 1


class BankAccount(models.Model):
    """A bank account the company is paid into, printed on the invoices that choose it.

    UK accounts use a sort code and account number; international accounts use
    SWIFT/BIC and IBAN. ``is_default`` with a currency makes it the account new
    invoices in that currency get; a default with no currency is the fallback.
    An account used on an invoice is archived, not deleted.
    """

    UK = 'uk'
    INTERNATIONAL = 'international'
    KIND_CHOICES = [
        (UK, 'UK (sort code and account number)'),
        (INTERNATIONAL, 'International (SWIFT and IBAN)'),
    ]

    kind = models.CharField(max_length=13, choices=KIND_CHOICES, default=UK)
    label = models.CharField(max_length=100)
    beneficiary_name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255)
    sort_code = models.CharField(max_length=6, blank=True)
    account_number = models.CharField(max_length=8, blank=True)
    swift_bic = models.CharField(max_length=11, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True, related_name='bank_accounts',
    )
    is_default = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['label', 'pk']

    def __str__(self):
        return self.label

    @property
    def is_uk(self):
        return self.kind == self.UK

    @property
    def sort_code_display(self):
        code = self.sort_code
        return f'{code[0:2]}-{code[2:4]}-{code[4:6]}' if len(code) == 6 else code

    @property
    def iban_display(self):
        return ' '.join(self.iban[i:i + 4] for i in range(0, len(self.iban), 4))

    def clean_fields(self, exclude=None):
        # Typed with spaces or dashes; stored compact, before the length checks run.
        self.sort_code = _compact(self.sort_code)
        self.account_number = _compact(self.account_number)
        self.swift_bic = _compact(self.swift_bic)
        self.iban = _compact(self.iban)
        super().clean_fields(exclude=exclude)

    def clean(self):
        errors = {}
        if self.kind == self.UK:
            if not re.fullmatch(r'[0-9]{6}', self.sort_code):
                errors['sort_code'] = 'Enter the 6-digit sort code, for example 12-34-56.'
            if not re.fullmatch(r'[0-9]{8}', self.account_number):
                errors['account_number'] = 'Enter the 8-digit account number.'
            self.swift_bic = self.iban = ''
        else:
            if not re.fullmatch(r'[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?', self.swift_bic):
                errors['swift_bic'] = 'Enter an 8 or 11 character SWIFT/BIC code.'
            if not iban_is_valid(self.iban):
                errors['iban'] = 'This IBAN is not valid. Check it for a typing error.'
            self.sort_code = self.account_number = ''
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from django.db import transaction

        with transaction.atomic():
            if self.archived_at is not None:
                self.is_default = False
            if self.is_default:
                BankAccount.objects.filter(
                    is_default=True, currency=self.currency,
                ).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)
            # Drafts follow the account; sent invoices keep what they were sent with.
            self.invoices.filter(sent_at__isnull=True).update(**self.snapshot())

    def snapshot(self):
        """The fields an invoice copies, as ``Invoice`` field names."""
        return {
            'bank_kind': self.kind,
            'bank_beneficiary_name': self.beneficiary_name,
            'bank_name': self.bank_name,
            'bank_sort_code': self.sort_code,
            'bank_account_number': self.account_number,
            'bank_swift_bic': self.swift_bic,
            'bank_iban': self.iban,
        }

    @classmethod
    def default_for(cls, currency_code):
        """The active default for this currency, else the default with no currency."""
        active = cls.objects.filter(archived_at__isnull=True, is_default=True)
        if currency_code:
            account = active.filter(currency__code=currency_code).first()
            if account:
                return account
        return active.filter(currency__isnull=True).first()
