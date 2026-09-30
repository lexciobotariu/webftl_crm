from django import forms

from apps.tasks.models import Label

from .models import Project, Status

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'


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
        fields = ['name', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'category': forms.Select(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A status created with just a name is a plain "unstarted" column.
        self.fields['category'].required = False

    def clean_category(self):
        return self.cleaned_data.get('category') or Status.UNSTARTED


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ['name', 'color']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'flex-1 bg-panel border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none',
                'placeholder': 'Label name',
            }),
            'color': forms.TextInput(attrs={
                'class': 'w-20 bg-panel border border-border-subtle rounded-control px-2 py-2 text-sm text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none',
                'type': 'color',
            }),
        }
