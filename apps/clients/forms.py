from django import forms

from .models import Client


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none',
                'rows': 3
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none',
                'rows': 4
            }),
        }
