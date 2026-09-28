from django.db import migrations, models

# Codes that print the symbol after the amount. Every other stored code
# prints it before. Rows with no code are left blank.
_SYMBOL_AFTER = ('EUR', 'RON')


def place_existing_invoice_symbols(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')
    coded = Invoice.objects.exclude(currency_code='')
    coded.filter(currency_code__in=_SYMBOL_AFTER).update(symbol_before=False)
    coded.exclude(currency_code__in=_SYMBOL_AFTER).update(symbol_before=True)


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0002_invoice_company_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='symbol_before',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(place_existing_invoice_symbols, migrations.RunPython.noop),
    ]
