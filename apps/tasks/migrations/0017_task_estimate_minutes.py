from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0016_task_closed_at_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='estimate_minutes',
            field=models.PositiveIntegerField(blank=True, help_text='Estimated time, in minutes', null=True),
        ),
    ]
