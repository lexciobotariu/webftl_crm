import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
        ('clients', '0003_client_billing'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='currency',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='clients',
                to='crm.currency',
            ),
        ),
    ]
