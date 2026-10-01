from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0018_task_estimate_minutes_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='task',
            name='time_estimate',
        ),
    ]
