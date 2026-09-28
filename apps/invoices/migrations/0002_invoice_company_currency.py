from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='company_address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='invoice',
            name='company_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='invoice',
            name='company_legal_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='invoice',
            name='company_phone',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='invoice',
            name='company_tax_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='invoice',
            name='currency_code',
            field=models.CharField(blank=True, default='', max_length=3),
        ),
        migrations.AddField(
            model_name='invoice',
            name='currency_symbol',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]
