from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0012_task_number_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='number',
            field=models.PositiveIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.UniqueConstraint(
                fields=('project', 'number'), name='unique_task_number_per_project'
            ),
        ),
    ]
