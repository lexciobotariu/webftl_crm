from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0010_my_tasks_view'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='number',
            field=models.PositiveIntegerField(editable=False, null=True),
        ),
    ]
