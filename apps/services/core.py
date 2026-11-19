"""What services do: create their project, count hours, bill, renew, report."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.invoices.models import Invoice, add_months
from apps.projects.models import Project, ProjectAccess

from .models import (
    FREQUENCY_MONTHS,
    Service,
    ServiceOverage,
    ServiceReport,
    Site,
)

logger = logging.getLogger(__name__)

HUNDREDTH = Decimal('0.01')
# The hour bar turns amber from this share of the included hours.
WARN_SHARE = Decimal('0.8')
# Days between issue and due date of invoices the service creates, unless told otherwise.
PAYMENT_DAYS = 14

PROJECT_STATUS = {
    Service.ACTIVE: Project.ACTIVE,
    Service.PAUSED: Project.ON_HOLD,
    Service.ENDED: Project.FINISHED,
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


# --- Creating and changing services ---------------------------------------


@transaction.atomic
def create_service(service, user, sites=()):
    """Save a new ``service`` (unsaved, client and fields set) with its own project.

    The project carries the service's name and is billed at a fixed price, so its
    time is never billed again by the hour. The creator gets access to it.
    """
    project = Project.objects.create(
        client=service.client,
        name=service.name,
        description=service.description,
        billing_type=Project.FIXED,
        start_date=service.start_date,
        deadline=service.renewal_date,
        status=PROJECT_STATUS[service.status],
    )
    ProjectAccess.objects.get_or_create(project=project, user=user)
    service.project = project
    service.created_by = user
    service.save()
    service.sites.set(sites)
    kind = service.service_type
    if kind is not None and kind.checklist.strip():
        add_checklist_task(service, kind.checklist_title or 'Checks', kind.checklist, user)
    return service


# The checklist task is due on the 28th, so it is done within its month.
CHECKLIST_DUE_AFTER_DAYS = 27


def add_checklist_task(service, title, checklist, user=None, frequency=None, today=None):
    """A recurring task on the service's project, every month from this month, with one sub-task per line."""
    from apps.tasks import recurring
    from apps.tasks.models import RecurringTask

    today = today or timezone.localdate()
    rule = RecurringTask(
        project=service.project, title=title[:500], checklist=checklist, billable=False,
        frequency=RecurringTask.MONTHLY, interval=FREQUENCY_MONTHS.get(frequency or 'monthly', 1),
        month_day=1, start_date=max(month_start(service.start_date), month_start(today)), created_by=user,
        due_after_days=CHECKLIST_DUE_AFTER_DAYS,
    )
    recurring.schedule(rule, today)
    rule.save()
    return rule


def sync_project(service):
    """Give the service's project the service's name, start date and end (renewal) date."""
    project = service.project
    wanted = {'name': service.name, 'start_date': service.start_date, 'deadline': service.renewal_date}
    changed = [field for field, value in wanted.items() if getattr(project, field) != value]
    if changed:
        for field in changed:
            setattr(project, field, wanted[field])
        project.save(update_fields=[*changed, 'updated_at'])


@transaction.atomic
def update_service(service, sites=None):
    """Save an edited service, keeping its project's name and dates in step."""
    service.save()
    if sites is not None:
        service.sites.set(sites)
    sync_project(service)
    return service


@transaction.atomic
def set_status(service, status):
    """Pause, resume or end a service. Its project follows (On hold, Active, Finished).

    A service that is not active creates no invoice drafts, and its project's
    recurring tasks wait (they only run on Active projects).
    """
    if status not in dict(Service.STATUS_CHOICES):
        raise ValidationError('Unknown status.')
    service.status = status
    service.save(update_fields=['status', 'updated_at'])
    project = service.project
    project.status = PROJECT_STATUS[status]
    project.save(update_fields=['status', 'updated_at'])
    return service


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
        """Hours past the included ones; 0 for a service without a limit."""
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


def month_entries(service, month):
    """Time entries on the service's project that started in ``month``."""
    from apps.tasks.models import TimeEntry

    return TimeEntry.objects.filter(
        task__project_id=service.project_id,
        started_at__gte=_day_start(month),
        started_at__lt=_day_start(add_months(month, 1)),
    )


def usage(service, month=None, now=None):
    from apps.tasks.services import entry_seconds

    now = now or timezone.now()
    month = month_start(month or timezone.localdate())
    seconds = sum(entry_seconds(entry, now) for entry in month_entries(service, month))
    return Usage(month=month, seconds=seconds, included=service.included_hours)


# --- Invoices ----------------------------------------------------------


def _check_billable(service):
    if service.client.currency_id is None:
        raise ValidationError("Set the client's currency first: invoices are in it.")
    if service.client.archived_at is not None:
        raise ValidationError('This client is archived.')


@transaction.atomic
def set_up_invoicing(service, user, *, issue_date, payment_days=PAYMENT_DAYS, tax_rate=Decimal('0')):
    """Create the service's first invoice (a draft) and repeat it every billing period.

    Later drafts come from the daily job, like any repeated invoice, and are
    never sent on their own. They stop while the service is paused or ended.
    """
    from apps.invoices.recurring import save_recurring
    from apps.invoices.services import add_line, create_invoice

    if service.recurring_invoice_id is not None:
        raise ValidationError('This service already has its repeating invoice.')
    if service.price is None:
        raise ValidationError('Set the price of the service first.')
    _check_billable(service)
    invoice = create_invoice(
        client=service.client,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=payment_days),
        tax_rate=tax_rate,
        project=service.project,
    )
    add_line(
        invoice,
        project=service.project,
        description=service.name,
        details=service.get_frequency_display(),
        quantity=Decimal('1'),
        unit_price=service.price,
    )
    recurring = save_recurring(
        invoice,
        frequency=service.frequency,
        next_date=add_months(issue_date, FREQUENCY_MONTHS[service.frequency]),
        user=user,
        today=issue_date,
    )
    service.recurring_invoice = recurring
    service.save(update_fields=['recurring_invoice', 'updated_at'])
    return invoice


def service_invoices(service):
    """Invoices made from the service: its first one, the repeated drafts and those carrying its extra hours."""
    query = Q(project=service.project) | Q(lines__project=service.project)
    if service.recurring_invoice_id:
        query |= Q(from_recurring=service.recurring_invoice_id) | Q(recurring=service.recurring_invoice_id)
    return Invoice.objects.filter(query).distinct().order_by('-issue_date', '-number')


def _draft_for_extra_hours(service, today):
    """The service's newest draft invoice, or a new draft."""
    from apps.invoices.services import create_invoice

    drafts = Invoice.objects.filter(client=service.client, sent_at__isnull=True, cancelled_at__isnull=True)
    if service.recurring_invoice_id:
        draft = drafts.filter(from_recurring=service.recurring_invoice_id).order_by('-issue_date', '-pk').first()
        if draft is None and service.recurring_invoice.template.sent_at is None:
            draft = drafts.filter(pk=service.recurring_invoice.template_id).first()
        if draft is not None:
            return draft
    template = service.recurring_invoice.template if service.recurring_invoice_id else None
    return create_invoice(
        client=service.client,
        issue_date=today,
        due_date=today + timedelta(days=PAYMENT_DAYS),
        tax_rate=template.tax_rate if template else Decimal('0'),
        project=service.project,
    )


def add_extra_hours(service, month, user, today=None):
    """Put the hours past the included ones of ``month`` on a draft invoice. Returns the invoice.

    They go on the service's newest draft, or a new draft when there is none, at
    the service's extra-hour rate. A month is billed once.
    """
    from apps.invoices.services import add_line

    today = today or timezone.localdate()
    month = month_start(month)
    if service.overage_rate is None:
        raise ValidationError('Set the price of an extra hour on the service first.')
    if ServiceOverage.objects.filter(service=service, month=month).exists():
        raise ValidationError('The extra hours of this month are already on an invoice.')
    extra = usage(service, month).extra_hours
    if extra <= 0:
        raise ValidationError('There are no extra hours this month.')
    _check_billable(service)
    try:
        with transaction.atomic():
            invoice = _draft_for_extra_hours(service, today)
            line = add_line(
                invoice,
                project=service.project,
                description=f'Extra hours, {service.name}',
                details=f'{month:%B %Y}: {usage(service, month).hours} h worked, {service.included_hours.normalize():f} h included',
                quantity=extra,
                unit_price=service.overage_rate,
            )
            ServiceOverage.objects.create(
                service=service, month=month, hours=extra, rate=service.overage_rate,
                invoice=invoice, invoice_line=line, created_by=user,
            )
    except IntegrityError:
        raise ValidationError('The extra hours of this month are already on an invoice.') from None
    return invoice


def paused_invoice(recurring):
    """True when ``recurring`` belongs to a service that is paused or ended: the daily job then skips its draft."""
    service = Service.objects.filter(recurring_invoice=recurring).only('status').first()
    return service is not None and not service.is_active


# --- Renewal -----------------------------------------------------------


def process_renewals(today=None):
    """Move the renewal date of auto-renewing services past it; end the others. Returns (renewed, ended)."""
    today = today or timezone.localdate()
    renewed, ended = [], []
    due = Service.objects.select_related('project').exclude(status=Service.ENDED).filter(
        renewal_date__isnull=False, renewal_date__lt=today,
    )
    for service in due:
        if service.auto_renew and service.term_months:
            while service.renewal_date < today:
                service.renewal_date = add_months(service.renewal_date, service.term_months)
            service.save(update_fields=['renewal_date', 'updated_at'])
            sync_project(service)
            renewed.append(service)
        else:
            set_status(service, Service.ENDED)
            ended.append(service)
    return renewed, ended


def run_daily(today=None):
    """The services part of the daily job: renewals and ends."""
    renewed, ended = process_renewals(today)
    return {'renewed': renewed, 'ended': ended}


# --- Reports -----------------------------------------------------------


@dataclass
class WorkItem:
    task: object
    seconds: int

    @property
    def hours(self):
        return hours(self.seconds)


def report_data(service, month, now=None):
    """What a month's report shows: hours, tasks worked on or closed, and the checks."""
    from apps.tasks.models import Task
    from apps.tasks.services import entry_seconds

    now = now or timezone.now()
    month = month_start(month)
    by_task = {}
    for entry in month_entries(service, month).select_related('task'):
        by_task[entry.task_id] = by_task.get(entry.task_id, 0) + entry_seconds(entry, now)
    closed = Task.objects.filter(
        project=service.project, closed_at__gte=_day_start(month), closed_at__lt=_day_start(add_months(month, 1)),
    ).values_list('pk', flat=True)
    ids = set(by_task) | set(closed)
    tasks = Task.objects.filter(pk__in=ids).select_related('status', 'project').order_by('closed_at', 'pk')
    # The month's recurring tasks with checklists ("Checks · November 2026"), each with its sub-tasks.
    checklists = (
        Task.objects.filter(
            project=service.project, recurring__isnull=False,
            recurring_date__gte=month, recurring_date__lt=add_months(month, 1),
        )
        .filter(subtasks__isnull=False).distinct()
        .select_related('status', 'project').prefetch_related('subtasks').order_by('recurring_date', 'pk')
    )
    return {
        'usage': usage(service, month, now),
        'work': [WorkItem(task=task, seconds=by_task.get(task.pk, 0)) for task in tasks],
        'checklists': list(checklists),
        'overage': ServiceOverage.objects.filter(service=service, month=month).first(),
    }


def report_for(service, month):
    report, _created = ServiceReport.objects.get_or_create(service=service, month=month_start(month))
    return report


def report_pdf(report):
    from django.template.loader import render_to_string
    from weasyprint import HTML

    from apps.crm.models import Company

    context = {
        'report': report,
        'service': report.service,
        'company': Company.load(),
        'for_pdf': True,
        **report_data(report.service, report.month),
    }
    return HTML(string=render_to_string('services/report_print.html', context)).write_pdf()


def report_filename(report):
    return f'Report {report.service.name} {report.month:%Y-%m}.pdf'.replace('/', '-')


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
        logger.exception('Emailing service report %s failed', report.pk)
        error = str(exc) or exc.__class__.__name__
    else:
        report.sent_at = timezone.now()
        report.save(update_fields=['sent_at', 'updated_at'])
    return ClientMessage.objects.create(
        client=report.service.client,
        project=report.service.project,
        kind=ClientMessage.EMAIL,
        subject=subject,
        body=message,
        recipients=', '.join(to),
        error=error,
        author=author,
    )


def default_message(report):
    from apps.crm.models import Company

    data = report_data(report.service, report.month)
    used = data['usage']
    lines = ['Hello,', '', f'Attached is the report for {report.month:%B %Y} ({report.service.name}).', '']
    if report.service.has_hour_limit:
        lines.append(f'Hours used: {used.hours} of {report.service.included_hours.normalize():f} included.')
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
    """Renewals coming up, services past their hours, domains and certificates expiring."""
    from django.urls import reverse

    from .models import SOON

    today = today or timezone.localdate()
    alerts = []
    items = Service.objects.filter(status=Service.ACTIVE).select_related('client')
    for service in items:
        url = reverse('service_detail', args=[service.pk])
        if service.renewal_date and service.renewal_state:
            word = 'Renews' if service.auto_renew else 'Ends'
            alerts.append(Alert(service.renewal_date, service.name, f'{word} · {service.client.name}', url, 'refresh-cw',
                                'late' if service.renewal_date < today else ''))
        if service.has_hour_limit:
            used = usage(service, today)
            if used.state:
                alerts.append(Alert(
                    today, service.name, f'{used.hours} of {service.included_hours.normalize():f} h this month · {service.client.name}',
                    url, 'clock', 'late' if used.state == 'over' else '',
                ))
    sites = Site.objects.filter(client__archived_at__isnull=True).filter(
        Q(domain_expires__lte=today + SOON) | Q(ssl_expires__lte=today + SOON),
    ).select_related('client')
    for site in sites:
        url = reverse('site_detail', args=[site.pk])
        if site.domain_expires and site.domain_expires <= today + SOON:
            alerts.append(Alert(site.domain_expires, site.name, f'Domain expires · {site.client.name}', url, 'globe',
                                'late' if site.domain_expires < today else ''))
        if site.ssl_expires and site.ssl_expires <= today + SOON:
            alerts.append(Alert(site.ssl_expires, site.name, f'SSL expires · {site.client.name}', url, 'lock',
                                'late' if site.ssl_expires < today else ''))
    alerts.sort(key=lambda alert: (alert.day, alert.label))
    return alerts[:limit]
