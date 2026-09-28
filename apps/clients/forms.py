from django import forms

from apps.crm.models import Currency

from .models import Client

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'name', 'email', 'phone', 'address',
            'billing_name', 'billing_email', 'tax_id',
            'currency',
            'notes',
        ]
        labels = {
            'billing_name': 'Billing name',
            'billing_email': 'Billing email',
            'tax_id': 'Tax ID',
        }
        help_texts = {
            'billing_name': 'A blank value uses the contact name.',
            'billing_email': 'A blank value uses the contact email.',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASSES}),
            'phone': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'address': forms.Textarea(attrs={
                'class': INPUT_CLASSES,
                'rows': 3
            }),
            'billing_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'billing_email': forms.EmailInput(attrs={'class': INPUT_CLASSES}),
            'tax_id': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'notes': forms.Textarea(attrs={
                'class': INPUT_CLASSES,
                'rows': 4
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locked = bool(self.instance.pk and self.instance.currency_id)
        if locked:
            self.fields.pop('currency')
            return
        currency = self.fields['currency']
        currency.queryset = Currency.objects.order_by('code')
        currency.required = True
        currency.empty_label = 'Select a currency'
        currency.label = 'Currency'
        currency.help_text = 'Choose once. It stays after the first save.'
        currency.widget.attrs['class'] = INPUT_CLASSES


class ClientDrawerForm(ClientForm):
    """Client form limited to the fields the drawers actually render.

    ClientForm also covers the legacy ``notes`` text field; submitting the
    drawer with the full field list silently blanked it.
    """

    class Meta(ClientForm.Meta):
        fields = [
            'name', 'email', 'phone', 'address',
            'billing_name', 'billing_email', 'tax_id',
            'currency',
        ]
