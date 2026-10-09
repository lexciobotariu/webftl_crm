from django.conf import settings
from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    billing_name = models.CharField(max_length=255, blank=True)
    billing_email = models.EmailField(blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    currency = models.ForeignKey(
        'crm.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='clients',
    )
    notes = models.TextField(blank=True)
    # Set when the client is archived. An archived client keeps its projects,
    # invoices and history; it only leaves the default list and the pickers.
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_clients',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def bill_to_name(self):
        return self.billing_name or self.name

    @property
    def billing_contact(self):
        return self.contacts.filter(is_billing=True).first()

    @property
    def bill_to_email(self):
        """The billing email, else the billing contact's email, else the client email."""
        if self.billing_email:
            return self.billing_email
        contact = self.billing_contact
        return (contact.email if contact else '') or self.email

    @property
    def project_count(self):
        return self.projects.count()

    @property
    def is_archived(self):
        return self.archived_at is not None


class ClientContact(models.Model):
    """A person at a client. At most one is the primary contact and one the billing contact."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False, db_default=False)
    is_billing = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', '-is_billing', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['client'], condition=models.Q(is_primary=True), name='one_primary_contact_per_client',
            ),
            models.UniqueConstraint(
                fields=['client'], condition=models.Q(is_billing=True), name='one_billing_contact_per_client',
            ),
        ]

    def __str__(self):
        return self.name


class ClientMessage(models.Model):
    """One entry in a client's message log: a note the team wrote, or an email sent to the client.

    Notes are internal; the client never sees them. Emails are logged when they
    are sent, with whom they went to and whether sending worked.
    """

    NOTE = 'note'
    EMAIL = 'email'
    KIND_CHOICES = [(NOTE, 'Note'), (EMAIL, 'Email')]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='messages')
    project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='client_messages',
    )
    # Emails about an invoice point at it, so the invoice page lists them too.
    invoice = models.ForeignKey(
        'invoices.Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='emails',
    )
    estimate = models.ForeignKey(
        'invoices.Estimate', on_delete=models.SET_NULL, null=True, blank=True, related_name='emails',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=NOTE, db_default=NOTE)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    # Emails only: who it went to, and the error when sending failed.
    recipients = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='client_messages',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.subject or self.body[:50]

    @property
    def failed(self):
        return bool(self.error)


def messages_visible_to(user, client):
    """The client's log entries this user may read.

    Entries with no project, or on a project they can open. Invoice and estimate
    emails carry amounts, so they also need the invoices module and sight of
    that invoice or estimate.
    """
    from apps.invoices.models import visible_estimates, visible_invoices
    from apps.projects.models import visible_projects

    entries = client.messages.filter(
        models.Q(project__isnull=True) | models.Q(project__in=visible_projects(user))
    )
    if user.has_app_permission('access_invoices'):
        entries = entries.filter(
            models.Q(invoice__isnull=True) | models.Q(invoice__in=visible_invoices(user)),
            models.Q(estimate__isnull=True) | models.Q(estimate__in=visible_estimates(user)),
        )
    else:
        entries = entries.filter(invoice__isnull=True, estimate__isnull=True)
    return entries.select_related('author', 'project', 'invoice', 'estimate')


def active_clients(queryset):
    """Clients that are not archived: the ones offered when picking a client."""
    return queryset.filter(archived_at__isnull=True)


def visible_clients(user):
    """Clients this user may open on the dashboard, list, detail, edit, and delete.

    ``clients_view_all`` is every client. Without it, the distinct clients of
    projects where ``user`` has a ProjectAccess row, plus clients ``user`` created.
    ``role=admin`` bypasses the flag through ``User.has_app_permission``.
    Creating a client does not grant edit.

    Access is filtered through a primary-key subquery so two projects on
    the same client still count as one client.
    """
    if user.has_app_permission('clients_view_all'):
        return Client.objects.all()
    from apps.projects.models import ProjectAccess

    client_ids = ProjectAccess.objects.filter(user=user).values('project__client_id')
    return Client.objects.filter(models.Q(pk__in=client_ids) | models.Q(created_by=user))
