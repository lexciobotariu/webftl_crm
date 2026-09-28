from django.db import migrations, models

# Inserted only when the code is not already there. An existing row is left
# as it was, including whether it can be deleted.
DEFAULT_CURRENCIES = (
    ('EUR', 'Euro', '€', False),
    ('GBP', 'British Pound', '£', True),
    ('USD', 'US Dollar', '$', True),
    ('RON', 'Romanian Leu', 'lei', False),
)


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model('crm', 'Currency')
    for code, name, symbol, symbol_before in DEFAULT_CURRENCIES:
        Currency.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'symbol': symbol,
                'symbol_before': symbol_before,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='currency',
            name='symbol_before',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(seed_currencies, migrations.RunPython.noop),
    ]
