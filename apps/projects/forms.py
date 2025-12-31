from django import forms

from .models import Project, Status

INPUT_CLASSES = 'w-full bg-card border border-border rounded-md px-3 py-2 text-zinc-50 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'

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
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
        }
