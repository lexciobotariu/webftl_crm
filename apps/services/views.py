"""Services: the list, a service's page, sites and their logins, extra hours, monthly reports.

Everything needs the Services module (``access_services``); whoever has
it sees every service and site. The tasks of a service live in its project and
follow the usual task rights. Deleting a site is for admins.
"""
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import Client
from apps.invoices.forms import InvoiceEmailForm
from apps.invoices.models import add_months

from . import core
from .forms import CredentialForm, InvoicingForm, ReportIntroForm, ServiceForm, SiteForm
from .models import Service, ServiceType, Site, SiteCredential

STATUS_FILTERS = ('open', 'active', 'paused', 'ended', 'all')


def _redirect(url):
    response = HttpResponse('')
    response['HX-Redirect'] = url
    return response


def _service_or_404(pk):
    return get_object_or_404(Service.objects.select_related('client__currency', 'project'), pk=pk)


def _error(exc):
    return exc.messages[0] if getattr(exc, 'messages', None) else str(exc)


# --- Services -------------------------------------------------------------


@login_required
@require_permission('access_services')
def service_list(request):
    status = request.GET.get('status', 'open')
    if status not in STATUS_FILTERS:
        status = 'open'
    items = Service.objects.select_related('client__currency', 'service_type').prefetch_related('sites')
    if status == 'open':
        items = items.exclude(status=Service.ENDED)
    elif status != 'all':
        items = items.filter(status=status)
    query = request.GET.get('q', '').strip()[:100]
    if query:
        items = items.filter(name__icontains=query) | items.filter(client__name__icontains=query)
    today = timezone.localdate()
    rows = [{'service': service, 'usage': core.usage(service, today)} for service in items]
    return render(request, 'services/service_list.html', {
        'rows': rows, 'status': status, 'query': query, 'today': today,
    })


@login_required
@require_permission('access_services')
def service_create(request):
    raw = request.GET.get('client', '')
    client = Client.objects.filter(pk=raw, archived_at__isnull=True).first() if raw.isdigit() else None
    if request.method == 'POST':
        form = ServiceForm(request.POST, user=request.user)
        if form.is_valid():
            service = form.save(commit=False)
            core.create_service(service, request.user, sites=form.cleaned_data['sites'])
            return _redirect(reverse('service_detail', args=[service.pk]))
    else:
        form = ServiceForm(user=request.user, client=client, initial=_drawer_initial(request.GET))
    return render(request, 'services/partials/service_drawer.html', {
        'form': form, 'service': None, 'type_checklist': _type_checklist(form),
    })


def _type_checklist(form):
    """"Checks, 6 items" for the chosen type, or '' when it has no checklist."""
    raw = str(form['service_type'].value() or '')
    kind = ServiceType.objects.filter(pk=raw).first() if raw.isdigit() else None
    items = [line for line in (kind.checklist if kind else '').splitlines() if line.strip()]
    if not items:
        return ''
    return f'{kind.checklist_title or "Checks"}, {len(items)} item{"s" if len(items) != 1 else ""}'


TYPE_FIELDS = ('description', 'frequency', 'price', 'included_hours', 'overage_rate')


def _drawer_initial(params):
    """What the new-service drawer shows again when it reloads for a new client or type.

    Choosing a type (``apply_type``) fills in its description, billing, price and hours.
    """
    initial = {}
    for name in ServiceForm.Meta.fields:
        if name == 'sites':
            continue
        if name in params:
            initial[name] = params.get(name)
    if 'auto_renew' in initial or 'name' in params:
        initial['auto_renew'] = params.get('auto_renew') == 'on'
    raw = params.get('service_type', '')
    kind = ServiceType.objects.filter(pk=raw).first() if raw.isdigit() else None
    if kind is not None and params.get('apply_type'):
        for name in TYPE_FIELDS:
            value = getattr(kind, name)
            if value not in (None, ''):
                initial[name] = value
        if not initial.get('name') and initial.get('client'):
            client = Client.objects.filter(pk=initial['client']).first() if str(initial['client']).isdigit() else None
            initial['name'] = f'{client.name} · {kind.name}' if client else kind.name
        elif not initial.get('name'):
            initial['name'] = kind.name
    return initial


@login_required
@require_permission('access_services')
def service_edit(request, pk):
    service = _service_or_404(pk)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service, user=request.user)
        if form.is_valid():
            core.update_service(form.save(commit=False), sites=form.cleaned_data['sites'])
            return _redirect(reverse('service_detail', args=[service.pk]))
    else:
        form = ServiceForm(instance=service, user=request.user)
    return render(request, 'services/partials/service_drawer.html', {'form': form, 'service': service})


def _month_choices(service, today):
    """The months the hour card can show: from the service's start (at most a year back) to this month."""
    first = core.month_start(max(service.start_date, add_months(today, -11)))
    months, month = [], core.month_start(today)
    while month >= first:
        months.append(month)
        month = add_months(month, -1)
    return months or [core.month_start(today)]


@login_required
@require_permission('access_services')
def service_detail(request, pk):
    service = _service_or_404(pk)
    return render(request, 'services/service_detail.html', _service_context(request, service, request.GET.get('month')))


@login_required
@require_permission('access_services')
def service_sections(request, pk):
    """The service page's sections alone: reloaded when its tasks or time change."""
    service = _service_or_404(pk)
    return _sections(request, service, request.GET.get('month'))


def _service_context(request, service, raw_month=None):
    from apps.tasks.models import Task, can_view_tasks_on
    from apps.tasks.recurring_views import panel_context

    today = timezone.localdate()
    month = core.parse_month(raw_month, core.month_start(today))
    can_see_tasks = can_view_tasks_on(request.user, service.project)
    open_tasks = (
        Task.objects.filter(project=service.project, closed_at__isnull=True)
        .select_related('status', 'assignee', 'project').order_by('due_date', '-updated_at')[:10]
        if can_see_tasks else []
    )
    can_bill = request.user.has_app_permission('access_invoices') and request.user.has_app_permission('invoices_create')
    return {
        'service': service,
        'sites': service.sites.all(),
        'month': month,
        'months': _month_choices(service, today),
        'usage': core.usage(service, month),
        'overage': service.overages.filter(month=month).select_related('invoice').first(),
        'can_bill': can_bill,
        'can_see_tasks': can_see_tasks,
        'open_tasks': open_tasks,
        'recurring': panel_context(request.user, service.project) if can_see_tasks else None,
        'invoices': core.service_invoices(service)[:6] if request.user.has_app_permission('access_invoices') else [],
        'reports': service.reports.all()[:12],
        'this_month': core.month_start(today),
        'last_month': core.month_start(core.month_start(today) - timedelta(days=1)),
        'today': today,
    }


def _sections(request, service, raw_month=None):
    return render(request, 'services/partials/service_sections.html', _service_context(request, service, raw_month))


@login_required
@require_permission('access_services')
@require_POST
def service_status(request, pk):
    service = _service_or_404(pk)
    try:
        core.set_status(service, request.POST.get('status', ''))
    except ValidationError as exc:
        return HttpResponse(_error(exc), status=400)
    return _redirect(reverse('service_detail', args=[service.pk]))


@login_required
@require_permission('access_services')
@require_permission('access_invoices')
@require_permission('invoices_create')
def service_invoicing(request, pk):
    """Create the service's first invoice and repeat it every billing period."""
    service = _service_or_404(pk)
    if service.recurring_invoice_id:
        return HttpResponse('This service already has its repeating invoice.', status=400)
    error = ''
    if request.method == 'POST':
        form = InvoicingForm(request.POST)
        if form.is_valid():
            try:
                invoice = core.set_up_invoicing(service, request.user, **form.cleaned_data)
            except ValidationError as exc:
                error = _error(exc)
            else:
                return _redirect(reverse('invoice_detail', args=[invoice.pk]))
    else:
        form = InvoicingForm()
    return render(request, 'services/partials/invoicing_drawer.html', {'form': form, 'service': service, 'error': error})


@login_required
@require_permission('access_services')
@require_permission('access_invoices')
@require_permission('invoices_create')
@require_POST
def service_extra_hours(request, pk):
    service = _service_or_404(pk)
    month = core.parse_month(request.POST.get('month'))
    if month is None:
        return HttpResponse('Choose a month.', status=400)
    try:
        invoice = core.add_extra_hours(service, month, request.user)
    except ValidationError as exc:
        return HttpResponse(_error(exc), status=400)
    return _redirect(reverse('invoice_detail', args=[invoice.pk]))


# --- Reports -----------------------------------------------------------


def _report(service, year, month):
    month = core.parse_month(f'{year}-{month}')
    if month is None:
        return None
    return core.report_for(service, month)


@login_required
@require_permission('access_services')
def report_detail(request, pk, year, month):
    service = _service_or_404(pk)
    report = _report(service, year, month)
    if report is None:
        return HttpResponse('Unknown month.', status=404)
    saved = False
    if request.method == 'POST':
        form = ReportIntroForm(request.POST, instance=report)
        if form.is_valid():
            form.save()
            saved = True
    else:
        form = ReportIntroForm(instance=report)
    from apps.crm.models import Company

    return render(request, 'services/report_detail.html', {
        'service': service, 'report': report, 'form': form, 'saved': saved, 'company': Company.load(),
        **core.report_data(service, report.month),
    })


@login_required
@require_permission('access_services')
def report_pdf(request, pk, year, month):
    service = _service_or_404(pk)
    report = _report(service, year, month)
    if report is None:
        return HttpResponse('Unknown month.', status=404)
    response = HttpResponse(core.report_pdf(report), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{core.report_filename(report)}"'
    return response


@login_required
@require_permission('access_services')
def report_email(request, pk, year, month):
    service = _service_or_404(pk)
    report = _report(service, year, month)
    if report is None:
        return HttpResponse('Unknown month.', status=404)
    if request.method == 'POST':
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            sent = core.send_report(
                report,
                to=form.cleaned_data['to'],
                subject=form.cleaned_data['subject'],
                message=form.cleaned_data['message'],
                author=request.user,
            )
            if not sent.failed:
                return _redirect(reverse('service_report', args=[service.pk, report.month.year, report.month.month]))
            form.add_error(None, f'The email was not sent: {sent.error}')
    else:
        form = InvoiceEmailForm(initial={
            'to': core.default_recipient(service.client),
            'subject': f'Report {report.month:%B %Y}: {service.name}',
            'message': core.default_message(report),
        })
    return render(request, 'services/partials/report_email_drawer.html', {
        'form': form, 'service': service, 'report': report, 'filename': core.report_filename(report),
    })


# --- Sites -------------------------------------------------------------


def _site_or_404(pk):
    return get_object_or_404(Site.objects.select_related('client', 'project'), pk=pk)


@login_required
@require_permission('access_services')
def site_create(request):
    raw = request.GET.get('client', '') or request.POST.get('client', '')
    client = get_object_or_404(Client, pk=raw) if str(raw).isdigit() else None
    if client is None:
        return HttpResponse('Choose a client.', status=400)
    if request.method == 'POST':
        form = SiteForm(request.POST, client=client)
        if form.is_valid():
            site = form.save()
            return _redirect(reverse('site_detail', args=[site.pk]))
    else:
        form = SiteForm(client=client)
    return render(request, 'services/partials/site_drawer.html', {'form': form, 'site': None, 'client': client})


@login_required
@require_permission('access_services')
def site_edit(request, pk):
    site = _site_or_404(pk)
    if request.method == 'POST':
        form = SiteForm(request.POST, instance=site, client=site.client)
        if form.is_valid():
            form.save()
            return _redirect(reverse('site_detail', args=[site.pk]))
    else:
        form = SiteForm(instance=site, client=site.client)
    return render(request, 'services/partials/site_drawer.html', {'form': form, 'site': site, 'client': site.client})


@login_required
@require_permission('access_services')
def site_detail(request, pk):
    site = _site_or_404(pk)
    return render(request, 'services/site_detail.html', {
        'site': site,
        'services': site.services.all(),
        'credentials': site.credentials.all(),
    })


@login_required
@require_permission('access_services')
@require_POST
def site_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden('Only admins delete sites.')
    site = _site_or_404(pk)
    client = site.client
    site.delete()
    return _redirect(reverse('client_detail_sites', args=[client.pk]))


def _credentials_changed():
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({'closeSlideOver': True, 'credentialsChanged': True})
    return response


@login_required
@require_permission('access_services')
def credential_create(request, pk):
    site = _site_or_404(pk)
    if request.method == 'POST':
        form = CredentialForm(request.POST)
        if form.is_valid():
            credential = form.save(commit=False)
            credential.site = site
            credential.updated_by = request.user
            credential.save()
            return _credentials_changed()
    else:
        form = CredentialForm()
    return render(request, 'services/partials/credential_drawer.html', {'form': form, 'site': site, 'credential': None})


@login_required
@require_permission('access_services')
def credential_edit(request, pk, credential_pk):
    site = _site_or_404(pk)
    credential = get_object_or_404(SiteCredential, pk=credential_pk, site=site)
    if request.method == 'POST':
        form = CredentialForm(request.POST, instance=credential)
        if form.is_valid():
            credential = form.save(commit=False)
            credential.updated_by = request.user
            credential.save()
            return _credentials_changed()
    else:
        form = CredentialForm(instance=credential)
    return render(request, 'services/partials/credential_drawer.html', {
        'form': form, 'site': site, 'credential': credential,
    })


@login_required
@require_permission('access_services')
@require_POST
def credential_delete(request, pk, credential_pk):
    site = _site_or_404(pk)
    get_object_or_404(SiteCredential, pk=credential_pk, site=site).delete()
    return credentials_list(request, pk)


@login_required
@require_permission('access_services')
def credentials_list(request, pk):
    site = _site_or_404(pk)
    return render(request, 'services/partials/credentials.html', {
        'site': site, 'credentials': site.credentials.all(),
    })


@login_required
@require_permission('access_services')
def credential_reveal(request, pk, credential_pk):
    """One login's password and notes, shown only when asked for."""
    site = _site_or_404(pk)
    credential = get_object_or_404(SiteCredential, pk=credential_pk, site=site)
    response = render(request, 'services/partials/credential_secret.html', {'site': site, 'credential': credential})
    response['Cache-Control'] = 'no-store'
    return response


# --- Client tabs -------------------------------------------------------


def client_tab_context(client, tab):
    """What the client page's Services and Sites tabs show."""
    today = timezone.localdate()
    if tab == 'services':
        items = client.services.prefetch_related('sites')
        return {'service_rows': [{'service': service, 'usage': core.usage(service, today)} for service in items]}
    return {'client_sites': client.sites.prefetch_related('services')}
