from django import forms

from apps.accounts.models import User
from apps.projects.models import get_assignable_users

from .models import Label, Subtask, Task

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors'


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assignee', 'priority', 'due_date', 'time_estimate', 'labels']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
            'assignee': forms.Select(attrs={'class': INPUT_CLASSES}),
            'priority': forms.Select(attrs={'class': INPUT_CLASSES}),
            'due_date': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'time_estimate': forms.NumberInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Hours'}),
            'labels': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, project=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].required = False
        if project:
            self.fields['labels'].queryset = Label.objects.filter(project=project)
            self.fields['assignee'].queryset = get_assignable_users(project)
        else:
            self.fields['assignee'].queryset = User.objects.none()


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Add subtask...'}),
        }
