from django import forms
from django.core.validators import MaxLengthValidator
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import get_assignable_users

from .durations import format_minutes, parse_duration
from .models import Label, Subtask, Task
from .templatetags.task_markdown import MAX_LENGTH as MARKDOWN_MAX_LENGTH

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none transition-colors'


class TaskForm(forms.ModelForm):
    # Typed as text ("1h 30m") and stored as minutes on ``estimate_minutes``.
    estimate = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'e.g. 1h 30m'}),
    )

    class Meta:
        model = Task
        fields = ['title', 'description', 'assignee', 'priority', 'due_date', 'labels']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
            'assignee': forms.Select(attrs={'class': INPUT_CLASSES}),
            'priority': forms.Select(attrs={'class': INPUT_CLASSES}),
            'due_date': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
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
        self.fields['description'].max_length = MARKDOWN_MAX_LENGTH
        self.fields['description'].validators.append(MaxLengthValidator(MARKDOWN_MAX_LENGTH))
        if self.instance.pk and 'estimate' not in self.initial:
            self.initial['estimate'] = format_minutes(self.instance.estimate_minutes)

    def clean_estimate(self):
        text = self.cleaned_data['estimate'].strip()
        if not text:
            return None
        try:
            # A bare number keeps meaning hours, as the old field did.
            return parse_duration(text, bare_unit='hours')
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def _post_clean(self):
        super()._post_clean()
        if 'estimate' in self.cleaned_data:
            self.instance.estimate_minutes = self.cleaned_data['estimate']


DRAWER_INPUT = (
    'w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm '
    'text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'
)


class DurationEntryForm(forms.Form):
    """Time as a duration on a day, not a start and an end."""

    duration = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': DRAWER_INPUT,
            'placeholder': 'e.g. 1h 30m',
            'autocomplete': 'off',
        }),
    )
    day = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DRAWER_INPUT}),
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': DRAWER_INPUT,
            'rows': 3,
            'placeholder': 'What did you work on? (optional)',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['day'].initial = timezone.localdate

    def clean_duration(self):
        try:
            # No bare_unit: "15" must not log 15 hours.
            return parse_duration(self.cleaned_data['duration'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Add subtask...'}),
        }
