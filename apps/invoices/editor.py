"""The inline editor for a draft invoice or estimate.

The header (client, project, dates, tax) and every line are edited in place on
the document's page. Each change is saved as it is made: a header change or a
line edit answers with the new amounts swapped in out of band, so the field
being typed in keeps its focus; adding or removing a line redraws the lines.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .estimates import (
    EstimateLocked,
    add_estimate_line,
    delete_estimate_line,
    update_estimate,
    update_estimate_line,
)
from .forms import EstimateForm, InvoiceForm
from .models import InvoiceLocked, visible_estimates, visible_invoices
from .services import add_line, update_invoice, update_line

INVOICE = 'invoice'
ESTIMATE = 'estimate'


class LineForm(forms.Form):
    """One line as typed in the table. A project line may leave the description empty."""

    description = forms.CharField(max_length=255, required=False)
    quantity = forms.DecimalField(min_value=Decimal('0.01'), decimal_places=2, max_digits=10)
    unit_price = forms.DecimalField(min_value=Decimal('0'), decimal_places=2, max_digits=12)

    def __init__(self, *args, line=None, **kwargs):
        self.line = line
        super().__init__(*args, **kwargs)

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        if not description and not (self.line and self.line.project_id):
            raise forms.ValidationError('Enter a description.')
        return description


def _document_or_404(user, kind, pk):
    documents = visible_estimates(user) if kind == ESTIMATE else visible_invoices(user)
    return get_object_or_404(documents, pk=pk)


def _url(kind, name, *args):
    return reverse(f'{kind}_{name}', args=args)


def editor_context(document, kind, **extra):
    """What the editor partials need: the document, its rows with their URLs, and the header URL."""
    rows = [
        {
            'line': line,
            'update_url': _url(kind, 'line_edit', document.pk, line.pk),
            'delete_url': _url(kind, 'line_delete', document.pk, line.pk),
        }
        for line in document.lines.select_related('project')
    ]
    return {
        'doc': document,
        'invoice': document,  # the money partial reads the currency from ``invoice``
        'kind': kind,
        'rows': rows,
        'header_url': _url(kind, 'header', document.pk),
        'create_url': _url(kind, 'line_create', document.pk),
        **extra,
    }


def header_form(user, document, kind, data=None):
    form_class = EstimateForm if kind == ESTIMATE else InvoiceForm
    initial = {
        'client': document.client_id,
        'project': document.project_id,
        'issue_date': document.issue_date,
        'tax_rate': document.tax_rate,
    }
    if kind == ESTIMATE:
        initial.update(valid_until=document.valid_until, notes=document.notes)
    else:
        initial['due_date'] = document.due_date
    return form_class(
        data, user=user, initial=initial,
        current_client_id=document.client_id, current_project_id=document.project_id,
    )


def _refused(document):
    if not document.is_draft:
        return HttpResponseForbidden(f'This {document._meta.verbose_name} has been sent.')
    return None


def _render_totals_and(request, document, kind, template, **extra):
    """``template`` plus the totals swapped in out of band."""
    fresh = type(document).objects.get(pk=document.pk)
    return render(request, template, editor_context(fresh, kind, oob_totals=True, **extra))


def header(request, kind, pk):
    """Save the header as it changes. A new client reloads the page: its bill-to, currency and projects differ."""
    document = _document_or_404(request.user, kind, pk)
    refused = _refused(document)
    if refused:
        return refused
    data = request.POST.copy()
    client_changed = data.get('client') != str(document.client_id)
    if client_changed:
        data['project'] = ''
    form = header_form(request.user, document, kind, data)
    if form.is_valid():
        values = {key: form.cleaned_data[key] for key in ('client', 'project', 'issue_date', 'tax_rate')}
        try:
            if kind == ESTIMATE:
                update_estimate(document, valid_until=form.cleaned_data['valid_until'],
                                notes=form.cleaned_data['notes'], **values)
            else:
                update_invoice(document, due_date=form.cleaned_data['due_date'], **values)
        except (InvoiceLocked, EstimateLocked):
            return HttpResponseForbidden('This document has been sent.')
        except ValidationError as exc:
            for field, messages in getattr(exc, 'message_dict', {None: exc.messages}).items():
                form.add_error(field if field in form.fields else None, messages[0])
        else:
            if client_changed:
                response = HttpResponse('')
                response['HX-Refresh'] = 'true'
                return response
            document = type(document).objects.get(pk=document.pk)
            form = header_form(request.user, document, kind)
    return _render_totals_and(request, document, kind, 'invoices/partials/editor_header.html', form=form)


def line_create(request, kind, pk):
    document = _document_or_404(request.user, kind, pk)
    refused = _refused(document)
    if refused:
        return refused
    if request.method != 'POST':
        return HttpResponse(status=405)
    form = LineForm(request.POST)
    if form.is_valid():
        values = {**form.cleaned_data, 'project': None}
        try:
            if kind == ESTIMATE:
                add_estimate_line(document, **values)
            else:
                add_line(document, **values)
        except (InvoiceLocked, EstimateLocked):
            return HttpResponseForbidden('This document has been sent.')
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            return _render_totals_and(request, document, kind, 'invoices/partials/editor_lines.html',
                                      focus_new=True)
    return _render_totals_and(request, document, kind, 'invoices/partials/editor_lines.html',
                              new_form=form, focus_new=True)


def line_edit(request, kind, pk, line_pk):
    """Save one line. Answers only out of band (amount, totals, error) so the cursor stays put."""
    document = _document_or_404(request.user, kind, pk)
    refused = _refused(document)
    if refused:
        return refused
    if request.method != 'POST':
        return HttpResponse(status=405)
    line = get_object_or_404(document.lines, pk=line_pk)
    form = LineForm(request.POST, line=line)
    error = ''
    if form.is_valid():
        values = {**form.cleaned_data, 'project': line.project}
        try:
            line = update_estimate_line(line, **values) if kind == ESTIMATE else update_line(line, **values)
        except (InvoiceLocked, EstimateLocked):
            return HttpResponseForbidden('This document has been sent.')
        except ValidationError as exc:
            error = exc.messages[0]
    else:
        error = next(iter(form.errors.values()))[0]
    return _render_totals_and(request, document, kind, 'invoices/partials/editor_line_saved.html',
                              saved_line=line, error=error)


def line_delete(request, kind, pk, line_pk):
    document = _document_or_404(request.user, kind, pk)
    refused = _refused(document)
    if refused:
        return refused
    if request.method != 'POST':
        return HttpResponse(status=405)
    line = get_object_or_404(document.lines, pk=line_pk)
    try:
        delete_estimate_line(line) if kind == ESTIMATE else line.delete()
    except (InvoiceLocked, EstimateLocked):
        return HttpResponseForbidden('This document has been sent.')
    return _render_totals_and(request, document, kind, 'invoices/partials/editor_lines.html')
