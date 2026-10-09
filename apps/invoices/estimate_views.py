"""Estimates: list, create, edit while a draft, send, record the answer, turn into an invoice.

They use the invoices module's permissions: ``access_invoices`` to see them,
``invoices_create`` to create one or turn it into an invoice, ``invoices_edit``
to change, send and record answers. Visibility follows ``visible_invoices``.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import visible_clients

from . import emails
from .estimates import (
    EstimateLocked,
    add_estimate_line,
    convert_to_invoice,
    create_estimate,
    delete_estimate_line,
    mark_estimate_sent,
    record_answer,
    update_estimate,
    update_estimate_line,
)
from .forms import EstimateForm, InvoiceEmailForm, InvoiceLineForm
from .pdf import estimate_pdf, invoice_pdf_filename
from .views import _redirect_to, _validation_message

ESTIMATES_PER_PAGE = 25
STATUS_CHOICES = (
    ('', 'All statuses'),
    ('draft', 'Draft'),
    ('sent', 'Sent'),
    ('accepted', 'Accepted'),
    ('declined', 'Declined'),
    ('expired', 'Expired'),
    ('invoiced', 'Invoiced'),
)


def _estimate_or_404(user, pk):
    from .models import visible_estimates

    return get_object_or_404(visible_estimates(user), pk=pk)


def _draft_refusal(estimate):
    if not estimate.is_draft:
        return HttpResponseForbidden('This estimate has been sent.')
    return None


def _form_errors(form, exc):
    if hasattr(exc, 'message_dict'):
        for field, messages in exc.message_dict.items():
            form.add_error(field if field in form.fields else None, messages[0])
    else:
        form.add_error(None, _validation_message(exc))


@login_required
@require_permission('access_invoices')
def estimate_list(request):
    from .models import visible_estimates

    visible = visible_estimates(request.user)
    status = request.GET.get('status', '')
    if status not in dict(STATUS_CHOICES):
        status = ''
    rows = [estimate for estimate in visible if not status or estimate.status == status]
    page_obj = Paginator(rows, ESTIMATES_PER_PAGE).get_page(request.GET.get('page', 1))
    return render(request, 'invoices/estimate_list.html', {
        'estimates': page_obj,
        'page_obj': page_obj,
        'total_count': len(rows),
        'has_estimates': bool(rows) or visible.exists(),
        'status': status,
        'status_choices': STATUS_CHOICES,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_create')
def estimate_create(request):
    initial = {}
    raw_client = request.GET.get('client', '')
    if request.method != 'POST' and raw_client.isdigit():
        match = visible_clients(request.user).filter(pk=raw_client).first()
        if match is not None:
            initial['client'] = match.pk

    if request.method == 'POST':
        form = EstimateForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                estimate = create_estimate(
                    client=form.cleaned_data['client'],
                    issue_date=form.cleaned_data['issue_date'],
                    valid_until=form.cleaned_data['valid_until'],
                    tax_rate=form.cleaned_data['tax_rate'],
                    notes=form.cleaned_data['notes'],
                )
            except ValidationError as exc:
                _form_errors(form, exc)
            else:
                return _redirect_to('estimate_detail', estimate.pk)
    else:
        form = EstimateForm(user=request.user, initial=initial)
    return render(request, 'invoices/partials/estimate_drawer.html', {'form': form, 'estimate': None})


@login_required
@require_permission('access_invoices')
def estimate_detail(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    return render(request, 'invoices/estimate_detail.html', {
        'estimate': estimate,
        'invoice': estimate,  # the money partial reads the currency from ``invoice``
        'can_email': emails.can_email(estimate, emails.ESTIMATE),
        'sent_emails': estimate.emails.select_related('author'),
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def estimate_edit(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    refused = _draft_refusal(estimate)
    if refused:
        return refused
    if request.method == 'POST':
        form = EstimateForm(request.POST, user=request.user, current_client_id=estimate.client_id)
        if form.is_valid():
            try:
                update_estimate(estimate, **{key: form.cleaned_data[key] for key in (
                    'client', 'issue_date', 'valid_until', 'tax_rate', 'notes')})
            except EstimateLocked:
                return HttpResponseForbidden('This estimate has been sent.')
            except ValidationError as exc:
                _form_errors(form, exc)
            else:
                return _redirect_to('estimate_detail', estimate.pk)
    else:
        form = EstimateForm(user=request.user, current_client_id=estimate.client_id, initial={
            'client': estimate.client_id,
            'issue_date': estimate.issue_date,
            'valid_until': estimate.valid_until,
            'tax_rate': estimate.tax_rate,
            'notes': estimate.notes,
        })
    return render(request, 'invoices/partials/estimate_drawer.html', {'form': form, 'estimate': estimate})


@login_required
@require_permission('access_invoices')
@require_POST
def estimate_delete(request, pk):
    """Admins delete an estimate that has not been turned into an invoice."""
    estimate = _estimate_or_404(request.user, pk)
    if not request.user.is_admin:
        return HttpResponseForbidden('Admin access required')
    if estimate.invoice_id:
        return HttpResponse('This estimate has been invoiced.', status=400)
    estimate.delete()
    return _redirect_to('estimate_list')


def _line_form(request, estimate, *, line):
    action_url = (
        reverse('estimate_line_edit', args=[estimate.pk, line.pk]) if line
        else reverse('estimate_line_create', args=[estimate.pk])
    )
    current_project_id = line.project_id if line else None
    if request.method == 'POST':
        form = InvoiceLineForm(request.POST, invoice=estimate, current_project_id=current_project_id)
        if form.is_valid():
            payload = {key: form.cleaned_data[key] for key in ('project', 'description', 'quantity', 'unit_price')}
            try:
                if line is None:
                    add_estimate_line(estimate, **payload)
                else:
                    update_estimate_line(line, **payload)
            except EstimateLocked:
                return HttpResponseForbidden('This estimate has been sent.')
            except ValidationError as exc:
                _form_errors(form, exc)
            else:
                return _redirect_to('estimate_detail', estimate.pk)
    elif line:
        form = InvoiceLineForm(invoice=estimate, current_project_id=current_project_id, initial={
            'project': line.project_id,
            'description': '' if line.project_id else line.description,
            'quantity': line.quantity,
            'unit_price': line.unit_price,
        })
    else:
        form = InvoiceLineForm(invoice=estimate, initial={'quantity': 1})
    return render(request, 'invoices/partials/line_drawer.html', {
        'form': form,
        'invoice': estimate,
        'line': line,
        'action_url': action_url,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def estimate_line_create(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    return _draft_refusal(estimate) or _line_form(request, estimate, line=None)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def estimate_line_edit(request, pk, line_pk):
    estimate = _estimate_or_404(request.user, pk)
    line = get_object_or_404(estimate.lines, pk=line_pk)
    return _draft_refusal(estimate) or _line_form(request, estimate, line=line)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_line_delete(request, pk, line_pk):
    estimate = _estimate_or_404(request.user, pk)
    line = get_object_or_404(estimate.lines, pk=line_pk)
    try:
        delete_estimate_line(line)
    except EstimateLocked:
        return HttpResponseForbidden('This estimate has been sent.')
    return _redirect_to('estimate_detail', estimate.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_mark_sent(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    try:
        mark_estimate_sent(estimate)
    except ValidationError as exc:
        return HttpResponse(_validation_message(exc), status=400)
    return _redirect_to('estimate_detail', estimate.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_answer(request, pk, answer):
    estimate = _estimate_or_404(request.user, pk)
    if answer not in ('accepted', 'declined', 'open'):
        return HttpResponse('Unknown answer.', status=404)
    try:
        record_answer(estimate, answer)
    except ValidationError as exc:
        return HttpResponse(_validation_message(exc), status=400)
    return _redirect_to('estimate_detail', estimate.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_create')
@require_POST
def estimate_convert(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    try:
        invoice = convert_to_invoice(estimate)
    except ValidationError as exc:
        return HttpResponse(_validation_message(exc), status=400)
    return _redirect_to('invoice_detail', invoice.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def estimate_email(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    if not emails.can_email(estimate, emails.ESTIMATE):
        return HttpResponse('This estimate already has an answer.', status=400)
    if request.method == 'POST':
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            try:
                sent = emails.send_invoice_email(
                    estimate, kind=emails.ESTIMATE, author=request.user,
                    **{key: form.cleaned_data[key] for key in ('to', 'subject', 'message')},
                )
            except ValidationError as exc:
                form.add_error(None, _validation_message(exc))
            else:
                if not sent.failed:
                    return _redirect_to('estimate_detail', estimate.pk)
                form.add_error(None, f'The email was not sent: {sent.error}')
    else:
        form = InvoiceEmailForm(initial={
            'to': emails.default_recipient(estimate),
            'subject': emails.default_subject(estimate, emails.ESTIMATE),
            'message': emails.default_message(estimate, emails.ESTIMATE),
        })
    return render(request, 'invoices/partials/email_drawer.html', {
        'form': form,
        'invoice': estimate,
        'kind': emails.ESTIMATE,
        'action_url': reverse('estimate_email', args=[estimate.pk]),
    })


@login_required
@require_permission('access_invoices')
def estimate_print(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    return render(request, 'invoices/estimate_print.html', {'estimate': estimate, 'invoice': estimate})


@login_required
@require_permission('access_invoices')
def estimate_pdf_download(request, pk):
    estimate = _estimate_or_404(request.user, pk)
    response = HttpResponse(estimate_pdf(estimate), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice_pdf_filename(estimate)}"'
    return response
