from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0002_currency_symbol_before'),
    ]

    operations = [
        # default='dark' fills the company row that already exists.
        migrations.AddField(
            model_name='company',
            name='theme',
            field=models.CharField(
                choices=[('dark', 'Dark'), ('light', 'Light')],
                default='dark',
                max_length=5,
            ),
        ),
    ]
