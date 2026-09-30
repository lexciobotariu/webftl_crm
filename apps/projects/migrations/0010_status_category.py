from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0009_task_list_priority_filters'),
    ]

    operations = [
        migrations.AddField(
            model_name='status',
            name='category',
            field=models.CharField(
                choices=[
                    ('backlog', 'Backlog'),
                    ('unstarted', 'Unstarted'),
                    ('started', 'Started'),
                    ('completed', 'Completed'),
                    ('canceled', 'Canceled'),
                ],
                default='unstarted',
                max_length=20,
            ),
        ),
    ]
