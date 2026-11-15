from django import forms

from .models import BankAccount, Company, Currency
from .storage import StorageCheckError, bucket_for, check_bucket


def _symbol_sits_before(value):
    return value == 'before'


INPUT_CLASSES = (
    'w-full bg-panel border border-border-subtle rounded-control px-3 py-2 text-sm '
    'text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'
)


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['legal_name', 'address', 'email', 'phone', 'tax_id']
        labels = {
            'legal_name': 'Legal name',
            'tax_id': 'Tax ID',
        }
        widgets = {
            'legal_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'address': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 3}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASSES}),
            'phone': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'tax_id': forms.TextInput(attrs={'class': INPUT_CLASSES}),
        }

    def save(self, commit=True):
        company = super().save(commit=False)
        if commit:
            company.save(update_fields=['legal_name', 'address', 'email', 'phone', 'tax_id'])
        return company


RADIO_CLASSES = (
    'w-3.5 h-3.5 border-border-subtle bg-panel accent-zinc-200 '
    'focus:ring-border-strong focus:ring-offset-0'
)


class ThemeForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['theme']
        widgets = {
            'theme': forms.RadioSelect(attrs={'class': RADIO_CLASSES}),
        }

    def save(self, commit=True):
        company = super().save(commit=False)
        if commit:
            company.save(update_fields=['theme'])
        return company


class StorageForm(forms.ModelForm):
    """Where uploaded files go. Saving a bucket first proves it can be written.

    The secret key is never shown again: leaving it blank keeps the saved one.
    """

    s3_endpoint_url = forms.URLField(
        required=False,
        assume_scheme='https',
        label='Endpoint URL',
        help_text=(
            'Leave blank for Amazon S3. For Cloudflare R2, Backblaze B2, '
            'Hetzner, DigitalOcean or MinIO, paste the S3 endpoint they give you.'
        ),
        widget=forms.URLInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'https://'}),
    )

    class Meta:
        model = Company
        fields = [
            'storage_backend', 's3_endpoint_url', 's3_region', 's3_bucket',
            's3_access_key', 's3_secret_key', 's3_prefix',
        ]
        labels = {
            'storage_backend': 'Store files on',
            's3_region': 'Region',
            's3_bucket': 'Bucket',
            's3_access_key': 'Access key ID',
            's3_secret_key': 'Secret access key',
            's3_prefix': 'Folder in the bucket',
        }
        help_texts = {
            's3_region': 'For example eu-central-1. R2 uses "auto".',
            's3_prefix': 'Optional, for example "crm". Files go under this folder.',
        }
        widgets = {
            'storage_backend': forms.RadioSelect(attrs={'class': RADIO_CLASSES}),
            's3_region': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            's3_bucket': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            's3_access_key': forms.TextInput(attrs={
                'class': INPUT_CLASSES, 'autocomplete': 'off',
            }),
            's3_secret_key': forms.PasswordInput(
                render_value=False,
                attrs={'class': INPUT_CLASSES, 'autocomplete': 'new-password'},
            ),
            's3_prefix': forms.TextInput(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved_secret = self.instance.s3_secret_key if self.instance.pk else ''
        if self.saved_secret:
            self.fields['s3_secret_key'].widget.attrs['placeholder'] = (
                'Saved. Leave blank to keep it.'
            )

    def clean_s3_bucket(self):
        return (self.cleaned_data.get('s3_bucket') or '').strip()

    def clean_s3_access_key(self):
        return (self.cleaned_data.get('s3_access_key') or '').strip()

    def clean_s3_secret_key(self):
        return (self.cleaned_data.get('s3_secret_key') or '').strip() or self.saved_secret

    def clean_s3_region(self):
        return (self.cleaned_data.get('s3_region') or '').strip()

    def clean_s3_prefix(self):
        return (self.cleaned_data.get('s3_prefix') or '').strip().strip('/')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('storage_backend') != Company.STORAGE_S3:
            return cleaned
        for field in ('s3_bucket', 's3_access_key', 's3_secret_key'):
            if not cleaned.get(field):
                self.add_error(field, 'Required for a bucket.')
        if self.errors:
            return cleaned
        storage = bucket_for(
            cleaned.get('s3_endpoint_url') or '',
            cleaned['s3_region'],
            cleaned['s3_bucket'],
            cleaned['s3_access_key'],
            cleaned['s3_secret_key'],
            cleaned['s3_prefix'],
        )
        try:
            check_bucket(storage)
        except StorageCheckError as exc:
            raise forms.ValidationError(
                f'Could not write a test file to the bucket, so nothing was saved: {exc}'
            ) from exc
        return cleaned

    def save(self, commit=True):
        company = super().save(commit=False)
        if commit:
            company.save(update_fields=self.Meta.fields)
        return company


class CurrencyForm(forms.ModelForm):
    symbol_before = forms.TypedChoiceField(
        label='Symbol position',
        choices=(
            ('before', 'Before the amount'),
            ('after', 'After the amount'),
        ),
        coerce=_symbol_sits_before,
        widget=forms.Select(attrs={'class': INPUT_CLASSES}),
    )

    class Meta:
        model = Currency
        fields = ['code', 'name', 'symbol', 'symbol_before']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'maxlength': '3',
                'autocapitalize': 'characters',
            }),
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'symbol': forms.TextInput(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['symbol_before'] = (
            'before' if self.instance.symbol_before else 'after'
        )

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise forms.ValidationError('Enter a 3-letter code.')
        return code


CHECKBOX_CLASSES = (
    'w-3.5 h-3.5 rounded border-border-subtle bg-panel accent-zinc-200 '
    'focus:ring-border-strong focus:ring-offset-0'
)


class BankAccountForm(forms.ModelForm):
    """One account. The model cleans the numbers and checks them for its kind."""

    class Meta:
        model = BankAccount
        fields = [
            'kind', 'label', 'beneficiary_name', 'bank_name',
            'sort_code', 'account_number', 'swift_bic', 'iban',
            'currency', 'is_default',
        ]
        labels = {
            'kind': 'Type',
            'label': 'Name in the CRM',
            'beneficiary_name': 'Beneficiary name',
            'bank_name': 'Bank name',
            'sort_code': 'Sort code',
            'account_number': 'Account number',
            'swift_bic': 'SWIFT/BIC',
            'iban': 'IBAN',
            'currency': 'Currency',
            'is_default': 'Default for this currency',
        }
        help_texts = {
            'label': 'Only you see it, in the invoice selector. For example "Wise GBP".',
            'currency': 'Optional. New invoices in this currency get the default account for it.',
            'is_default': (
                'New invoices in this currency get this account. '
                'A default with no currency is used when a currency has none.'
            ),
        }
        widgets = {
            'kind': forms.RadioSelect(attrs={'class': RADIO_CLASSES}),
            'label': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'beneficiary_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'bank_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'sort_code': forms.TextInput(attrs={
                'class': INPUT_CLASSES, 'placeholder': '12-34-56', 'maxlength': '8',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'account_number': forms.TextInput(attrs={
                'class': INPUT_CLASSES, 'placeholder': '12345678', 'maxlength': '10',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'swift_bic': forms.TextInput(attrs={
                'class': INPUT_CLASSES, 'maxlength': '11', 'autocapitalize': 'characters',
                'autocomplete': 'off',
            }),
            'iban': forms.TextInput(attrs={
                'class': INPUT_CLASSES, 'maxlength': '42', 'autocapitalize': 'characters',
                'autocomplete': 'off',
            }),
            'currency': forms.Select(attrs={'class': INPUT_CLASSES}),
            'is_default': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].empty_label = 'Any currency'
        # Typed with spaces or dashes; the model stores them compact.
        for name, size in (('sort_code', 8), ('account_number', 10), ('swift_bic', 11), ('iban', 42)):
            self.fields[name].max_length = size
            self.fields[name].validators = []

    def _compact(self, name):
        return ''.join((self.cleaned_data.get(name) or '').split()).replace('-', '').upper()

    def clean_sort_code(self):
        return self._compact('sort_code')

    def clean_account_number(self):
        return self._compact('account_number')

    def clean_swift_bic(self):
        return self._compact('swift_bic')

    def clean_iban(self):
        return self._compact('iban')
