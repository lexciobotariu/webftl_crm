from django import forms

from .models import Client

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'name', 'email', 'phone', 'address',
            'billing_name', 'billing_email', 'tax_id',
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


class ClientDrawerForm(ClientForm):
    """Client form limited to the fields the drawers actually render.

    ClientForm also covers the legacy ``notes`` text field; submitting the
    drawer with the full field list silently blanked it.
    """

    class Meta(ClientForm.Meta):
        fields = [
            'name', 'email', 'phone', 'address',
            'billing_name', 'billing_email', 'tax_id',
        ]
