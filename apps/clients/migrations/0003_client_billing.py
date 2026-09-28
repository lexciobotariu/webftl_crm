from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0002_client_created_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='billing_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='client',
            name='billing_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='tax_id',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
