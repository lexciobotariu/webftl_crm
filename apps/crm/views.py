from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_admin

from .forms import CompanyForm, CurrencyForm
from .models import Company, Currency


def _settings_page(request, company_form, currency_form, currency_error='', status=200):
    return render(
        request,
        'crm/settings.html',
        {
            'company_form': company_form,
            'currency_form': currency_form,
            'currencies': Currency.objects.order_by('code'),
            'currency_error': currency_error,
        },
        status=status,
    )


@login_required
@require_admin
def settings_page(request):
    company = Company.load()
    if request.method == 'POST':
        company_form = CompanyForm(request.POST, instance=company)
        if company_form.is_valid():
            company_form.save()
            return redirect('settings')
    else:
        company_form = CompanyForm(instance=company)
    return _settings_page(request, company_form, CurrencyForm())


@login_required
@require_admin
@require_POST
def currency_add(request):
    currency_form = CurrencyForm(request.POST)
    if currency_form.is_valid():
        currency_form.save()
        return redirect('settings')
    return _settings_page(
        request,
        CompanyForm(instance=Company.load()),
        currency_form,
    )


@login_required
@require_admin
@require_POST
def currency_delete(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    if currency.clients.exists():
        return _settings_page(
            request,
            CompanyForm(instance=Company.load()),
            CurrencyForm(),
            currency_error='This currency is used by a client.',
            status=400,
        )
    try:
        currency.delete()
    except ProtectedError:
        return _settings_page(
            request,
            CompanyForm(instance=Company.load()),
            CurrencyForm(),
            currency_error='This currency is used by a client.',
            status=400,
        )
    return redirect('settings')
