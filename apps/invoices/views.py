from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import visible_clients

from . import emails
from .forms import InvoiceEmailForm, InvoiceForm, InvoiceLineForm, PaymentForm
from .listing import PERIOD_CHOICES, STATUS_CHOICES, InvoiceFilters, filter_invoices
from .models import InvoiceHasPayments, InvoiceLocked, visible_invoices
from .pdf import invoice_pdf, invoice_pdf_filename
from .services import (
    add_line,
    cancel_invoice,
    create_invoice,
    delete_payment,
    mark_sent,
    record_payment,
    update_invoice,
    update_line,
)

INVOICES_PER_PAGE = 25


def _invoice_or_404(user, pk):
    """An invoice outside ``visible_invoices`` is a 404, including by id."""
    return get_object_or_404(visible_invoices(user), pk=pk)


def _redirect_to(url_name, *args):
    response = HttpResponse('')
    response['HX-Redirect'] = reverse(url_name, args=args)
    return response


def _sent_refusal(invoice):
    if invoice.sent_at is not None:
        return HttpResponseForbidden('This invoice has been sent.')
    return None


def _validation_message(exc):
    if hasattr(exc, 'messages') and exc.messages:
        return exc.messages[0]
    return 'This invoice could not be saved.'


@login_required
@require_permission('access_invoices')
def invoice_list(request):
    """Invoices filtered by ``status``, ``client`` and ``period``, paged, with totals per currency."""
    visible = visible_invoices(request.user)
    filters = InvoiceFilters.from_query(request.GET)
    rows, totals = filter_invoices(visible, filters)
    page_obj = Paginator(rows, INVOICES_PER_PAGE).get_page(request.GET.get('page', 1))
    return render(request, 'invoices/invoice_list.html', {
        'invoices': page_obj,
        'page_obj': page_obj,
        'total_count': len(rows),
        'has_invoices': bool(rows) or visible.exists(),
        'filters': filters,
        'totals': totals,
        'status_choices': STATUS_CHOICES,
        'period_choices': PERIOD_CHOICES,
        'client_choices': visible_clients(request.user).filter(
            pk__in=visible.values('client_id')
        ).order_by('name'),
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_create')
def invoice_create(request):
    initial = {}
    raw_client = request.GET.get('client')
    if request.method != 'POST' and raw_client and str(raw_client).isdigit():
        match = visible_clients(request.user).filter(pk=raw_client).first()
        if match is not None:
            initial['client'] = match.pk

    if request.method == 'POST':
        form = InvoiceForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                invoice = create_invoice(
                    client=form.cleaned_data['client'],
                    issue_date=form.cleaned_data['issue_date'],
                    due_date=form.cleaned_data['due_date'],
                    tax_rate=form.cleaned_data['tax_rate'],
                )
            except ValidationError as exc:
                form.add_error('client', _validation_message(exc))
            else:
                return _redirect_to('invoice_detail', invoice.pk)
    else:
        form = InvoiceForm(user=request.user, initial=initial)

    return render(request, 'invoices/partials/invoice_drawer.html', {
        'form': form,
        'invoice': None,
    })


@login_required
@require_permission('access_invoices')
def invoice_detail(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    return render(request, 'invoices/invoice_detail.html', {
        'invoice': invoice,
        'can_email': emails.can_email(invoice, emails.INVOICE),
        'can_remind': emails.can_email(invoice, emails.REMINDER),
        'sent_emails': invoice.emails.select_related('author'),
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def invoice_edit(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    refused = _sent_refusal(invoice)
    if refused:
        return refused

    if request.method == 'POST':
        form = InvoiceForm(request.POST, user=request.user, current_client_id=invoice.client_id)
        if form.is_valid():
            try:
                update_invoice(
                    invoice,
                    client=form.cleaned_data['client'],
                    issue_date=form.cleaned_data['issue_date'],
                    due_date=form.cleaned_data['due_date'],
                    tax_rate=form.cleaned_data['tax_rate'],
                )
            except InvoiceLocked:
                return HttpResponseForbidden('This invoice has been sent.')
            except ValidationError as exc:
                form.add_error(None, _validation_message(exc))
            else:
                return _redirect_to('invoice_detail', invoice.pk)
    else:
        form = InvoiceForm(
            user=request.user,
            current_client_id=invoice.client_id,
            initial={
                'client': invoice.client_id,
                'issue_date': invoice.issue_date,
                'due_date': invoice.due_date,
                'tax_rate': invoice.tax_rate,
            },
        )

    return render(request, 'invoices/partials/invoice_drawer.html', {
        'form': form,
        'invoice': invoice,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def invoice_mark_sent(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    if invoice.sent_at is not None:
        return HttpResponse('This invoice has already been sent.', status=400)
    try:
        mark_sent(invoice)
    except ValidationError as exc:
        return HttpResponse(_validation_message(exc), status=400)
    return _redirect_to('invoice_detail', invoice.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def invoice_cancel(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    try:
        cancel_invoice(invoice)
    except ValidationError as exc:
        return HttpResponse(_validation_message(exc), status=400)
    return _redirect_to('invoice_detail', invoice.pk)


@login_required
@require_permission('access_invoices')
@require_POST
def invoice_delete(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    if not request.user.is_admin:
        return HttpResponseForbidden('Admin access required')
    try:
        invoice.delete()
    except InvoiceHasPayments:
        return HttpResponse('This invoice has payments.', status=400)
    if request.htmx:
        return _redirect_to('invoice_list')
    return redirect('invoice_list')


@login_required
@require_permission('access_invoices')
def invoice_print(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    return render(request, 'invoices/invoice_print.html', {
        'invoice': invoice,
    })


@login_required
@require_permission('access_invoices')
def invoice_pdf_download(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    response = HttpResponse(invoice_pdf(invoice), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice_pdf_filename(invoice)}"'
    return response


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def invoice_email(request, pk, kind):
    """Email the invoice (``kind='invoice'``) or a reminder about it, with the PDF attached."""
    invoice = _invoice_or_404(request.user, pk)
    if kind not in emails.KINDS:
        return HttpResponse('Unknown email.', status=404)
    if not emails.can_email(invoice, kind):
        message = 'Only an invoice that is still owed gets a reminder.' if kind == emails.REMINDER else (
            'This invoice has been cancelled.'
        )
        return HttpResponse(message, status=400)

    sent = None
    if request.method == 'POST':
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            try:
                sent = emails.send_invoice_email(
                    invoice,
                    kind=kind,
                    to=form.cleaned_data['to'],
                    subject=form.cleaned_data['subject'],
                    message=form.cleaned_data['message'],
                    author=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, _validation_message(exc))
            else:
                if not sent.failed:
                    return _redirect_to('invoice_detail', invoice.pk)
                form.add_error(None, f'The email was not sent: {sent.error}')
    else:
        form = InvoiceEmailForm(initial={
            'to': emails.default_recipient(invoice),
            'subject': emails.default_subject(invoice, kind),
            'message': emails.default_message(invoice, kind),
        })
    return render(request, 'invoices/partials/email_drawer.html', {
        'form': form,
        'invoice': invoice,
        'kind': kind,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def line_create(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    refused = _sent_refusal(invoice)
    if refused:
        return refused
    return _line_form(request, invoice, line=None)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def line_edit(request, pk, line_pk):
    invoice = _invoice_or_404(request.user, pk)
    refused = _sent_refusal(invoice)
    if refused:
        return refused
    line = get_object_or_404(invoice.lines, pk=line_pk)
    return _line_form(request, invoice, line=line)


def _line_form(request, invoice, *, line):
    current_project_id = line.project_id if line is not None else None
    if request.method == 'POST':
        form = InvoiceLineForm(request.POST, invoice=invoice, current_project_id=current_project_id)
        if form.is_valid():
            payload = {
                'project': form.cleaned_data['project'],
                'description': form.cleaned_data['description'],
                'quantity': form.cleaned_data['quantity'],
                'unit_price': form.cleaned_data['unit_price'],
            }
            try:
                if line is None:
                    add_line(invoice, **payload)
                else:
                    update_line(line, **payload)
            except InvoiceLocked:
                return HttpResponseForbidden('This invoice has been sent.')
            except ValidationError as exc:
                form.add_error(None, _validation_message(exc))
            else:
                return _redirect_to('invoice_detail', invoice.pk)
    elif line is None:
        form = InvoiceLineForm(invoice=invoice)
    else:
        form = InvoiceLineForm(
            invoice=invoice,
            current_project_id=current_project_id,
            initial={
                'project': line.project_id,
                'description': line.description,
                'quantity': line.quantity,
                'unit_price': line.unit_price,
            },
        )
    return render(request, 'invoices/partials/line_drawer.html', {
        'form': form,
        'invoice': invoice,
        'line': line,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def line_delete(request, pk, line_pk):
    invoice = _invoice_or_404(request.user, pk)
    refused = _sent_refusal(invoice)
    if refused:
        return refused
    line = get_object_or_404(invoice.lines, pk=line_pk)
    try:
        line.delete()
    except InvoiceLocked:
        return HttpResponseForbidden('This invoice has been sent.')
    return _redirect_to('invoice_detail', invoice.pk)


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
def payment_create(request, pk):
    invoice = _invoice_or_404(request.user, pk)
    if invoice.sent_at is None:
        return HttpResponse('Mark the invoice sent before recording a payment.', status=400)
    if invoice.cancelled_at is not None:
        return HttpResponse('This invoice has been cancelled.', status=400)
    if request.method == 'POST':
        form = PaymentForm(request.POST, invoice=invoice)
        if form.is_valid():
            try:
                record_payment(
                    invoice,
                    date=form.cleaned_data['date'],
                    amount=form.cleaned_data['amount'],
                    note=form.cleaned_data['note'],
                )
            except ValidationError as exc:
                messages = getattr(exc, 'message_dict', {}).get('amount')
                form.add_error('amount', messages[0] if messages else _validation_message(exc))
            else:
                return _redirect_to('invoice_detail', invoice.pk)
    else:
        form = PaymentForm(invoice=invoice)
    return render(request, 'invoices/partials/payment_drawer.html', {
        'form': form,
        'invoice': invoice,
    })


@login_required
@require_permission('access_invoices')
@require_permission('invoices_edit')
@require_POST
def payment_delete(request, pk, payment_pk):
    invoice = _invoice_or_404(request.user, pk)
    payment = get_object_or_404(invoice.payments, pk=payment_pk)
    delete_payment(payment)
    return _redirect_to('invoice_detail', invoice.pk)
