from django import forms

from .models import Client

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASSES}),
            'phone': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'address': forms.Textarea(attrs={
                'class': INPUT_CLASSES,
                'rows': 3
            }),
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
        fields = ['name', 'email', 'phone', 'address']
