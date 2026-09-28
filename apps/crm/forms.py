from django import forms

from .models import Company, Currency


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
