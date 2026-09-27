import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_mark_done_statuses'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ProjectMember',
            new_name='ProjectAccess',
        ),
        migrations.RemoveField(
            model_name='projectaccess',
            name='role',
        ),
        migrations.AlterField(
            model_name='projectaccess',
            name='project',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='access',
                to='projects.project',
            ),
        ),
        migrations.AlterField(
            model_name='projectaccess',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='project_access',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
