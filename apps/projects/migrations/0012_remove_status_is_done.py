from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0011_status_category_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='status',
            name='is_done',
        ),
    ]
