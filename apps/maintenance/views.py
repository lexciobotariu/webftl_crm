"""Maintenance: plans, sites and their logins, checks, extra hours, monthly reports.

Everything needs the Maintenance module (``access_maintenance``); whoever has
it sees every plan and site. The tasks of a plan live in its project and
follow the usual task rights. Deleting a site is for admins.
"""
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import Client
from apps.invoices.forms import InvoiceEmailForm
from apps.invoices.models import add_months

from . import services
from .forms import CheckForm, CredentialForm, InvoicingForm, PlanForm, ReportIntroForm, SiteForm
from .models import MaintenanceCheck, MaintenancePlan, Site, SiteCredential

STATUS_FILTERS = ('open', 'active', 'paused', 'ended', 'all')


def _redirect(url):
    response = HttpResponse('')
    response['HX-Redirect'] = url
    return response


def _plan_or_404(pk):
    return get_object_or_404(MaintenancePlan.objects.select_related('client__currency', 'project'), pk=pk)


def _error(exc):
    return exc.messages[0] if getattr(exc, 'messages', None) else str(exc)


# --- Plans -------------------------------------------------------------


@login_required
@require_permission('access_maintenance')
def plan_list(request):
    status = request.GET.get('status', 'open')
    if status not in STATUS_FILTERS:
        status = 'open'
    plans = MaintenancePlan.objects.select_related('client__currency').prefetch_related('sites')
    if status == 'open':
        plans = plans.exclude(status=MaintenancePlan.ENDED)
    elif status != 'all':
        plans = plans.filter(status=status)
    query = request.GET.get('q', '').strip()[:100]
    if query:
        plans = plans.filter(name__icontains=query) | plans.filter(client__name__icontains=query)
    today = timezone.localdate()
    rows = [{'plan': plan, 'usage': services.usage(plan, today)} for plan in plans]
    return render(request, 'maintenance/plan_list.html', {
        'rows': rows, 'status': status, 'query': query, 'today': today,
    })


@login_required
@require_permission('access_maintenance')
def plan_create(request):
    raw = request.GET.get('client', '')
    client = Client.objects.filter(pk=raw, archived_at__isnull=True).first() if raw.isdigit() else None
    if request.method == 'POST':
        form = PlanForm(request.POST, user=request.user)
        if form.is_valid():
            plan = form.save(commit=False)
            services.create_plan(plan, request.user, sites=form.cleaned_data['sites'])
            return _redirect(reverse('maintenance_plan_detail', args=[plan.pk]))
    else:
        form = PlanForm(user=request.user, client=client)
    return render(request, 'maintenance/partials/plan_drawer.html', {'form': form, 'plan': None})


@login_required
@require_permission('access_maintenance')
def plan_edit(request, pk):
    plan = _plan_or_404(pk)
    if request.method == 'POST':
        form = PlanForm(request.POST, instance=plan, user=request.user)
        if form.is_valid():
            services.update_plan(form.save(commit=False), sites=form.cleaned_data['sites'])
            return _redirect(reverse('maintenance_plan_detail', args=[plan.pk]))
    else:
        form = PlanForm(instance=plan, user=request.user)
    return render(request, 'maintenance/partials/plan_drawer.html', {'form': form, 'plan': plan})


def _month_choices(plan, today):
    """The months the hour card can show: from the plan's start (at most a year back) to this month."""
    first = services.month_start(max(plan.start_date, add_months(today, -11)))
    months, month = [], services.month_start(today)
    while month >= first:
        months.append(month)
        month = add_months(month, -1)
    return months or [services.month_start(today)]


@login_required
@require_permission('access_maintenance')
def plan_detail(request, pk):
    plan = _plan_or_404(pk)
    return render(request, 'maintenance/plan_detail.html', _plan_context(request, plan, request.GET.get('month')))


@login_required
@require_permission('access_maintenance')
def plan_sections(request, pk):
    """The plan page's sections alone: reloaded when its tasks, time or checks change."""
    plan = _plan_or_404(pk)
    return _sections(request, plan, request.GET.get('month'))


def _plan_context(request, plan, raw_month=None, check_form=None):
    from apps.tasks.models import Task, can_view_tasks_on

    today = timezone.localdate()
    month = services.parse_month(raw_month, services.month_start(today))
    can_see_tasks = can_view_tasks_on(request.user, plan.project)
    open_tasks = (
        Task.objects.filter(project=plan.project, closed_at__isnull=True)
        .select_related('status', 'assignee', 'project').order_by('due_date', '-updated_at')[:10]
        if can_see_tasks else []
    )
    can_bill = request.user.has_app_permission('access_invoices') and request.user.has_app_permission('invoices_create')
    return {
        'plan': plan,
        'sites': plan.sites.all(),
        'month': month,
        'months': _month_choices(plan, today),
        'usage': services.usage(plan, month),
        'overage': plan.overages.filter(month=month).select_related('invoice').first(),
        'can_bill': can_bill,
        'can_see_tasks': can_see_tasks,
        'open_tasks': open_tasks,
        'checks': plan.checks.all(),
        'check_form': check_form or CheckForm(),
        'runs': plan.check_runs.select_related('task__status')[:6],
        'invoices': services.plan_invoices(plan)[:6] if request.user.has_app_permission('access_invoices') else [],
        'reports': plan.reports.all()[:12],
        'this_month': services.month_start(today),
        'last_month': services.month_start(services.month_start(today) - timedelta(days=1)),
        'today': today,
    }


def _sections(request, plan, raw_month=None, check_form=None, toast=''):
    response = render(request, 'maintenance/partials/plan_sections.html',
                      _plan_context(request, plan, raw_month, check_form))
    if toast:
        response['HX-Trigger'] = json.dumps({'infoToast': {'target': 'body', 'message': toast}})
    return response


@login_required
@require_permission('access_maintenance')
@require_POST
def plan_status(request, pk):
    plan = _plan_or_404(pk)
    try:
        services.set_status(plan, request.POST.get('status', ''))
    except ValidationError as exc:
        return HttpResponse(_error(exc), status=400)
    return _redirect(reverse('maintenance_plan_detail', args=[plan.pk]))


@login_required
@require_permission('access_maintenance')
@require_POST
def check_create(request, pk):
    plan = _plan_or_404(pk)
    form = CheckForm(request.POST)
    title = form.cleaned_data['title'].strip() if form.is_valid() else ''
    if not title:
        return _sections(request, plan, request.POST.get('month'), check_form=form)
    position = (plan.checks.aggregate(top=Max('position'))['top'] or 0) + 1
    MaintenanceCheck.objects.create(plan=plan, title=title, position=position)
    services.schedule_checks(plan)
    return _sections(request, plan, request.POST.get('month'), toast=f'Check added: {title}')


@login_required
@require_permission('access_maintenance')
@require_POST
def check_delete(request, pk, check_pk):
    plan = _plan_or_404(pk)
    check = get_object_or_404(MaintenanceCheck, pk=check_pk, plan=plan)
    check.delete()
    return _sections(request, plan, request.POST.get('month'), toast=f'Check removed: {check.title}')


@login_required
@require_permission('access_maintenance')
@require_POST
def check_run(request, pk):
    """Create this period's checks task now, instead of waiting for the daily job."""
    plan = _plan_or_404(pk)
    if not plan.checks.exists():
        return HttpResponse('Add a check first.', status=400)
    if not plan.is_active:
        return HttpResponse('The plan is not active.', status=400)
    period, task = services.create_current_checks(plan, request.user)
    if task is None:
        toast = f'"{services.check_task_title(plan, period)}" was already created.'
    else:
        toast = f'Created {task.identifier}: {task.title}'
    return _sections(request, plan, request.POST.get('month'), toast=toast)


@login_required
@require_permission('access_maintenance')
@require_permission('access_invoices')
@require_permission('invoices_create')
def plan_invoicing(request, pk):
    """Create the plan's first invoice and repeat it every billing period."""
    plan = _plan_or_404(pk)
    if plan.recurring_invoice_id:
        return HttpResponse('This plan already has its repeating invoice.', status=400)
    error = ''
    if request.method == 'POST':
        form = InvoicingForm(request.POST)
        if form.is_valid():
            try:
                invoice = services.set_up_invoicing(plan, request.user, **form.cleaned_data)
            except ValidationError as exc:
                error = _error(exc)
            else:
                return _redirect(reverse('invoice_detail', args=[invoice.pk]))
    else:
        form = InvoicingForm()
    return render(request, 'maintenance/partials/invoicing_drawer.html', {'form': form, 'plan': plan, 'error': error})


@login_required
@require_permission('access_maintenance')
@require_permission('access_invoices')
@require_permission('invoices_create')
@require_POST
def plan_extra_hours(request, pk):
    plan = _plan_or_404(pk)
    month = services.parse_month(request.POST.get('month'))
    if month is None:
        return HttpResponse('Choose a month.', status=400)
    try:
        invoice = services.add_extra_hours(plan, month, request.user)
    except ValidationError as exc:
        return HttpResponse(_error(exc), status=400)
    return _redirect(reverse('invoice_detail', args=[invoice.pk]))


# --- Reports -----------------------------------------------------------


def _report(plan, year, month):
    month = services.parse_month(f'{year}-{month}')
    if month is None:
        return None
    return services.report_for(plan, month)


@login_required
@require_permission('access_maintenance')
def report_detail(request, pk, year, month):
    plan = _plan_or_404(pk)
    report = _report(plan, year, month)
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

    return render(request, 'maintenance/report_detail.html', {
        'plan': plan, 'report': report, 'form': form, 'saved': saved, 'company': Company.load(),
        **services.report_data(plan, report.month),
    })


@login_required
@require_permission('access_maintenance')
def report_pdf(request, pk, year, month):
    plan = _plan_or_404(pk)
    report = _report(plan, year, month)
    if report is None:
        return HttpResponse('Unknown month.', status=404)
    response = HttpResponse(services.report_pdf(report), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{services.report_filename(report)}"'
    return response


@login_required
@require_permission('access_maintenance')
def report_email(request, pk, year, month):
    plan = _plan_or_404(pk)
    report = _report(plan, year, month)
    if report is None:
        return HttpResponse('Unknown month.', status=404)
    if request.method == 'POST':
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            sent = services.send_report(
                report,
                to=form.cleaned_data['to'],
                subject=form.cleaned_data['subject'],
                message=form.cleaned_data['message'],
                author=request.user,
            )
            if not sent.failed:
                return _redirect(reverse('maintenance_report', args=[plan.pk, report.month.year, report.month.month]))
            form.add_error(None, f'The email was not sent: {sent.error}')
    else:
        form = InvoiceEmailForm(initial={
            'to': services.default_recipient(plan.client),
            'subject': f'Maintenance report {report.month:%B %Y}: {plan.name}',
            'message': services.default_message(report),
        })
    return render(request, 'maintenance/partials/report_email_drawer.html', {
        'form': form, 'plan': plan, 'report': report, 'filename': services.report_filename(report),
    })


# --- Sites -------------------------------------------------------------


def _site_or_404(pk):
    return get_object_or_404(Site.objects.select_related('client', 'project'), pk=pk)


@login_required
@require_permission('access_maintenance')
def site_create(request):
    raw = request.GET.get('client', '') or request.POST.get('client', '')
    client = get_object_or_404(Client, pk=raw) if str(raw).isdigit() else None
    if client is None:
        return HttpResponse('Choose a client.', status=400)
    if request.method == 'POST':
        form = SiteForm(request.POST, client=client)
        if form.is_valid():
            site = form.save()
            return _redirect(reverse('maintenance_site_detail', args=[site.pk]))
    else:
        form = SiteForm(client=client)
    return render(request, 'maintenance/partials/site_drawer.html', {'form': form, 'site': None, 'client': client})


@login_required
@require_permission('access_maintenance')
def site_edit(request, pk):
    site = _site_or_404(pk)
    if request.method == 'POST':
        form = SiteForm(request.POST, instance=site, client=site.client)
        if form.is_valid():
            form.save()
            return _redirect(reverse('maintenance_site_detail', args=[site.pk]))
    else:
        form = SiteForm(instance=site, client=site.client)
    return render(request, 'maintenance/partials/site_drawer.html', {'form': form, 'site': site, 'client': site.client})


@login_required
@require_permission('access_maintenance')
def site_detail(request, pk):
    site = _site_or_404(pk)
    return render(request, 'maintenance/site_detail.html', {
        'site': site,
        'plans': site.plans.all(),
        'credentials': site.credentials.all(),
    })


@login_required
@require_permission('access_maintenance')
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
@require_permission('access_maintenance')
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
    return render(request, 'maintenance/partials/credential_drawer.html', {'form': form, 'site': site, 'credential': None})


@login_required
@require_permission('access_maintenance')
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
    return render(request, 'maintenance/partials/credential_drawer.html', {
        'form': form, 'site': site, 'credential': credential,
    })


@login_required
@require_permission('access_maintenance')
@require_POST
def credential_delete(request, pk, credential_pk):
    site = _site_or_404(pk)
    get_object_or_404(SiteCredential, pk=credential_pk, site=site).delete()
    return credentials_list(request, pk)


@login_required
@require_permission('access_maintenance')
def credentials_list(request, pk):
    site = _site_or_404(pk)
    return render(request, 'maintenance/partials/credentials.html', {
        'site': site, 'credentials': site.credentials.all(),
    })


@login_required
@require_permission('access_maintenance')
def credential_reveal(request, pk, credential_pk):
    """One login's password and notes, shown only when asked for."""
    site = _site_or_404(pk)
    credential = get_object_or_404(SiteCredential, pk=credential_pk, site=site)
    response = render(request, 'maintenance/partials/credential_secret.html', {'site': site, 'credential': credential})
    response['Cache-Control'] = 'no-store'
    return response


# --- Client tabs -------------------------------------------------------


def client_tab_context(client, tab):
    """What the client page's Maintenance and Sites tabs show."""
    today = timezone.localdate()
    if tab == 'maintenance':
        plans = client.maintenance_plans.prefetch_related('sites')
        return {'maintenance_rows': [{'plan': plan, 'usage': services.usage(plan, today)} for plan in plans]}
    return {'client_sites': client.sites.prefetch_related('plans')}
