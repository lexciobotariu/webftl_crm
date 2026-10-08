from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import visible_clients

from .forms import InvoiceForm, InvoiceLineForm, PaymentForm
from .models import InvoiceHasPayments, InvoiceLocked, visible_invoices
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
    invoices = visible_invoices(request.user)
    return render(request, 'invoices/invoice_list.html', {
        'invoices': invoices,
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
