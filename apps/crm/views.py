from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_admin

from .forms import BankAccountForm, CompanyForm, CurrencyForm, StorageForm, ThemeForm
from .models import BankAccount, Company, Currency


def _settings_page(
    request, company_form, currency_form, currency_error='', status=200, theme_form=None,
    storage_form=None,
):
    if theme_form is None:
        theme_form = ThemeForm(instance=Company.load())
    if storage_form is None:
        storage_form = StorageForm(instance=Company.load())
    return render(
        request,
        'crm/settings.html',
        {
            'company_form': company_form,
            'theme_form': theme_form,
            'storage_form': storage_form,
            'files_on_disk_in_production': (
                not settings.DEBUG
                and not Company.load().uses_s3
            ),
            'currency_form': currency_form,
            'currencies': Currency.objects.order_by('code'),
            'currency_error': currency_error,
            'bank_accounts': BankAccount.objects.select_related('currency').annotate(
                invoice_count=Count('invoices'),
            ).order_by('archived_at', 'label', 'pk'),
        },
        status=status,
    )


@login_required
@require_admin
def settings_page(request):
    company = Company.load()
    if request.method == 'POST' and 'theme' in request.POST:
        theme_form = ThemeForm(request.POST, instance=company)
        if theme_form.is_valid():
            theme_form.save()
            return redirect('settings')
        return _settings_page(
            request,
            CompanyForm(instance=Company.load()),
            CurrencyForm(),
            theme_form=theme_form,
        )
    if request.method == 'POST' and 'storage_backend' in request.POST:
        storage_form = StorageForm(request.POST, instance=company)
        if storage_form.is_valid():
            storage_form.save()
            return redirect('settings')
        return _settings_page(
            request,
            CompanyForm(instance=Company.load()),
            CurrencyForm(),
            storage_form=storage_form,
            status=400,
        )
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
    if currency.bank_accounts.exists():
        return _settings_page(
            request,
            CompanyForm(instance=Company.load()),
            CurrencyForm(),
            currency_error='This currency is used by a bank account.',
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


def _bank_account_page(request, form, account=None, status=200):
    return render(
        request, 'crm/bank_account_form.html',
        {'form': form, 'account': account}, status=status,
    )


@login_required
@require_admin
def bank_account_add(request):
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('settings')}#bank-accounts")
        return _bank_account_page(request, form, status=400)
    return _bank_account_page(request, BankAccountForm())


@login_required
@require_admin
def bank_account_edit(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('settings')}#bank-accounts")
        return _bank_account_page(request, form, account, status=400)
    return _bank_account_page(request, BankAccountForm(instance=account), account)


@login_required
@require_admin
@require_POST
def bank_account_archive(request, pk):
    """Archive hides the account from new invoices; restore brings it back."""
    account = get_object_or_404(BankAccount, pk=pk)
    account.archived_at = None if account.archived_at else timezone.now()
    account.save()
    return redirect(f"{reverse('settings')}#bank-accounts")


@login_required
@require_admin
@require_POST
def bank_account_delete(request, pk):
    """Only an account no invoice uses can go; the others are archived."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        account.delete()
    except ProtectedError:
        return HttpResponseBadRequest('This account is on an invoice. Archive it instead.')
    return redirect(f"{reverse('settings')}#bank-accounts")
