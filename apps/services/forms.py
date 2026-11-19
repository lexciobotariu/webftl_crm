from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.clients.models import Client, active_clients
from apps.projects.models import Project

from .models import Service, ServiceReport, ServiceType, Site, SiteCredential

INPUT_CLASSES = (
    'w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm text-zinc-100 '
    'placeholder-zinc-500 focus:border-border-strong focus:ring-1 focus:ring-border-strong focus:outline-none'
)
CHECKBOX_CLASSES = 'w-4 h-4 bg-elevated border-border-subtle rounded text-zinc-200 focus:ring-border-strong'


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', '%Y-%m-%d')
        super().__init__(*args, **kwargs)


def _style(form):
    for field in form.fields.values():
        if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
            field.widget.attrs.setdefault('class', CHECKBOX_CLASSES)
        else:
            field.widget.attrs.setdefault('class', INPUT_CLASSES)


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = [
            'name', 'url', 'built_by', 'built_by_name', 'project', 'platform', 'hosting',
            'domain_registrar', 'domain_expires', 'ssl_expires', 'admin_url', 'repo_url', 'notes',
        ]
        labels = {
            'url': 'Address',
            'built_by': 'Built by',
            'built_by_name': 'Who built it',
            'project': 'Our project',
            'domain_expires': 'Domain expires',
            'ssl_expires': 'SSL expires',
            'admin_url': 'Admin address',
            'repo_url': 'Repository',
        }
        widgets = {
            'domain_expires': DateInput(),
            'ssl_expires': DateInput(),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.fields['project'].queryset = Project.objects.filter(client=client).order_by('name')
        self.fields['project'].empty_label = 'None'
        self.fields['project'].help_text = 'When we built it.'
        self.fields['built_by_name'].help_text = 'The agency or person, when it was not us.'
        self.fields['url'].widget.attrs.setdefault('placeholder', 'https://')
        _style(self)

    def save(self, commit=True):
        site = super().save(commit=False)
        site.client = self.client
        if site.built_by == Site.US:
            site.built_by_name = ''
        if commit:
            site.save()
        return site


class CredentialForm(forms.ModelForm):
    # The typed text is limited; the encrypted text stored is longer.
    username = forms.CharField(max_length=255, required=False)
    password = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput(render_value=True))
    notes = forms.CharField(max_length=1500, required=False, widget=forms.Textarea(attrs={'rows': 3}))

    class Meta:
        model = SiteCredential
        fields = ['label', 'url', 'username', 'password', 'notes']
        labels = {'url': 'Login address'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['label'].widget.attrs.setdefault('placeholder', 'Hosting, WordPress admin, FTP, ...')
        self.fields['password'].widget.attrs.setdefault('autocomplete', 'new-password')
        _style(self)


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            'client', 'service_type', 'name', 'sites', 'description', 'start_date', 'renewal_date', 'auto_renew',
            'term_months', 'notice_days', 'frequency', 'price', 'included_hours', 'overage_rate',
        ]
        labels = {
            'renewal_date': 'Renews or ends on',
            'auto_renew': 'Renews automatically',
            'term_months': 'Renews for (months)',
            'notice_days': 'Remind me (days before)',
            'frequency': 'Billed',
            'price': 'Price per billing period',
            'included_hours': 'Hours included each month',
            'overage_rate': 'Price of an extra hour',
            'service_type': 'Type',
            'description': 'What it covers',
        }
        widgets = {
            'start_date': DateInput(),
            'renewal_date': DateInput(),
            'description': forms.Textarea(attrs={'rows': 3}),
            'sites': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, user, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        editing = self.instance.pk is not None
        if editing:
            # The service's project belongs to the client, so the client stays.
            del self.fields['client']
            client = self.instance.client
        else:
            self.fields['client'].queryset = active_clients(Client.objects.all()).order_by('name')
            self.fields['client'].empty_label = 'Choose a client'
            if client is not None:
                self.initial['client'] = client.pk
            self.initial.setdefault('start_date', timezone.localdate())
        if client is None and self.is_bound:
            raw = self.data.get('client', '')
            client = Client.objects.filter(pk=raw).first() if str(raw).isdigit() else None
        self.for_client = client
        self.fields['sites'].queryset = Site.objects.filter(client=client) if client else Site.objects.none()
        self.fields['sites'].required = False
        self.fields['description'].help_text = ''
        self.fields['included_hours'].help_text = '0 means no limit. Unused hours do not move to the next month.'
        self.fields['renewal_date'].help_text = 'Blank for no end date.'
        self.fields['price'].help_text = "In the client's currency."
        for name in ('price', 'overage_rate', 'included_hours'):
            self.fields[name].widget.attrs.update(min='0', step='0.01')
        _style(self)

    def clean(self):
        cleaned = super().clean()
        start, renewal = cleaned.get('start_date'), cleaned.get('renewal_date')
        if start and renewal and renewal < start:
            self.add_error('renewal_date', 'This is before the start date.')
        if cleaned.get('auto_renew') and renewal and not cleaned.get('term_months'):
            self.add_error('term_months', 'Say how many months a renewal adds.')
        sites = cleaned.get('sites')
        client = cleaned.get('client') or self.for_client
        if sites and client and any(site.client_id != client.pk for site in sites):
            self.add_error('sites', "Choose this client's sites.")
        return cleaned


class ServiceTypeForm(forms.ModelForm):
    class Meta:
        model = ServiceType
        fields = ['name', 'description', 'frequency', 'price', 'included_hours', 'overage_rate',
                  'checklist_title', 'checklist']
        labels = {
            'description': 'What it covers',
            'frequency': 'Billed',
            'price': 'Price per billing period',
            'included_hours': 'Hours included each month',
            'overage_rate': 'Price of an extra hour',
            'checklist_title': 'Monthly task',
            'checklist': 'Its sub-tasks',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'checklist': forms.Textarea(attrs={'rows': 5, 'placeholder': 'One per line, e.g. Update plugins'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('placeholder', 'Maintenance, Social media, Content, ...')
        self.fields['checklist'].help_text = (
            'A new service of this type gets a monthly recurring task with these sub-tasks. Blank: none.'
        )
        self.fields['price'].help_text = 'Filled in on a new service; each service can change it.'
        for name in ('price', 'overage_rate', 'included_hours'):
            self.fields[name].widget.attrs.update(min='0', step='0.01')
        _style(self)


class InvoicingForm(forms.Form):
    issue_date = forms.DateField(widget=DateInput(), label='First invoice on')
    payment_days = forms.IntegerField(min_value=0, max_value=365, initial=14, label='Days to pay')
    tax_rate = forms.DecimalField(min_value=0, max_value=100, decimal_places=2, initial=Decimal('0'),
                                  label='Tax rate (%)')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('issue_date', timezone.localdate())
        _style(self)


class ReportIntroForm(forms.ModelForm):
    class Meta:
        model = ServiceReport
        fields = ['introduction']
        widgets = {'introduction': forms.Textarea(attrs={'rows': 5})}
        labels = {'introduction': 'Introduction'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['introduction'].widget.attrs.update(placeholder='A few words for the client about this month.')
        _style(self)
