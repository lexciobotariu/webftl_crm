"""Maintenance: agreements to look after a client's sites, whoever built them.

A **Site** is something we look after (a website, a shop, an app): where it
lives, who built it, when its domain and certificate expire, and the logins we
need for it (encrypted). A **MaintenancePlan** is the agreement: price per
billing period, hours included each month, renewal, status. Each plan owns a
project, created with it, where its tasks, time and notes live, so everything
tasks can do works for maintenance too. The plan's project is billed at a fixed
price, so its time is never billed by the hour; extra hours go on an invoice
through "Add extra hours" (``MaintenanceOverage``).

A daily job (``create_recurring_invoices``) also creates each plan's checks
task (``MaintenanceCheckRun``) and renews or ends plans past their date.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.fields import EncryptedCharField

# Months in each billing or check period.
MONTHLY = 'monthly'
QUARTERLY = 'quarterly'
YEARLY = 'yearly'
FREQUENCY_CHOICES = [(MONTHLY, 'Monthly'), (QUARTERLY, 'Every 3 months'), (YEARLY, 'Yearly')]
FREQUENCY_MONTHS = {MONTHLY: 1, QUARTERLY: 3, YEARLY: 12}

# Dates closer than this show on the dashboard.
SOON = timedelta(days=30)


def safe_link(url):
    """``url`` when it is safe to render as a link, else ''."""
    url = url or ''
    return url if url.lower().startswith(('https://', 'http://')) else ''


class Site(models.Model):
    US = 'us'
    OTHER = 'other'
    BUILT_BY_CHOICES = [(US, 'Us'), (OTHER, 'Someone else')]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500, blank=True)
    built_by = models.CharField(max_length=10, choices=BUILT_BY_CHOICES, default=US)
    # Who built it, when it was not us (an agency, a freelancer).
    built_by_name = models.CharField(max_length=255, blank=True)
    # The project we built it in, when we did.
    project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='sites',
    )
    platform = models.CharField(max_length=100, blank=True, help_text='WordPress, Django, Shopify, ...')
    hosting = models.CharField(max_length=255, blank=True)
    domain_registrar = models.CharField(max_length=255, blank=True)
    domain_expires = models.DateField(null=True, blank=True)
    ssl_expires = models.DateField(null=True, blank=True)
    repo_url = models.URLField(max_length=500, blank=True)
    admin_url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'pk']

    def __str__(self):
        return self.name

    @property
    def link(self):
        return safe_link(self.url)

    @property
    def admin_link(self):
        return safe_link(self.admin_url)

    @property
    def repo_link(self):
        return safe_link(self.repo_url)

    @property
    def built_by_label(self):
        if self.built_by == self.US:
            return 'Us'
        return self.built_by_name or 'Someone else'

    def expiry_state(self, day, today=None):
        """'expired', 'soon' or '' for an expiry date."""
        if day is None:
            return ''
        today = today or timezone.localdate()
        if day < today:
            return 'expired'
        if day <= today + SOON:
            return 'soon'
        return ''

    @property
    def domain_state(self):
        return self.expiry_state(self.domain_expires)

    @property
    def ssl_state(self):
        return self.expiry_state(self.ssl_expires)


class SiteCredential(models.Model):
    """A login for a site (hosting, admin, FTP, database). Username, password and notes are encrypted."""

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='credentials')
    label = models.CharField(max_length=100)
    url = models.CharField(max_length=500, blank=True)
    # Sizes are for the encrypted text; the form limits what is typed.
    username = EncryptedCharField(max_length=1000, blank=True)
    password = EncryptedCharField(max_length=1000, blank=True)
    notes = EncryptedCharField(max_length=3000, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['label', 'pk']

    def __str__(self):
        return f'{self.site} · {self.label}'

    @property
    def link(self):
        return safe_link(self.url)


class MaintenancePlan(models.Model):
    ACTIVE = 'active'
    PAUSED = 'paused'
    ENDED = 'ended'
    STATUS_CHOICES = [(ACTIVE, 'Active'), (PAUSED, 'Paused'), (ENDED, 'Ended')]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='maintenance_plans')
    name = models.CharField(max_length=255)
    sites = models.ManyToManyField(Site, blank=True, related_name='plans')
    # Tasks, time and notes of the plan live here. Created with the plan.
    project = models.OneToOneField(
        'projects.Project', on_delete=models.PROTECT, related_name='maintenance_plan',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    description = models.TextField(blank=True, help_text="What the plan covers.")

    start_date = models.DateField()
    # When the agreement renews (auto_renew) or ends. Blank: open-ended.
    renewal_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    # How far a renewal moves the date.
    term_months = models.PositiveSmallIntegerField(default=12)
    # The renewal shows on the dashboard this many days before.
    notice_days = models.PositiveSmallIntegerField(default=30)

    # Price per billing period, in the client's currency.
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default=MONTHLY)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Hours included each calendar month. 0: no limit. Unused hours do not roll over.
    included_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # The hourly price of hours past the included ones.
    overage_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # The plan's repeating invoice, once set up.
    recurring_invoice = models.OneToOneField(
        'invoices.RecurringInvoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenance_plan',
    )

    check_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default=MONTHLY)
    # The start of the next period that gets a checks task. Blank until there are checks.
    next_check_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client__name', 'name', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__isnull=True) | models.Q(price__gte=0),
                name='maintenance_price_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(included_hours__gte=0), name='maintenance_hours_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(overage_rate__isnull=True) | models.Q(overage_rate__gte=0),
                name='maintenance_rate_non_negative',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == self.ACTIVE

    @property
    def has_hour_limit(self):
        return self.included_hours > 0

    @property
    def renewal_state(self):
        """'due' when the renewal date is within the notice period (or past), else ''."""
        if not self.renewal_date or self.status == self.ENDED:
            return ''
        if self.renewal_date <= timezone.localdate() + timedelta(days=self.notice_days):
            return 'due'
        return ''


class MaintenanceCheck(models.Model):
    """One line of a plan's checklist. Each period's checks task gets one sub-task per line."""

    plan = models.ForeignKey(MaintenancePlan, on_delete=models.CASCADE, related_name='checks')
    title = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']

    def __str__(self):
        return self.title


class MaintenanceCheckRun(models.Model):
    """The checks task created for one period. One per plan and period, so a period is never created twice."""

    plan = models.ForeignKey(MaintenancePlan, on_delete=models.CASCADE, related_name='check_runs')
    period_start = models.DateField()
    task = models.ForeignKey('tasks.Task', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'period_start'], name='maintenance_one_run_per_period'),
        ]


class MaintenanceOverage(models.Model):
    """Extra hours of one month, put on an invoice. One per plan and month, so they are billed once."""

    plan = models.ForeignKey(MaintenancePlan, on_delete=models.CASCADE, related_name='overages')
    month = models.DateField(help_text='The first day of the month.')
    hours = models.DecimalField(max_digits=8, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    invoice = models.ForeignKey(
        'invoices.Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    invoice_line = models.ForeignKey(
        'invoices.InvoiceLine', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'month'], name='maintenance_one_overage_per_month'),
        ]


class MaintenanceReport(models.Model):
    """The monthly report of a plan. Its figures come from the month's time and tasks; we write the introduction.

    A report the client has been sent shows in the portal.
    """

    plan = models.ForeignKey(MaintenancePlan, on_delete=models.CASCADE, related_name='reports')
    month = models.DateField(help_text='The first day of the month.')
    introduction = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'month'], name='maintenance_one_report_per_month'),
        ]

    def __str__(self):
        return f'{self.plan} · {self.month:%B %Y}'
