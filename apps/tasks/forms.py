from django import forms
from django.core.validators import MaxLengthValidator
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import get_assignable_users

from .durations import format_minutes, parse_duration
from .models import Label, RecurringTask, Subtask, Task
from .templatetags.task_markdown import MAX_LENGTH as MARKDOWN_MAX_LENGTH

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none transition-colors'


class TaskForm(forms.ModelForm):
    # Typed as text ("1h 30m") and stored as minutes on ``estimate_minutes``.
    estimate = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'e.g. 1h 30m'}),
    )
    # Posted as "1" or "0" by the switch on the form; left out, a task stays billable.
    billable = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Task
        fields = ['title', 'description', 'assignee', 'priority', 'due_date', 'billable', 'labels']
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

    def clean_billable(self):
        return self.cleaned_data['billable'] not in ('0', 'False')

    @property
    def billable_on(self):
        """Whether the switch shows billable: what was posted, else the task's value."""
        return self['billable'].value() not in (False, '0', 'False')

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


class RecurringTaskForm(forms.ModelForm):
    """A recurring task: what each new task gets, and when it repeats."""

    estimate = forms.CharField(required=False, label='Estimate',
                               widget=forms.TextInput(attrs={'placeholder': 'e.g. 1h 30m'}))
    weekday_choices = forms.MultipleChoiceField(
        required=False, label='On',
        choices=[(str(i), name) for i, name in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])],
        widget=forms.CheckboxSelectMultiple,
    )
    month_day_choice = forms.ChoiceField(required=False, label='On day')

    class Meta:
        model = RecurringTask
        fields = [
            'title', 'description', 'checklist', 'status', 'assignee', 'priority', 'billable', 'labels',
            'frequency', 'interval', 'start_date', 'end_date', 'due_after_days', 'add_date_to_title',
        ]
        labels = {
            'checklist': 'Sub-tasks',
            'status': 'Status',
            'billable': 'Billable',
            'frequency': 'Repeat every',
            'interval': 'Every',
            'start_date': 'Starts on',
            'end_date': 'Ends on',
            'due_after_days': 'Due (days after it is created)',
            'add_date_to_title': 'Add the date to the title (e.g. "Checks · November 2026")',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'checklist': forms.Textarea(attrs={'rows': 4, 'placeholder': 'One per line'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'labels': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields['status'].queryset = project.statuses.all()
        self.fields['status'].empty_label = 'First column'
        self.fields['assignee'].queryset = get_assignable_users(project)
        self.fields['assignee'].empty_label = 'Nobody'
        self.fields['labels'].queryset = Label.objects.filter(project=project)
        self.fields['priority'].choices = [('', 'No priority')] + list(Task.PRIORITY_CHOICES)
        self.fields['interval'].widget.attrs.update(min='1', max='99')
        self.fields['due_after_days'].widget.attrs.update(min='0', max='365', placeholder='No due date')
        self.fields['end_date'].help_text = 'Blank: keeps repeating.'
        self.fields['description'].max_length = MARKDOWN_MAX_LENGTH
        self.fields['month_day_choice'].choices = (
            [('', 'Same day as the start')] + [(str(day), str(day)) for day in range(1, 32)]
            + [(str(RecurringTask.LAST_DAY), 'Last day of the month')]
        )
        instance = self.instance
        if not self.is_bound:
            if instance.pk:
                self.initial['estimate'] = format_minutes(instance.estimate_minutes)
                self.initial['weekday_choices'] = [str(day) for day in instance.weekday_list]
                self.initial['month_day_choice'] = '' if instance.month_day is None else str(instance.month_day)
            elif not self.initial.get('start_date'):
                # The unsaved instance puts start_date=None in initial, so setdefault would keep it empty.
                self.initial['start_date'] = timezone.localdate()
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'w-4 h-4 bg-elevated border-border-subtle rounded text-zinc-200')
            else:
                field.widget.attrs.setdefault('class', DRAWER_INPUT)

    def clean_estimate(self):
        text = self.cleaned_data['estimate'].strip()
        if not text:
            return None
        try:
            return parse_duration(text, bare_unit='hours')
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'This is before the start date.')
        return cleaned

    def _post_clean(self):
        super()._post_clean()
        data = self.cleaned_data
        if 'estimate' in data:
            self.instance.estimate_minutes = data['estimate']
        self.instance.weekdays = ','.join(sorted(data.get('weekday_choices') or []))
        raw = data.get('month_day_choice')
        self.instance.month_day = int(raw) if raw not in (None, '') else None
