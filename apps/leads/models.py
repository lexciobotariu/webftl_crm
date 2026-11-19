"""Leads: people or companies we are talking to, before they become clients.

A lead never shows in Clients. It can get estimates (``Estimate.lead``) and
emails (``ClientMessage.lead``); converting it creates or picks a client and
moves those over, and the lead stays behind as Converted with a link to it.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class LeadStatus(models.Model):
    """A column of the leads board. Admins edit them in Settings > Leads.

    ``kind`` tells the app what a column means: Won is where a converted lead
    goes, Lost asks for a reason. There is always at least one of each.
    """

    OPEN = 'open'
    WON = 'won'
    LOST = 'lost'
    KIND_CHOICES = [(OPEN, 'Open'), (WON, 'Won'), (LOST, 'Lost')]
    COLOR_CHOICES = [
        ('zinc', 'Grey'), ('blue', 'Blue'), ('violet', 'Violet'), ('amber', 'Amber'),
        ('green', 'Green'), ('red', 'Red'),
    ]

    name = models.CharField(max_length=50)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=OPEN)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default='zinc')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']
        verbose_name_plural = 'lead statuses'

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.kind == self.OPEN

    @classmethod
    def first_of(cls, kind):
        return cls.objects.filter(kind=kind).first()


class LeadSource(models.Model):
    """Where a lead came from (Website, Referral, ...). Edited in Settings > Leads."""

    name = models.CharField(max_length=50, unique=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'name']

    def __str__(self):
        return self.name


class Lead(models.Model):
    name = models.CharField(max_length=255, help_text='Company, or the person when there is no company.')
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    currency = models.ForeignKey(
        'crm.Currency', on_delete=models.PROTECT, null=True, blank=True, related_name='leads',
    )
    status = models.ForeignKey(LeadStatus, on_delete=models.PROTECT, related_name='leads')
    source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads',
    )
    # What the work could be worth, in the lead's currency. Never added up across currencies.
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    lost_reason = models.TextField(blank=True)
    # Set by "Convert to client". The lead stays, so the history of the sale does too.
    client = models.ForeignKey(
        'clients.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads',
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_leads',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(value__isnull=True) | models.Q(value__gte=0),
                name='lead_value_non_negative',
            ),
        ]

    def __str__(self):
        return self.name

    # The names estimates read when they copy the recipient (invoices.services).
    @property
    def bill_to_name(self):
        return self.name

    @property
    def bill_to_email(self):
        return self.email

    @property
    def is_converted(self):
        return self.client_id is not None

    @property
    def follow_up_state(self):
        """'overdue', 'today' or '' for the badge next to the follow-up date."""
        if not self.next_follow_up or self.is_converted:
            return ''
        today = timezone.localdate()
        if self.next_follow_up < today:
            return 'overdue'
        if self.next_follow_up == today:
            return 'today'
        return ''


class LeadNote(models.Model):
    """A note the team writes on a lead. Converting the lead copies them to the client's notes."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='lead_notes')
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='lead_notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.body[:50]
