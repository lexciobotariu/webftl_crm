from datetime import timedelta
from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.clients.models import Client, visible_clients
from apps.projects.models import Project

from .models import RecurringInvoice, money

INPUT_CLASSES = (
    'w-full bg-elevated border border-border-subtle rounded-control px-3 py-2 text-sm '
    'text-zinc-100 placeholder-zinc-500 focus:border-border-strong focus:ring-1 '
    'focus:ring-border-strong focus:outline-none'
)


class HtmlDateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', '%Y-%m-%d')
        kwargs.setdefault('attrs', {})
        kwargs['attrs'].setdefault('class', INPUT_CLASSES)
        super().__init__(*args, **kwargs)


class InvoiceForm(forms.Form):
    client = forms.ModelChoiceField(queryset=Client.objects.none())
    issue_date = forms.DateField(
        input_formats=['%Y-%m-%d'],
        widget=HtmlDateInput(),
    )
    due_date = forms.DateField(
        input_formats=['%Y-%m-%d'],
        widget=HtmlDateInput(),
    )
    tax_rate = forms.DecimalField(
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        decimal_places=2,
        max_digits=5,
        initial=Decimal('0.00'),
    )

    def __init__(self, *args, user, current_client_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Archived clients are not offered, except the one a draft already has.
        clients = visible_clients(user).filter(
            Q(archived_at__isnull=True) | Q(pk=current_client_id)
        )
        self.fields['client'].queryset = clients.order_by('name')
        self.fields['client'].empty_label = 'Select a client'
        if not self.is_bound and 'issue_date' not in self.initial:
            today = timezone.localdate()
            self.initial.setdefault('issue_date', today)
            self.initial.setdefault('due_date', today + timedelta(days=30))
            self.initial.setdefault('tax_rate', Decimal('0.00'))

    def clean_tax_rate(self):
        return money(self.cleaned_data['tax_rate'])


class InvoiceLineForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), required=False)
    description = forms.CharField(max_length=255, required=False)
    quantity = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        max_digits=10,
    )
    unit_price = forms.DecimalField(
        min_value=Decimal('0'),
        decimal_places=2,
        max_digits=12,
    )

    def __init__(self, *args, invoice, current_project_id=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        # Open projects only, plus the one this line already names: a project
        # finished before its invoice is written keeps its line.
        offered = Q(status__in=Project.OPEN_STATUSES)
        if current_project_id:
            offered |= Q(pk=current_project_id)
        self.fields['project'].queryset = invoice.client.projects.filter(offered).order_by('name')
        self.fields['project'].empty_label = 'Free-text line'

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get('project')
        description = (cleaned.get('description') or '').strip()
        if project and project.client_id != self.invoice.client_id:
            self.add_error('project', 'Choose a project that belongs to this client.')
        elif project:
            cleaned['description'] = project.name
        elif not description:
            self.add_error('description', 'Enter a description for a free-text line.')
        else:
            cleaned['description'] = description
        return cleaned


class PaymentForm(forms.Form):
    date = forms.DateField(
        input_formats=['%Y-%m-%d'],
        widget=HtmlDateInput(),
    )
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        max_digits=12,
    )
    note = forms.CharField(required=False)

    def __init__(self, *args, invoice, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        if not self.is_bound and 'date' not in self.initial:
            self.initial['date'] = timezone.localdate()

    def clean_amount(self):
        amount = money(self.cleaned_data['amount'])
        if amount > self.invoice.balance:
            raise forms.ValidationError('Amount cannot exceed the balance.')
        return amount


MAX_RECIPIENTS = 10


class InvoiceEmailForm(forms.Form):
    to = forms.CharField(max_length=500)
    subject = forms.CharField(max_length=255)
    message = forms.CharField(widget=forms.Textarea)

    def clean_to(self):
        """One or more addresses, separated by commas or semicolons."""
        from django.core.validators import validate_email

        addresses = [part.strip() for part in self.cleaned_data['to'].replace(';', ',').split(',') if part.strip()]
        if not addresses:
            raise forms.ValidationError('Enter at least one email address.')
        if len(addresses) > MAX_RECIPIENTS:
            raise forms.ValidationError(f'Send to at most {MAX_RECIPIENTS} addresses.')
        for address in addresses:
            try:
                validate_email(address)
            except forms.ValidationError:
                raise forms.ValidationError(f'"{address}" is not a valid email address.') from None
        return list(dict.fromkeys(addresses))


class RecurringInvoiceForm(forms.Form):
    frequency = forms.ChoiceField(choices=RecurringInvoice.FREQUENCY_CHOICES)
    next_date = forms.DateField(widget=HtmlDateInput(), label='Next draft on')
    end_date = forms.DateField(widget=HtmlDateInput(), required=False, label='Last draft on or before')
