from django import forms

from apps.tasks.models import Label

from .models import Project, Status

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['client', 'name', 'description', 'github_repo_url']
        widgets = {
            'client': forms.Select(attrs={'class': INPUT_CLASSES}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
            'github_repo_url': forms.URLInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'https://github.com/org/repo'}),
        }


class StatusForm(forms.ModelForm):
    class Meta:
        model = Status
        fields = ['name', 'is_done']
        labels = {'is_done': 'Counts as done'}
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'is_done': forms.CheckboxInput(attrs={'class': 'accent-accent w-4 h-4'}),
        }


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ['name', 'color']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'flex-1 bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none',
                'placeholder': 'Label name',
            }),
            'color': forms.TextInput(attrs={
                'class': 'w-20 bg-panel border border-border-subtle rounded-card px-2 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none',
                'type': 'color',
            }),
        }
