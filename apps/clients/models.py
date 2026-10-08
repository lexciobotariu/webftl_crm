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
    def bill_to_email(self):
        return self.billing_email or self.email

    @property
    def project_count(self):
        return self.projects.count()

    @property
    def is_archived(self):
        return self.archived_at is not None


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
