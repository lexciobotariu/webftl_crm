from django import forms

from .models import Company, Currency

INPUT_CLASSES = (
    'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm '
    'text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
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
    class Meta:
        model = Currency
        fields = ['code', 'name', 'symbol']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'maxlength': '3',
                'autocapitalize': 'characters',
            }),
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'symbol': forms.TextInput(attrs={'class': INPUT_CLASSES}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise forms.ValidationError('Enter a 3-letter code.')
        return code
