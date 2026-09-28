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
