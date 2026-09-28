from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('legal_name', models.CharField(blank=True, max_length=255)),
                ('address', models.TextField(blank=True)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('tax_id', models.CharField(blank=True, max_length=64)),
            ],
            options={
                'verbose_name_plural': 'company',
            },
        ),
        migrations.CreateModel(
            name='Currency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=3, unique=True)),
                ('name', models.CharField(max_length=64)),
                ('symbol', models.CharField(max_length=16)),
            ],
            options={
                'verbose_name_plural': 'currencies',
                'ordering': ['code'],
            },
        ),
    ]
