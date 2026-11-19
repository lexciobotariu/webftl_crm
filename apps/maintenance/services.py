"""What maintenance plans do: create their project, count hours, bill, run checks, renew."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.invoices.models import Invoice, add_months
from apps.projects.models import Project, ProjectAccess, Status

from .models import (
    FREQUENCY_MONTHS,
    MaintenanceCheckRun,
    MaintenanceOverage,
    MaintenancePlan,
    MaintenanceReport,
    Site,
)

logger = logging.getLogger(__name__)

HUNDREDTH = Decimal('0.01')
# The hour bar turns amber from this share of the included hours.
WARN_SHARE = Decimal('0.8')
# Days between issue and due date of invoices the plan creates, unless told otherwise.
PAYMENT_DAYS = 14

PROJECT_STATUS = {
    MaintenancePlan.ACTIVE: Project.ACTIVE,
    MaintenancePlan.PAUSED: Project.ON_HOLD,
    MaintenancePlan.ENDED: Project.FINISHED,
}


def month_start(day):
    return day.replace(day=1)


def parse_month(value, default=None):
    """'2026-11' as the first day of that month, or ``default``."""
    try:
        year, month = (int(part) for part in (value or '').split('-'))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return default


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def hours(seconds):
    return (Decimal(seconds) / Decimal(3600)).quantize(HUNDREDTH, rounding=ROUND_HALF_UP)


# --- Creating and changing plans ---------------------------------------


@transaction.atomic
def create_plan(plan, user, sites=()):
    """Save a new ``plan`` (unsaved, client and fields set) with its own project.

    The project carries the plan's name and is billed at a fixed price, so its
    time is never billed again by the hour. The creator gets access to it.
    """
    project = Project.objects.create(
        client=plan.client,
        name=plan.name,
        description=plan.description,
        billing_type=Project.FIXED,
        start_date=plan.start_date,
        deadline=plan.renewal_date,
        status=PROJECT_STATUS[plan.status],
    )
    ProjectAccess.objects.get_or_create(project=project, user=user)
    plan.project = project
    plan.created_by = user
    plan.save()
    plan.sites.set(sites)
    return plan


def sync_project(plan):
    """Give the plan's project the plan's name, start date and end (renewal) date."""
    project = plan.project
    wanted = {'name': plan.name, 'start_date': plan.start_date, 'deadline': plan.renewal_date}
    changed = [field for field, value in wanted.items() if getattr(project, field) != value]
    if changed:
        for field in changed:
            setattr(project, field, wanted[field])
        project.save(update_fields=[*changed, 'updated_at'])


@transaction.atomic
def update_plan(plan, sites=None):
    """Save an edited plan, keeping its project's name and dates in step."""
    plan.save()
    if sites is not None:
        plan.sites.set(sites)
    sync_project(plan)
    return plan


@transaction.atomic
def set_status(plan, status):
    """Pause, resume or end a plan. Its project follows (On hold, Active, Finished).

    A plan that is not active creates no invoice drafts and no checks tasks.
    """
    if status not in dict(MaintenancePlan.STATUS_CHOICES):
        raise ValidationError('Unknown status.')
    plan.status = status
    plan.save(update_fields=['status', 'updated_at'])
    project = plan.project
    project.status = PROJECT_STATUS[status]
    project.save(update_fields=['status', 'updated_at'])
    return plan


def schedule_checks(plan, today=None):
    """Give a plan with checks its first checks date (the start of the current month), if it has none."""
    if plan.next_check_date is None and plan.checks.exists():
        plan.next_check_date = month_start(today or timezone.localdate())
        plan.save(update_fields=['next_check_date', 'updated_at'])


# --- Hours -------------------------------------------------------------


@dataclass
class Usage:
    month: date
    seconds: int
    included: Decimal

    @property
    def hours(self):
        return hours(self.seconds)

    @property
    def extra_hours(self):
        """Hours past the included ones; 0 for a plan without a limit."""
        if self.included <= 0:
            return Decimal('0.00')
        return max(self.hours - self.included, Decimal('0.00'))

    @property
    def percent(self):
        if self.included <= 0:
            return 0
        return int(min(self.hours / self.included * 100, Decimal(100)))

    @property
    def state(self):
        """'over', 'warn' or '' for the colour of the hour bar."""
        if self.included <= 0:
            return ''
        if self.hours > self.included:
            return 'over'
        if self.hours >= self.included * WARN_SHARE:
            return 'warn'
        return ''


def month_entries(plan, month):
    """Time entries on the plan's project that started in ``month``."""
    from apps.tasks.models import TimeEntry

    return TimeEntry.objects.filter(
        task__project_id=plan.project_id,
        started_at__gte=_day_start(month),
        started_at__lt=_day_start(add_months(month, 1)),
    )


def usage(plan, month=None, now=None):
    from apps.tasks.services import entry_seconds

    now = now or timezone.now()
    month = month_start(month or timezone.localdate())
    seconds = sum(entry_seconds(entry, now) for entry in month_entries(plan, month))
    return Usage(month=month, seconds=seconds, included=plan.included_hours)


# --- Invoices ----------------------------------------------------------


def _check_billable(plan):
    if plan.client.currency_id is None:
        raise ValidationError("Set the client's currency first: invoices are in it.")
    if plan.client.archived_at is not None:
        raise ValidationError('This client is archived.')


@transaction.atomic
def set_up_invoicing(plan, user, *, issue_date, payment_days=PAYMENT_DAYS, tax_rate=Decimal('0')):
    """Create the plan's first invoice (a draft) and repeat it every billing period.

    Later drafts come from the daily job, like any repeated invoice, and are
    never sent on their own. They stop while the plan is paused or ended.
    """
    from apps.invoices.recurring import save_recurring
    from apps.invoices.services import add_line, create_invoice

    if plan.recurring_invoice_id is not None:
        raise ValidationError('This plan already has its repeating invoice.')
    if plan.price is None:
        raise ValidationError('Set the price of the plan first.')
    _check_billable(plan)
    invoice = create_invoice(
        client=plan.client,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=payment_days),
        tax_rate=tax_rate,
        project=plan.project,
    )
    add_line(
        invoice,
        project=plan.project,
        description=f'{plan.name}: maintenance',
        details=plan.get_frequency_display(),
        quantity=Decimal('1'),
        unit_price=plan.price,
    )
    recurring = save_recurring(
        invoice,
        frequency=plan.frequency,
        next_date=add_months(issue_date, FREQUENCY_MONTHS[plan.frequency]),
        user=user,
        today=issue_date,
    )
    plan.recurring_invoice = recurring
    plan.save(update_fields=['recurring_invoice', 'updated_at'])
    return invoice


def plan_invoices(plan):
    """Invoices made from the plan: its first one, the repeated drafts and those carrying its extra hours."""
    query = Q(project=plan.project) | Q(lines__project=plan.project)
    if plan.recurring_invoice_id:
        query |= Q(from_recurring=plan.recurring_invoice_id) | Q(recurring=plan.recurring_invoice_id)
    return Invoice.objects.filter(query).distinct().order_by('-issue_date', '-number')


def _draft_for_extra_hours(plan, today):
    """The plan's newest draft invoice, or a new draft."""
    from apps.invoices.services import create_invoice

    drafts = Invoice.objects.filter(client=plan.client, sent_at__isnull=True, cancelled_at__isnull=True)
    if plan.recurring_invoice_id:
        draft = drafts.filter(from_recurring=plan.recurring_invoice_id).order_by('-issue_date', '-pk').first()
        if draft is None and plan.recurring_invoice.template.sent_at is None:
            draft = drafts.filter(pk=plan.recurring_invoice.template_id).first()
        if draft is not None:
            return draft
    template = plan.recurring_invoice.template if plan.recurring_invoice_id else None
    return create_invoice(
        client=plan.client,
        issue_date=today,
        due_date=today + timedelta(days=PAYMENT_DAYS),
        tax_rate=template.tax_rate if template else Decimal('0'),
        project=plan.project,
    )


def add_extra_hours(plan, month, user, today=None):
    """Put the hours past the included ones of ``month`` on a draft invoice. Returns the invoice.

    They go on the plan's newest draft, or a new draft when there is none, at
    the plan's extra-hour rate. A month is billed once.
    """
    from apps.invoices.services import add_line

    today = today or timezone.localdate()
    month = month_start(month)
    if plan.overage_rate is None:
        raise ValidationError('Set the price of an extra hour on the plan first.')
    if MaintenanceOverage.objects.filter(plan=plan, month=month).exists():
        raise ValidationError('The extra hours of this month are already on an invoice.')
    extra = usage(plan, month).extra_hours
    if extra <= 0:
        raise ValidationError('There are no extra hours this month.')
    _check_billable(plan)
    try:
        with transaction.atomic():
            invoice = _draft_for_extra_hours(plan, today)
            line = add_line(
                invoice,
                project=plan.project,
                description=f'Extra hours, {plan.name}',
                details=f'{month:%B %Y}: {usage(plan, month).hours} h worked, {plan.included_hours.normalize():f} h included',
                quantity=extra,
                unit_price=plan.overage_rate,
            )
            MaintenanceOverage.objects.create(
                plan=plan, month=month, hours=extra, rate=plan.overage_rate,
                invoice=invoice, invoice_line=line, created_by=user,
            )
    except IntegrityError:
        raise ValidationError('The extra hours of this month are already on an invoice.') from None
    return invoice


def paused_invoice(recurring):
    """True when ``recurring`` belongs to a plan that is paused or ended: the daily job then skips its draft."""
    plan = MaintenancePlan.objects.filter(recurring_invoice=recurring).only('status').first()
    return plan is not None and not plan.is_active


# --- Checks ------------------------------------------------------------


def _period_end(plan, period_start):
    return add_months(period_start, FREQUENCY_MONTHS[plan.check_frequency]) - timedelta(days=1)


def check_task_title(plan, period_start):
    if plan.check_frequency == 'monthly':
        return f'Checks {period_start:%B %Y}'
    end = _period_end(plan, period_start)
    return f'Checks {period_start:%b %Y} to {end:%b %Y}'


def create_checks_task(plan, period_start, user=None):
    """The checks task of one period, with a sub-task per check. Returns it, or None when it already exists."""
    from apps.tasks.models import Subtask, Task

    with transaction.atomic():
        run, created = MaintenanceCheckRun.objects.get_or_create(plan=plan, period_start=period_start)
        if not created:
            return None
        project = plan.project
        status = (
            project.statuses.filter(category=Status.UNSTARTED, visible_on_board=True).first()
            or project.statuses.filter(visible_on_board=True).first()
            or project.statuses.first()
        )
        task = Task(
            project=project,
            status=status,
            title=check_task_title(plan, period_start),
            due_date=_period_end(plan, period_start),
            billable=False,
        )
        task._changed_by = user
        task.save()
        Subtask.objects.bulk_create([
            Subtask(task=task, title=check.title, order=index)
            for index, check in enumerate(plan.checks.all())
        ])
        run.task = task
        run.save(update_fields=['task'])
    return task


def create_due_checks(today=None):
    """Create the checks task of every active plan whose next period has started. Returns the tasks.

    Missed periods (the job did not run) are skipped: only the current one is created.
    """
    today = today or timezone.localdate()
    created = []
    plans = MaintenancePlan.objects.filter(
        status=MaintenancePlan.ACTIVE, next_check_date__isnull=False, next_check_date__lte=today,
    ).select_related('project')
    for plan in plans:
        months = FREQUENCY_MONTHS[plan.check_frequency]
        period = plan.next_check_date
        while add_months(period, months) <= today:
            period = add_months(period, months)
        try:
            if plan.checks.exists():
                task = create_checks_task(plan, period)
                if task is not None:
                    created.append(task)
        except Exception:
            logger.exception('Maintenance plan %s could not create its checks task', plan.pk)
            continue
        plan.next_check_date = add_months(period, months)
        plan.save(update_fields=['next_check_date', 'updated_at'])
    return created


def create_current_checks(plan, user=None, today=None):
    """Create the checks task of the plan's current period now. Returns (period_start, task).

    ``task`` is None when that period's task was already created.
    """
    today = today or timezone.localdate()
    schedule_checks(plan, today)
    months = FREQUENCY_MONTHS[plan.check_frequency]
    period = plan.next_check_date
    while period > today:
        period = add_months(period, -months)
    while add_months(period, months) <= today:
        period = add_months(period, months)
    task = create_checks_task(plan, period, user)
    following = add_months(period, months)
    if plan.next_check_date < following:
        plan.next_check_date = following
        plan.save(update_fields=['next_check_date', 'updated_at'])
    return period, task


# --- Renewal -----------------------------------------------------------


def process_renewals(today=None):
    """Move the renewal date of auto-renewing plans past it; end the others. Returns (renewed, ended)."""
    today = today or timezone.localdate()
    renewed, ended = [], []
    due = MaintenancePlan.objects.select_related('project').exclude(status=MaintenancePlan.ENDED).filter(
        renewal_date__isnull=False, renewal_date__lt=today,
    )
    for plan in due:
        if plan.auto_renew and plan.term_months:
            while plan.renewal_date < today:
                plan.renewal_date = add_months(plan.renewal_date, plan.term_months)
            plan.save(update_fields=['renewal_date', 'updated_at'])
            sync_project(plan)
            renewed.append(plan)
        else:
            set_status(plan, MaintenancePlan.ENDED)
            ended.append(plan)
    return renewed, ended


def run_daily(today=None):
    """The maintenance part of the daily job."""
    renewed, ended = process_renewals(today)
    tasks = create_due_checks(today)
    return {'renewed': renewed, 'ended': ended, 'checks': tasks}


# --- Reports -----------------------------------------------------------


@dataclass
class WorkItem:
    task: object
    seconds: int

    @property
    def hours(self):
        return hours(self.seconds)


def report_data(plan, month, now=None):
    """What a month's report shows: hours, tasks worked on or closed, and the checks."""
    from apps.tasks.models import Task
    from apps.tasks.services import entry_seconds

    now = now or timezone.now()
    month = month_start(month)
    by_task = {}
    for entry in month_entries(plan, month).select_related('task'):
        by_task[entry.task_id] = by_task.get(entry.task_id, 0) + entry_seconds(entry, now)
    closed = Task.objects.filter(
        project=plan.project, closed_at__gte=_day_start(month), closed_at__lt=_day_start(add_months(month, 1)),
    ).values_list('pk', flat=True)
    ids = set(by_task) | set(closed)
    tasks = Task.objects.filter(pk__in=ids).select_related('status', 'project').order_by('closed_at', 'pk')
    run = (
        MaintenanceCheckRun.objects.filter(plan=plan, period_start__lte=month, task__isnull=False)
        .select_related('task').order_by('-period_start').first()
    )
    checks_task = run.task if run and _period_end(plan, run.period_start) >= month else None
    return {
        'usage': usage(plan, month, now),
        'work': [WorkItem(task=task, seconds=by_task.get(task.pk, 0)) for task in tasks],
        'checks_task': checks_task,
        'checks': list(checks_task.subtasks.all()) if checks_task else [],
        'overage': MaintenanceOverage.objects.filter(plan=plan, month=month).first(),
    }


def report_for(plan, month):
    report, _created = MaintenanceReport.objects.get_or_create(plan=plan, month=month_start(month))
    return report


def report_pdf(report):
    from django.template.loader import render_to_string
    from weasyprint import HTML

    from apps.crm.models import Company

    context = {
        'report': report,
        'plan': report.plan,
        'company': Company.load(),
        'for_pdf': True,
        **report_data(report.plan, report.month),
    }
    return HTML(string=render_to_string('maintenance/report_print.html', context)).write_pdf()


def report_filename(report):
    return f'Maintenance report {report.plan.name} {report.month:%Y-%m}.pdf'.replace('/', '-')


def default_recipient(client):
    contacts = client.contacts.exclude(email='')
    contact = contacts.filter(is_primary=True).first() or contacts.filter(is_billing=True).first()
    if contact:
        return contact.email
    return client.email or client.billing_email


def send_report(report, *, to, subject, message, author=None):
    """Email the report PDF and log it on the client's Messages tab. The log's ``error`` is set when it failed."""
    from django.core.mail import EmailMessage

    from apps.clients.models import ClientMessage
    from apps.crm.models import Company

    error = ''
    try:
        email = EmailMessage(subject=subject, body=message, to=list(to))
        reply_to = Company.load().email
        if reply_to:
            email.reply_to = [reply_to]
        email.attach(report_filename(report), report_pdf(report), 'application/pdf')
        email.send()
    except Exception as exc:
        logger.exception('Emailing maintenance report %s failed', report.pk)
        error = str(exc) or exc.__class__.__name__
    else:
        report.sent_at = timezone.now()
        report.save(update_fields=['sent_at', 'updated_at'])
    return ClientMessage.objects.create(
        client=report.plan.client,
        project=report.plan.project,
        kind=ClientMessage.EMAIL,
        subject=subject,
        body=message,
        recipients=', '.join(to),
        error=error,
        author=author,
    )


def default_message(report):
    from apps.crm.models import Company

    data = report_data(report.plan, report.month)
    used = data['usage']
    lines = ['Hello,', '', f'Attached is the maintenance report for {report.month:%B %Y} ({report.plan.name}).', '']
    if report.plan.has_hour_limit:
        lines.append(f'Hours used: {used.hours} of {report.plan.included_hours.normalize():f} included.')
    else:
        lines.append(f'Hours worked: {used.hours}.')
    lines.append(f'Tasks: {len(data["work"])}.')
    lines += ['', 'Thank you,']
    company = Company.load()
    if company.legal_name:
        lines.append(company.legal_name)
    return '\n'.join(lines)


# --- Dashboard ---------------------------------------------------------


@dataclass
class Alert:
    day: date
    label: str
    detail: str
    url: str
    icon: str
    state: str  # 'late' or ''


def dashboard_alerts(today=None, limit=8):
    """Renewals coming up, plans past their hours, domains and certificates expiring."""
    from django.urls import reverse

    from .models import SOON

    today = today or timezone.localdate()
    alerts = []
    plans = MaintenancePlan.objects.filter(status=MaintenancePlan.ACTIVE).select_related('client')
    for plan in plans:
        url = reverse('maintenance_plan_detail', args=[plan.pk])
        if plan.renewal_date and plan.renewal_state:
            word = 'Renews' if plan.auto_renew else 'Ends'
            alerts.append(Alert(plan.renewal_date, plan.name, f'{word} · {plan.client.name}', url, 'refresh-cw',
                                'late' if plan.renewal_date < today else ''))
        if plan.has_hour_limit:
            used = usage(plan, today)
            if used.state:
                alerts.append(Alert(
                    today, plan.name, f'{used.hours} of {plan.included_hours.normalize():f} h this month · {plan.client.name}',
                    url, 'clock', 'late' if used.state == 'over' else '',
                ))
    sites = Site.objects.filter(client__archived_at__isnull=True).filter(
        Q(domain_expires__lte=today + SOON) | Q(ssl_expires__lte=today + SOON),
    ).select_related('client')
    for site in sites:
        url = reverse('maintenance_site_detail', args=[site.pk])
        if site.domain_expires and site.domain_expires <= today + SOON:
            alerts.append(Alert(site.domain_expires, site.name, f'Domain expires · {site.client.name}', url, 'globe',
                                'late' if site.domain_expires < today else ''))
        if site.ssl_expires and site.ssl_expires <= today + SOON:
            alerts.append(Alert(site.ssl_expires, site.name, f'SSL expires · {site.client.name}', url, 'lock',
                                'late' if site.ssl_expires < today else ''))
    alerts.sort(key=lambda alert: (alert.day, alert.label))
    return alerts[:limit]
