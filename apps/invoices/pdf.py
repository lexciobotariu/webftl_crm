"""The invoice as a PDF, drawn from the same template as the print page."""
from django.template.loader import render_to_string


def invoice_pdf(invoice):
    from weasyprint import HTML

    html = render_to_string('invoices/invoice_print.html', {'invoice': invoice, 'for_pdf': True})
    return HTML(string=html).write_pdf()


def invoice_pdf_filename(invoice):
    return f'{invoice.number_label}.pdf'
