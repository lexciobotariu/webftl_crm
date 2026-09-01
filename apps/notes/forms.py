from django import forms

from .models import Note


class NoteForm(forms.ModelForm):
    """Note form that owns the client-XOR-project invariant.

    The parent is not a form field — the view knows it from the URL — so it is
    passed in and validated here rather than via a bare ``full_clean()`` in the
    view, which raised an uncaught ValidationError (500) instead of rendering.
    """

    class Meta:
        model = Note
        fields = ['title', 'description', 'is_private']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card '
                         'text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none '
                         'focus:ring-2 focus:ring-purple-500',
                'placeholder': 'Enter note title',
            }),
            'description': forms.Textarea(attrs={
                'rows': 8,
                'class': 'w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card '
                         'text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none '
                         'focus:ring-2 focus:ring-purple-500 resize-none',
                'placeholder': 'Enter note description...',
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 bg-elevated border-border-subtle rounded text-purple-600 '
                         'focus:ring-2 focus:ring-purple-500',
            }),
        }

    def __init__(self, *args, client=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_client = client
        self.parent_project = project
        if client is not None:
            self.instance.client = client
        if project is not None:
            self.instance.project = project

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if not title:
            raise forms.ValidationError('Title is required.')
        return title

    def clean(self):
        cleaned_data = super().clean()
        client = self.parent_client or self.instance.client
        project = self.parent_project or self.instance.project
        if not (bool(client) ^ bool(project)):
            raise forms.ValidationError(
                'A note must belong to either a client or a project.'
            )
        return cleaned_data

    def save(self, commit=True):
        note = super().save(commit=False)
        if self.parent_client is not None:
            note.client = self.parent_client
        if self.parent_project is not None:
            note.project = self.parent_project
        if commit:
            note.save()
        return note
