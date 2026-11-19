from django import forms

from .models import VaultEntry

INPUT = ('w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 '
         'placeholder-zinc-600 focus:border-border-strong focus:outline-none')


class VaultEntryForm(forms.ModelForm):
    # The typed text is limited; the encrypted text stored is longer.
    username = forms.CharField(max_length=255, required=False)
    password = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput(render_value=True))
    notes = forms.CharField(max_length=8000, required=False, widget=forms.Textarea(attrs={'rows': 5}))

    class Meta:
        model = VaultEntry
        fields = ['kind', 'title', 'url', 'username', 'password', 'notes']
        labels = {'kind': 'Type', 'url': 'Address'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].widget.attrs.setdefault('placeholder', 'Hosting, WordPress admin, Instagram, ...')
        self.fields['url'].widget.attrs.setdefault('placeholder', 'https://...')
        self.fields['password'].widget.attrs.setdefault('autocomplete', 'new-password')
        self.fields['notes'].help_text = 'Encrypted. 2FA backup codes, API keys, anything private.'
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT)

    def clean(self):
        data = super().clean()
        if data.get('kind') == VaultEntry.NOTE:
            data['username'] = ''
            data['password'] = ''
        return data
