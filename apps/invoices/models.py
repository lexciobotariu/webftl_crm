from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.clients.models import Client, visible_clients

TWOPLACES = Decimal('0.01')
HUNDRED = Decimal('100')


class InvoiceLocked(Exception):
    """Lines, tax, dates, client, bill-to, company, and currency stay after send."""


class InvoiceHasPayments(Exception):
    """Delete is refused once a payment exists."""


def money(value):
    """Round a money figure to cents, half up."""
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def format_money(amount, symbol='', symbol_before=True):
    """Place a currency symbol on an amount.

    Before the amount there is no space (``£1.00``). After the amount there
    is one space (``1.00 €``). A blank symbol stays a plain number, which is
    how an invoice with no currency snapshot still prints.
    """
    figure = f'{money(amount):.2f}'
    if not symbol:
        return figure
    if symbol_before:
        return f'{symbol}{figure}'
    return f'{figure} {symbol}'


_LOCKED_AFTER_SEND = (
    'client_id',
    'issue_date',
    'due_date',
    'tax_rate',
    'bill_to_name',
    'bill_to_email',
    'bill_to_address',
    'bill_to_tax_id',
    'company_legal_name',
    'company_address',
    'company_email',
    'company_phone',
    'company_tax_id',
    'currency_code',
    'currency_symbol',
    'symbol_before',
    'number',
    'sent_at',
)


def invoice_is_sent(invoice_id):
    """Read ``sent_at`` from the database so a cached invoice cannot bypass the lock."""
    if not invoice_id:
        return False
    return Invoice.objects.filter(pk=invoice_id, sent_at__isnull=False).exists()


class Invoice(models.Model):
    """One invoice for one client.

    Totals and status are derived. ``sent_at`` empty means draft. Bill-to,
    company, and currency are a snapshot from create time, including which
    side the symbol sits on. Older rows have no currency snapshot, so those
    fields stay blank and amounts print as plain numbers.
    """

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    number = models.PositiveIntegerField(unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    bill_to_name = models.CharField(max_length=255)
    bill_to_email = models.EmailField(blank=True)
    bill_to_address = models.TextField(blank=True)
    bill_to_tax_id = models.CharField(max_length=64, blank=True)
    company_legal_name = models.CharField(max_length=255, blank=True, default='')
    company_address = models.TextField(blank=True, default='')
    company_email = models.EmailField(blank=True, default='')
    company_phone = models.CharField(max_length=50, blank=True, default='')
    company_tax_id = models.CharField(max_length=64, blank=True, default='')
    currency_code = models.CharField(max_length=3, blank=True, default='')
    currency_symbol = models.CharField(max_length=16, blank=True, default='')
    symbol_before = models.BooleanField(default=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-number']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tax_rate__gte=0) & models.Q(tax_rate__lte=100),
                name='invoice_tax_rate_between_0_and_100',
            ),
        ]

    def __str__(self):
        return self.number_label

    @property
    def number_label(self):
        return f'INV-{self.number:04d}'

    @property
    def is_draft(self):
        return self.sent_at is None

    @property
    def subtotal(self):
        total = Decimal('0.00')
        for line in self.lines.all():
            total += line.amount
        return total

    @property
    def tax_amount(self):
        return money(self.subtotal * self.tax_rate / HUNDRED)

    @property
    def total(self):
        return self.subtotal + self.tax_amount

    @property
    def amount_paid(self):
        total = Decimal('0.00')
        for payment in self.payments.all():
            total += payment.amount
        return total

    @property
    def balance(self):
        return self.total - self.amount_paid

    @property
    def status(self):
        """draft, sent, partial, paid, or overdue.

        Overdue is a sent invoice that is still owed and whose due date is
        before today. A draft stays a draft. A zero balance is paid.
        """
        if self.sent_at is None:
            return 'draft'
        if self.balance <= 0:
            return 'paid'
        if self.due_date < timezone.localdate():
            return 'overdue'
        if self.amount_paid > 0:
            return 'partial'
        return 'sent'

    @property
    def status_label(self):
        return {
            'draft': 'Draft',
            'sent': 'Sent',
            'partial': 'Partial',
            'paid': 'Paid',
            'overdue': 'Overdue',
        }[self.status]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = (
                Invoice.objects.filter(pk=self.pk).only(*_LOCKED_AFTER_SEND).first()
            )
            if previous and previous.sent_at is not None:
                locked_changed = any(
                    getattr(self, name) != getattr(previous, name)
                    for name in _LOCKED_AFTER_SEND
                )
                if locked_changed:
                    raise InvoiceLocked('This invoice has been sent.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.payments.exists():
            raise InvoiceHasPayments('This invoice has payments.')
        return super().delete(*args, **kwargs)


class InvoiceLine(models.Model):
    """A project line or a free-text line.

    A project line copies the project name into ``description`` when it is
    saved. A free-text line has no project.
    """

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_lines',
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='invoice_line_quantity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name='invoice_line_unit_price_non_negative',
            ),
        ]

    def __str__(self):
        return self.description

    @property
    def amount(self):
        return money(self.quantity * self.unit_price)

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors['quantity'] = 'Quantity must be greater than zero.'
        if self.unit_price is not None and self.unit_price < 0:
            errors['unit_price'] = 'Unit price cannot be negative.'
        if invoice_is_sent(self.invoice_id):
            raise InvoiceLocked('This invoice has been sent.')
        if self.project_id:
            if self.invoice_id and self.project.client_id != self.invoice.client_id:
                errors['project'] = 'Choose a project that belongs to this client.'
            else:
                self.description = self.project.name
        elif not (self.description or '').strip():
            errors['description'] = 'Enter a description for a free-text line.'
        else:
            self.description = self.description.strip()
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if invoice_is_sent(self.invoice_id):
            raise InvoiceLocked('This invoice has been sent.')
        return super().delete(*args, **kwargs)


class Payment(models.Model):
    """Money recorded against an invoice. The amount cannot exceed the balance."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='invoice_payment_amount_positive',
            ),
        ]

    def __str__(self):
        return f'{self.amount} on {self.date}'

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': 'Amount must be greater than zero.'})
        if self.invoice_id and self.amount > self.invoice.balance:
            raise ValidationError({'amount': 'Amount cannot exceed the balance.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


def visible_invoices(user):
    """Invoices this user may open.

    ``invoices_view_all`` is every invoice. Without it, invoices whose client
    is in ``visible_clients``. ``role=admin`` bypasses the flag through
    ``User.has_app_permission``. An invoice outside this set is a 404.
    """
    invoices = Invoice.objects.select_related('client').prefetch_related(
        'lines__project',
        'payments',
    )
    if user.has_app_permission('invoices_view_all'):
        return invoices
    return invoices.filter(client__in=visible_clients(user))
