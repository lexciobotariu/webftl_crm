"""The client portal at /portal/, and the staff action that invites a contact to it.

A signed-in contact sees their client's projects (not cancelled), invoices and
estimates that were sent (not cancelled), and the emails sent to the client.
They can download the PDFs and accept or decline an estimate that is waiting
for an answer. Internal notes and drafts never reach the portal.
"""
import json

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import ClientContact, ClientMessage
from apps.crm.models import Company
from apps.invoices.estimates import record_answer
from apps.invoices.models import Estimate, Invoice
from apps.invoices.pdf import estimate_pdf, invoice_pdf, invoice_pdf_filename
from apps.projects.models import Project

from . import emails
from .access import (
    LINK_LIFETIME,
    contacts_for_email,
    current_contact,
    find_link,
    portal_login_required,
    sign_in,
    sign_out,
    use_link,
)

ANSWERS = ('accepted', 'declined')


class EmailForm(forms.Form):
    email = forms.EmailField()


def _context(request, **extra):
    company = Company.load()
    return {
        'company_name': company.legal_name or 'WebFTL CRM',
        'company_email': company.email,
        'portal_contact': getattr(request, 'portal_contact', None),
        **extra,
    }


def _invoices(client):
    return Invoice.objects.filter(client=client, sent_at__isnull=False, cancelled_at__isnull=True)


def _estimates(client):
    return Estimate.objects.filter(client=client, sent_at__isnull=False)


def login(request):
    if current_contact(request) is not None:
        return redirect('portal_home')
    sent = False
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            # The same answer whether or not the email has access, so the form
            # cannot be used to find out who the clients are.
            emails.send_login_links(request, contacts_for_email(form.cleaned_data['email']))
            sent = True
    else:
        form = EmailForm(initial={'email': request.GET.get('email', '')})
    return render(request, 'portal/login.html', _context(
        request, form=form, sent=sent, minutes=int(LINK_LIFETIME.total_seconds() // 60),
    ))


def link(request, token):
    """GET asks for a click and POST signs in, so a mail scanner opening the link does not spend it."""
    if request.method == 'POST':
        contact = use_link(token)
        if contact is not None:
            response = redirect('portal_home')
            sign_in(response, contact)
            return response
        found = None
    else:
        found = find_link(token)
    return render(request, 'portal/link.html', _context(request, link=found), status=200 if found else 410)


@require_POST
def logout(request):
    response = redirect('portal_login')
    sign_out(response)
    return response


@portal_login_required
def home(request):
    client = request.portal_client
    estimates = list(_estimates(client).select_related('project').prefetch_related('lines'))
    invoices = list(_invoices(client).select_related('project').prefetch_related('lines', 'payments'))
    projects = (
        Project.objects.filter(client=client)
        .exclude(status=Project.CANCELLED)
        .order_by('status', 'deadline', 'name')
    )
    return render(request, 'portal/home.html', _context(
        request,
        client=client,
        waiting=[estimate for estimate in estimates if estimate.status == 'sent'],
        estimates=estimates,
        invoices=invoices,
        to_pay=[invoice for invoice in invoices if invoice.balance > 0],
        projects=projects,
    ))


@portal_login_required
def messages(request):
    sent = ClientMessage.objects.filter(
        client=request.portal_client, kind=ClientMessage.EMAIL, error='',
    ).select_related('invoice', 'estimate')
    return render(request, 'portal/messages.html', _context(request, sent=sent))


@portal_login_required
def estimate_detail(request, pk):
    estimate = get_object_or_404(_estimates(request.portal_client), pk=pk)
    error = ''
    if request.method == 'POST':
        answer = request.POST.get('answer')
        if answer in ANSWERS and estimate.status == 'sent':
            try:
                record_answer(estimate, answer)
            except ValidationError as exc:
                error = exc.messages[0]
            else:
                emails.notify_estimate_answer(request, estimate, request.portal_contact, answer)
                return redirect('portal_estimate', pk=estimate.pk)
        else:
            error = 'This estimate can no longer be answered here. Please contact us.'
    return render(request, 'portal/estimate.html', _context(request, estimate=estimate, error=error))


def _pdf_response(content, document):
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{invoice_pdf_filename(document)}"'
    return response


@portal_login_required
def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(_invoices(request.portal_client), pk=pk)
    return _pdf_response(invoice_pdf(invoice), invoice)


@portal_login_required
def estimate_pdf_view(request, pk):
    estimate = get_object_or_404(_estimates(request.portal_client), pk=pk)
    return _pdf_response(estimate_pdf(estimate), estimate)


@login_required
@require_permission('access_clients')
@require_POST
def invite(request, pk, contact_pk):
    """Staff: email a contact with portal access how to sign in."""
    from apps.clients.views import _editable_client_or_error

    client, refused = _editable_client_or_error(request.user, pk)
    if refused:
        return refused
    contact = get_object_or_404(ClientContact, pk=contact_pk, client=client)
    if not contact.portal_access or not contact.email:
        return HttpResponse('Tick "Portal access" and add an email first.', status=400)
    if client.is_archived:
        return HttpResponse('This client is archived.', status=400)
    sent = emails.send_invite(request, contact, author=request.user)
    if sent.failed:
        return HttpResponse(f'The invite was not sent: {sent.error}', status=400)
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({'profileChanged': True})
    return response
