from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0013_project_task_view'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='key',
            field=models.CharField(blank=True, default='', max_length=6),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='project',
            name='task_counter',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
