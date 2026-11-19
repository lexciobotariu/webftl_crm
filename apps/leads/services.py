"""Moving a lead along the board and turning it into a client."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.clients.models import Client, ClientContact, ClientMessage
from apps.invoices.models import Estimate
from apps.notes.models import Note

from .models import Lead, LeadStatus


def visible_leads(user):
    """Every lead, for someone with the Leads module; none otherwise."""
    if not user.has_app_permission('access_leads'):
        return Lead.objects.none()
    return Lead.objects.select_related('status', 'source', 'assignee', 'currency', 'client')


def move(lead, status, lost_reason=None):
    """Put the lead in ``status``. Won only comes from converting it; a client stays won."""
    if status.kind == LeadStatus.WON and not lead.is_converted:
        raise ValidationError('A lead is won when it becomes a client: use "Convert to client".')
    if lead.is_converted and status.kind != LeadStatus.WON:
        raise ValidationError('This lead is a client now, so it stays won.')
    lead.status = status
    fields = ['status', 'updated_at']
    if lost_reason is not None:
        lead.lost_reason = lost_reason.strip()
        fields.append('lost_reason')
    lead.save(update_fields=fields)
    return lead


def _new_client(lead, user):
    return Client.objects.create(
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        address=lead.address,
        tax_id=lead.tax_id,
        currency=lead.currency,
        notes=lead.description,
        created_by=user,
    )


def _add_contact(client, lead):
    """The lead's contact person on the client: Primary and Billing when the client has none."""
    name = lead.contact_name or (lead.name if lead.email or lead.phone else '')
    if not name:
        return None
    if lead.email and client.contacts.filter(email__iexact=lead.email).exists():
        return None
    return ClientContact.objects.create(
        client=client,
        name=name,
        email=lead.email,
        phone=lead.phone,
        is_primary=not client.contacts.filter(is_primary=True).exists(),
        is_billing=not client.contacts.filter(is_billing=True).exists(),
    )


def convert(lead, *, user, client=None, project_name='', project_estimate=None):
    """Make ``lead`` a client and move its estimates, emails and notes there.

    ``client`` is an existing client to join; without it a new client is made
    from the lead. With ``project_name`` a project is created on the client and
    ``project_estimate`` (one of the lead's estimates) is linked to it.
    Returns ``(client, project)``.
    """
    from apps.projects.models import Project, ProjectAccess

    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead.pk)
        if lead.is_converted:
            raise ValidationError('This lead is already a client.')
        won = LeadStatus.first_of(LeadStatus.WON)
        if won is None:
            raise ValidationError('Add a Won status in Settings > Lead statuses first.')
        if client is None:
            client = _new_client(lead, user)
        else:
            if client.is_archived:
                raise ValidationError('That client is archived.')
            codes = set(lead.estimates.exclude(currency_code='').values_list('currency_code', flat=True))
            if client.currency_id and codes - {client.currency.code}:
                raise ValidationError(
                    f'The lead\'s estimates are in {", ".join(sorted(codes))} and {client.name} is invoiced in '
                    f'{client.currency.code}. Choose a new client instead.'
                )
        _add_contact(client, lead)

        Estimate.objects.filter(lead=lead, client__isnull=True).update(client=client)
        ClientMessage.objects.filter(lead=lead, client__isnull=True).update(client=client)
        for note in lead.lead_notes.select_related('author'):
            Note.objects.create(
                client=client,
                title=f'From the lead, {timezone.localtime(note.created_at):%d %b %Y}',
                description=note.body,
                created_by=note.author or user,
            )

        project = None
        if project_name.strip():
            project = Project.objects.create(client=client, name=project_name.strip())
            ProjectAccess.objects.get_or_create(project=project, user=user)
            if project_estimate is not None:
                Estimate.objects.filter(
                    Q(pk=project_estimate.pk), Q(lead=lead), Q(project__isnull=True),
                ).update(project=project)

        lead.client = client
        lead.converted_at = timezone.now()
        lead.status = won
        lead.next_follow_up = None
        lead.save(update_fields=['client', 'converted_at', 'status', 'next_follow_up', 'updated_at'])
        return client, project
