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

from . import editor, emails
from .estimates import (
    EstimateLocked,
    convert_to_invoice,
    create_estimate,
    mark_estimate_sent,
    record_answer,
    update_estimate,
)
from .forms import EstimateForm, InvoiceEmailForm
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
    raw_project = request.GET.get('project', '')
    if request.method != 'POST' and raw_project.isdigit():
        from apps.projects.models import Project

        project = Project.objects.filter(pk=raw_project, client__in=visible_clients(request.user)).first()
        if project is not None:
            initial.update(client=project.client_id, project=project.pk)

    if request.method == 'POST':
        form = EstimateForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                estimate = create_estimate(
                    client=form.cleaned_data['client'],
                    project=form.cleaned_data['project'],
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
    context = {}
    if estimate.is_draft and request.user.has_app_permission('invoices_edit'):
        context = editor.editor_context(
            estimate, editor.ESTIMATE, editor=True,
            form=editor.header_form(request.user, estimate, editor.ESTIMATE),
        )
    return render(request, 'invoices/estimate_detail.html', {
        **context,
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
        form = EstimateForm(request.POST, user=request.user, current_client_id=estimate.client_id,
                            current_project_id=estimate.project_id)
        if form.is_valid():
            try:
                update_estimate(estimate, **{key: form.cleaned_data[key] for key in (
                    'client', 'project', 'issue_date', 'valid_until', 'tax_rate', 'notes')})
            except EstimateLocked:
                return HttpResponseForbidden('This estimate has been sent.')
            except ValidationError as exc:
                _form_errors(form, exc)
            else:
                return _redirect_to('estimate_detail', estimate.pk)
    else:
        form = EstimateForm(user=request.user, current_client_id=estimate.client_id,
                            current_project_id=estimate.project_id, initial={
            'client': estimate.client_id,
            'project': estimate.project_id,
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


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_header(request, pk):
    return editor.header(request, editor.ESTIMATE, pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_line_create(request, pk):
    return editor.line_create(request, editor.ESTIMATE, pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_line_edit(request, pk, line_pk):
    return editor.line_edit(request, editor.ESTIMATE, pk, line_pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def estimate_line_delete(request, pk, line_pk):
    return editor.line_delete(request, editor.ESTIMATE, pk, line_pk)


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
