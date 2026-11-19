"""Settings: one page per section, under a shared sub-nav (templates/crm/settings/)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_admin

from .forms import BankAccountForm, CompanyForm, CurrencyForm, StorageForm, ThemeForm
from .models import BankAccount, Company, Currency

# The sub-nav: (group, [(url name, label, icon)]). Pages pass their url name as `section`.
SECTIONS = (
    ('Company', (
        ('settings', 'Company details', 'building-2'),
        ('settings_appearance', 'Appearance', 'palette'),
    )),
    ('Billing', (
        ('settings_bank_accounts', 'Bank accounts', 'landmark'),
        ('settings_currencies', 'Currencies', 'coins'),
    )),
    ('Services', (
        ('settings_service_types', 'Service types', 'layers'),
    )),
    ('Leads', (
        ('settings_lead_statuses', 'Lead statuses', 'columns-3'),
        ('settings_lead_sources', 'Lead sources', 'signpost'),
    )),
    ('Integrations', (
        ('settings_storage', 'File storage', 'hard-drive'),
    )),
)


def _saved(request, text):
    # Tagged, so the settings pages show only their own notes, not allauth's "Signed in".
    messages.success(request, text, extra_tags='settings')


def _render(request, template, section, context=None, status=200):
    return render(
        request,
        f'crm/settings/{template}',
        {'sections': SECTIONS, 'section': section, **(context or {})},
        status=status,
    )


@login_required
@require_admin
def settings_page(request):
    """Company details. /settings/ opens here."""
    company = Company.load()
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            _saved(request, 'Company details saved.')
            return redirect('settings')
        return _render(request, 'company.html', 'settings', {'form': form}, status=400)
    return _render(request, 'company.html', 'settings', {'form': form})


@login_required
@require_admin
def settings_appearance(request):
    form = ThemeForm(request.POST or None, instance=Company.load())
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            _saved(request, 'Appearance saved.')
            return redirect('settings_appearance')
        return _render(request, 'appearance.html', 'settings_appearance', {'form': form}, status=400)
    return _render(request, 'appearance.html', 'settings_appearance', {'form': form})


@login_required
@require_admin
def settings_storage(request):
    company = Company.load()
    form = StorageForm(request.POST or None, instance=company)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            _saved(request, 'File storage saved.')
            return redirect('settings_storage')
        status = 400
    else:
        status = 200
    return _render(request, 'storage.html', 'settings_storage', {
        'form': form,
        'files_on_disk_in_production': not settings.DEBUG and not Company.load().uses_s3,
    }, status=status)


def _currencies_page(request, form=None, error='', status=200):
    return _render(request, 'currencies.html', 'settings_currencies', {
        'form': form or CurrencyForm(),
        'currencies': Currency.objects.order_by('code'),
        'currency_error': error,
    }, status=status)


@login_required
@require_admin
def settings_currencies(request):
    return _currencies_page(request)


@login_required
@require_admin
@require_POST
def currency_add(request):
    form = CurrencyForm(request.POST)
    if form.is_valid():
        currency = form.save()
        _saved(request, f'{currency.code} added.')
        return redirect('settings_currencies')
    return _currencies_page(request, form, status=400)


@login_required
@require_admin
@require_POST
def currency_delete(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    if currency.clients.exists():
        return _currencies_page(request, error='This currency is used by a client.', status=400)
    if currency.leads.exists():
        return _currencies_page(request, error='This currency is used by a lead.', status=400)
    if currency.bank_accounts.exists():
        return _currencies_page(request, error='This currency is used by a bank account.', status=400)
    try:
        currency.delete()
    except ProtectedError:
        return _currencies_page(request, error='This currency is used by a client.', status=400)
    _saved(request, f'{currency.code} deleted.')
    return redirect('settings_currencies')


def _bank_accounts_page(request, error='', status=200):
    return _render(request, 'bank_accounts.html', 'settings_bank_accounts', {
        'bank_accounts': BankAccount.objects.select_related('currency').annotate(
            invoice_count=Count('invoices'),
        ).order_by('archived_at', 'label', 'pk'),
        'bank_account_error': error,
    }, status=status)


@login_required
@require_admin
def settings_bank_accounts(request):
    return _bank_accounts_page(request)


def _bank_account_form(request, form, account=None, status=200):
    return _render(request, 'bank_account_form.html', 'settings_bank_accounts', {
        'form': form, 'account': account,
    }, status=status)


@login_required
@require_admin
def bank_account_add(request):
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            _saved(request, f'{account.label} added.')
            return redirect('settings_bank_accounts')
        return _bank_account_form(request, form, status=400)
    return _bank_account_form(request, BankAccountForm())


@login_required
@require_admin
def bank_account_edit(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            _saved(request, f'{account.label} saved.')
            return redirect('settings_bank_accounts')
        return _bank_account_form(request, form, account, status=400)
    return _bank_account_form(request, BankAccountForm(instance=account), account)


@login_required
@require_admin
@require_POST
def bank_account_archive(request, pk):
    """Archive hides the account from new invoices; restore brings it back."""
    account = get_object_or_404(BankAccount, pk=pk)
    account.archived_at = None if account.archived_at else timezone.now()
    account.save()
    _saved(request, f'{account.label} {"archived" if account.archived_at else "restored"}.')
    return redirect('settings_bank_accounts')


@login_required
@require_admin
@require_POST
def bank_account_delete(request, pk):
    """Only an account no invoice uses can go; the others are archived."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        account.delete()
    except ProtectedError:
        return _bank_accounts_page(
            request, error='This account is on an invoice. Archive it instead.', status=400,
        )
    _saved(request, f'{account.label} deleted.')
    return redirect('settings_bank_accounts')
