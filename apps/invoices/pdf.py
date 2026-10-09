"""Invoices and estimates as PDFs, drawn from the same templates as their print pages."""
from django.template.loader import render_to_string

from .models import Estimate


def _pdf(template, context):
    from weasyprint import HTML

    return HTML(string=render_to_string(template, {**context, 'for_pdf': True})).write_pdf()


def invoice_pdf(invoice):
    return _pdf('invoices/invoice_print.html', {'invoice': invoice})


def estimate_pdf(estimate):
    return _pdf('invoices/estimate_print.html', {'estimate': estimate, 'invoice': estimate})


def document_pdf(document):
    return estimate_pdf(document) if isinstance(document, Estimate) else invoice_pdf(document)


def invoice_pdf_filename(document):
    return f'{document.number_label}.pdf'
