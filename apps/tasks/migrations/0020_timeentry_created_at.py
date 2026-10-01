from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0019_remove_task_time_estimate'),
    ]

    operations = [
        migrations.AddField(
            model_name='timeentry',
            name='created_at',
            field=models.DateTimeField(null=True),
        ),
    ]
