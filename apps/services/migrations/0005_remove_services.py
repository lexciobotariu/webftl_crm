from django.db import migrations


class Migration(migrations.Migration):
    """Services was removed in 0.48.0. Sites and logins moved to the Vault first.

    Projects, their tasks and time, and recurring invoices stay: a service only
    pointed at them. Tables go children first, so this runs back too (empty).
    """

    dependencies = [
        ("maintenance", "0004_remove_checks"),
        ("vault", "0002_from_sites"),
        ("tasks", "0030_repeat_from_task"),
    ]

    operations = [
        migrations.DeleteModel(name="ServiceOverage"),
        migrations.DeleteModel(name="ServiceReport"),
        migrations.DeleteModel(name="Service"),
        migrations.DeleteModel(name="SiteCredential"),
        migrations.DeleteModel(name="Site"),
        migrations.DeleteModel(name="ServiceType"),
    ]
