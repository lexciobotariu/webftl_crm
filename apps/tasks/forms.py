from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import get_assignable_users

from .models import Label, Subtask, Task

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none transition-colors'


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


DATETIME_INPUT_FORMATS = [
    '%Y-%m-%dT%H:%M',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S',
]

DRAWER_INPUT = (
    'w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm '
    'text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'
)


class TimeEntryForm(forms.Form):
    started_at = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
            'type': 'datetime-local',
            'class': DRAWER_INPUT,
        }),
    )
    ended_at = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
            'type': 'datetime-local',
            'class': DRAWER_INPUT,
        }),
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': DRAWER_INPUT,
            'rows': 3,
            'placeholder': 'What did you work on? (optional)',
        }),
    )

    def clean(self):
        cleaned = super().clean()
        started = cleaned.get('started_at')
        ended = cleaned.get('ended_at')
        if started and ended:
            if ended <= started:
                self.add_error('ended_at', 'End must be after start.')
            elif ended > timezone.now():
                self.add_error('ended_at', 'End cannot be in the future.')
        return cleaned


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Add subtask...'}),
        }
