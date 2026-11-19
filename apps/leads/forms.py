from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.clients.models import active_clients, visible_clients
from apps.crm.models import Currency

from .models import Lead, LeadNote, LeadSource, LeadStatus

INPUT_CLASSES = (
    'w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 '
    'placeholder-zinc-500 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'
)


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', '%Y-%m-%d')
        super().__init__(*args, **kwargs)


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'name', 'contact_name', 'email', 'phone', 'website', 'address', 'tax_id', 'currency',
            'status', 'source', 'assignee', 'value', 'next_follow_up', 'description', 'lost_reason',
        ]
        labels = {
            'name': 'Company or name',
            'contact_name': 'Contact person',
            'tax_id': 'Tax ID',
            'value': 'Estimated value',
            'next_follow_up': 'Next follow-up',
            'description': 'About',
            'lost_reason': 'Why it was lost',
        }
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'lost_reason': forms.Textarea(attrs={'rows': 2}),
            'next_follow_up': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].queryset = Currency.objects.order_by('code')
        self.fields['currency'].empty_label = 'No currency yet'
        self.fields['currency'].help_text = 'Estimates for this lead are in this currency.'
        # Won is reached by converting the lead, and a converted lead stays won.
        if self.instance.is_converted:
            self.fields['status'].queryset = LeadStatus.objects.filter(kind=LeadStatus.WON)
        else:
            self.fields['status'].queryset = LeadStatus.objects.exclude(kind=LeadStatus.WON)
        self.fields['status'].empty_label = None
        self.fields['source'].queryset = LeadSource.objects.all()
        self.fields['source'].empty_label = 'Unknown'
        users = get_user_model().objects.filter(is_active=True)
        if self.instance.assignee_id:
            users = get_user_model().objects.filter(Q(is_active=True) | Q(pk=self.instance.assignee_id))
        self.fields['assignee'].queryset = users.order_by('name')
        self.fields['assignee'].empty_label = 'Nobody'
        self.fields['assignee'].label_from_instance = lambda user: user.name or user.email
        self.fields['value'].widget.attrs.update(min='0', step='0.01')
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault('status', LeadStatus.first_of(LeadStatus.OPEN))
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT_CLASSES)

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        if status and status.kind == LeadStatus.WON and not self.instance.is_converted:
            self.add_error('status', 'A lead is won when it becomes a client: use "Convert to client".')
        if self.instance.is_converted and status and status.kind != LeadStatus.WON:
            self.add_error('status', 'This lead is a client now, so it stays won.')
        return cleaned


class LeadNoteForm(forms.ModelForm):
    class Meta:
        model = LeadNote
        fields = ['body']
        widgets = {'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Call notes, what they need, next steps…'})}


class ConvertForm(forms.Form):
    """Make the lead a client: a new one from the lead's details, or one that exists."""

    NEW = 'new'
    EXISTING = 'existing'

    target = forms.ChoiceField(choices=[(NEW, 'New client'), (EXISTING, 'Existing client')], initial=NEW)
    client = forms.ModelChoiceField(queryset=None, required=False)
    create_project = forms.BooleanField(required=False)
    project_name = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, user, lead, **kwargs):
        super().__init__(*args, **kwargs)
        self.lead = lead
        self.fields['client'].queryset = active_clients(visible_clients(user)).order_by('name')
        self.fields['client'].empty_label = 'Select a client'
        if not self.is_bound:
            self.initial.setdefault('project_name', lead.name)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('target') == self.EXISTING and not cleaned.get('client'):
            self.add_error('client', 'Choose the client.')
        if cleaned.get('target') == self.NEW and self.lead.currency_id is None:
            self.add_error(None, 'Choose a currency for the lead first: the new client is invoiced in it.')
        if cleaned.get('create_project') and not cleaned.get('project_name', '').strip():
            self.add_error('project_name', 'Name the project.')
        return cleaned


class LeadStatusForm(forms.ModelForm):
    class Meta:
        model = LeadStatus
        fields = ['name', 'kind', 'color', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT_CLASSES)

    def clean_kind(self):
        kind = self.cleaned_data['kind']
        status = self.instance
        if status.pk and status.kind != kind and status.kind != LeadStatus.OPEN:
            if not LeadStatus.objects.filter(kind=status.kind).exclude(pk=status.pk).exists():
                raise forms.ValidationError(f'Keep one {status.get_kind_display()} status.')
        if status.pk and status.kind != kind and kind == LeadStatus.WON and status.leads.filter(
            client__isnull=True,
        ).exists():
            raise forms.ValidationError('Leads that are not clients are in this status.')
        return kind


class LeadSourceForm(forms.ModelForm):
    class Meta:
        model = LeadSource
        fields = ['name', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT_CLASSES)
