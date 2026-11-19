"""The old checks are now a recurring task on each service's project (0003)."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0003_checks_to_recurring_tasks"),
    ]

    operations = [
        migrations.DeleteModel(name="MaintenanceCheckRun"),
        migrations.DeleteModel(name="MaintenanceCheck"),
        migrations.RemoveField(model_name="service", name="check_frequency"),
        migrations.RemoveField(model_name="service", name="next_check_date"),
    ]
