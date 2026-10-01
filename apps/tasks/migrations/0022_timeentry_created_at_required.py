import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0021_timeentry_created_at_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='timeentry',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
