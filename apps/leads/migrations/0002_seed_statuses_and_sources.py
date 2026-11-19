from django.db import migrations

STATUSES = (
    ('New', 'open', 'blue'),
    ('Contacted', 'open', 'violet'),
    ('Proposal sent', 'open', 'amber'),
    ('Won', 'won', 'green'),
    ('Lost', 'lost', 'red'),
)
SOURCES = ('Website', 'Referral', 'LinkedIn', 'Email', 'Other')


def seed(apps, schema_editor):
    LeadStatus = apps.get_model('leads', 'LeadStatus')
    LeadSource = apps.get_model('leads', 'LeadSource')
    if not LeadStatus.objects.exists():
        for position, (name, kind, color) in enumerate(STATUSES):
            LeadStatus.objects.create(name=name, kind=kind, color=color, position=position)
    if not LeadSource.objects.exists():
        for position, name in enumerate(SOURCES):
            LeadSource.objects.create(name=name, position=position)


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
