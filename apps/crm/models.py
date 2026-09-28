from django.core.exceptions import ValidationError
from django.db import models


class Company(models.Model):
    """The single company these invoices are sent from.

    Fields stay blank until an admin fills them in. There is one row.
    """

    legal_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name_plural = 'company'

    def __str__(self):
        return self.legal_name or 'Company'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        company, _created = cls.objects.get_or_create(pk=1)
        return company


class Currency(models.Model):
    """A currency an admin allows on clients.

    ``code`` is three letters, unique, and stays as it was created.
    """

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=16)

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
