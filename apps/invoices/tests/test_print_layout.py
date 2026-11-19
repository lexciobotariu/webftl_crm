from django.template.loader import render_to_string


def _meta_rules():
    css = render_to_string('invoices/partials/document_print_style.html', {'for_pdf': True})
    return [line for line in css.splitlines() if line.strip().startswith('.meta')]


def test_detail_boxes_wrap_long_values_instead_of_cutting_them():
    """Company, address, email and project used to end in "…" on one line (INV-0049)."""
    rules = '\n'.join(_meta_rules())
    assert 'ellipsis' not in rules
    assert 'nowrap' not in rules
    assert 'overflow: hidden' not in rules
    assert 'overflow-wrap: anywhere' in rules


def test_label_column_fits_payment_terms_in_the_pdf_font():
    """30mm was too narrow for "PAYMENT TERMS" in DejaVu Sans, the font the server draws PDFs with."""
    label = next(rule for rule in _meta_rules() if rule.strip().startswith('.meta th {'))
    assert 'width: 36mm' in label
