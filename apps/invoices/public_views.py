"""The estimate's online page (apps/invoices/public.py): view, PDF, accept or decline. No login."""
from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_deny

from apps.crm.models import Company

from . import public
from .estimates import record_answer
from .pdf import estimate_pdf, invoice_pdf_filename


class AcceptForm(forms.Form):
    name = forms.CharField(max_length=255, error_messages={'required': 'Type your full name to accept.'})
    agree = forms.BooleanField(error_messages={'required': 'Tick the box to accept.'})

    def clean_name(self):
        name = ' '.join(self.cleaned_data['name'].split())
        if len(name) < 2:
            raise forms.ValidationError('Type your full name to accept.')
        return name


def _estimate_or_404(pk, token):
    estimate = public.find(pk, token)
    if estimate is None:
        raise Http404('This link does not work. Ask us for a new one.')
    return estimate


def _context(estimate, **extra):
    company = Company.load()
    return {
        'estimate': estimate,
        'invoice': estimate,  # the money partial reads the currency from ``invoice``
        'company_name': estimate.company_legal_name or company.legal_name or 'WebFTL CRM',
        'company_email': estimate.company_email or company.email,
        **extra,
    }


@never_cache
@xframe_options_deny
def estimate_public(request, pk, token):
    estimate = _estimate_or_404(pk, token)
    form = AcceptForm()
    error = ''
    if request.method == 'POST':
        answer = request.POST.get('answer')
        if estimate.status != 'sent':
            error = 'This estimate can no longer be answered here. Please contact us.'
        elif answer == 'accepted':
            form = AcceptForm(request.POST)
            if form.is_valid():
                error = _answer(request, estimate, 'accepted', form.cleaned_data['name'])
                if not error:
                    return redirect(request.path)
        elif answer == 'declined':
            name = ' '.join(request.POST.get('name', '').split())[:255]
            error = _answer(request, estimate, 'declined', name)
            if not error:
                return redirect(request.path)
        else:
            error = 'Choose Accept or Decline.'
    status = 400 if error or form.errors else 200
    return render(request, 'invoices/public_estimate.html', _context(estimate, form=form, error=error), status=status)


def _answer(request, estimate, answer, name):
    try:
        record_answer(estimate, answer, name=name, ip=public.client_ip(request))
    except ValidationError as exc:
        return exc.messages[0]
    public.notify_answer(request, estimate, answer, name)
    return ''


@never_cache
def estimate_public_pdf(request, pk, token):
    estimate = _estimate_or_404(pk, token)
    response = HttpResponse(estimate_pdf(estimate), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{invoice_pdf_filename(estimate)}"'
    return response
