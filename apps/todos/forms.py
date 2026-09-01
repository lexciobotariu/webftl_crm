from django import forms

from apps.clients.models import Client

from .models import Todo

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors'


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todo
        fields = ['title', 'description', 'due_date', 'client']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'What needs to be done?'}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 3, 'placeholder': 'Additional details...'}),
            'due_date': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'client': forms.Select(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_admin and not user.has_app_permission('access_clients'):
            self.fields['client'].queryset = Client.objects.none()
        else:
            self.fields['client'].queryset = Client.objects.all()
        self.fields['client'].required = False
        self.fields['client'].empty_label = 'Personal (no client)'
