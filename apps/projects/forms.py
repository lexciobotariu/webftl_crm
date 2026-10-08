from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from apps.clients.models import active_clients, visible_clients
from apps.tasks.models import Label

from .models import Project, Status

INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'


# Only web addresses: the overview renders this as a link, so a ``javascript:``
# value would run in the browser of whoever clicks it.
_github_url_validator = URLValidator(schemes=['http', 'https'])
_NAME_MAX = Project._meta.get_field('name').max_length
_URL_MAX = Project._meta.get_field('github_repo_url').max_length


def project_field_errors(name, github_repo_url):
    """Errors for the project fields saved outside a ModelForm (the settings page).

    The same rules ``ClientProjectForm`` and ``ProjectForm`` apply, keyed by field.
    """
    errors = {}
    if not name:
        errors['name'] = 'Name is required.'
    elif len(name) > _NAME_MAX:
        errors['name'] = f'Name can be at most {_NAME_MAX} characters.'
    if github_repo_url:
        if len(github_repo_url) > _URL_MAX:
            errors['github_repo_url'] = f'The address can be at most {_URL_MAX} characters.'
        else:
            try:
                _github_url_validator(github_repo_url)
            except ValidationError:
                errors['github_repo_url'] = 'Enter a web address starting with https://.'
    return errors


class ClientProjectForm(forms.ModelForm):
    """A new project on a client that is already chosen (the client page drawer)."""

    class Meta:
        model = Project
        fields = ['name', 'description', 'github_repo_url']

    def clean_github_repo_url(self):
        url = self.cleaned_data.get('github_repo_url', '')
        error = project_field_errors('x', url).get('github_repo_url')
        if error:
            raise ValidationError(error)
        return url


class ProjectForm(ClientProjectForm):
    """A new project from the projects page: the client is picked here.

    Only active clients the person can see are offered or accepted.
    """

    class Meta:
        model = Project
        fields = ['client', 'name', 'description', 'github_repo_url']
        widgets = {
            'client': forms.Select(attrs={'class': INPUT_CLASSES}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
            'github_repo_url': forms.URLInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'https://github.com/org/repo'}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = active_clients(visible_clients(user)).order_by('name')


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
