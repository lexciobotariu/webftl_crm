from django import template

from apps.invoices.models import format_money

register = template.Library()


@register.simple_tag
def format_invoice_amount(invoice, amount):
    """Format one invoice figure with the symbol placement stored on it."""
    return format_money(
        amount,
        symbol=invoice.currency_symbol,
        symbol_before=invoice.symbol_before,
    )


@register.simple_tag
def task_invoices(task):
    """The invoices this task's time is billed on, oldest first."""
    from apps.invoices.models import Invoice

    return list(
        Invoice.objects.filter(lines__time_entries__task=task).distinct().order_by('number')
    )


@register.simple_tag
def client_money(client, amount):
    """An amount in ``client``'s currency, or a plain number when it has none."""
    currency = getattr(client, 'currency', None)
    if currency is None:
        return f'{amount:.2f}'
    return format_money(amount, currency.symbol, currency.symbol_before)
