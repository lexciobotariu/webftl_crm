import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0015_project_key_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='key',
            field=models.CharField(
                blank=True,
                max_length=6,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        '^[A-Z][A-Z0-9]{1,5}$',
                        '2 to 6 capital letters or digits, starting with a letter.',
                    )
                ],
            ),
        ),
    ]
