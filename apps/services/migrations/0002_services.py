"""Maintenance becomes Services (0.47.0): the same tables, renamed, plus service types.

Renames only: every plan, site, login, overage and report keeps its row and id.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(old_name="MaintenancePlan", new_name="Service"),
        migrations.RenameModel(old_name="MaintenanceOverage", new_name="ServiceOverage"),
        migrations.RenameModel(old_name="MaintenanceReport", new_name="ServiceReport"),
        migrations.RenameField(model_name="serviceoverage", old_name="plan", new_name="service"),
        migrations.RenameField(model_name="servicereport", old_name="plan", new_name="service"),
        # The unique constraints follow the renamed column in the database; only Django's record of them changes.
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveConstraint(model_name="serviceoverage", name="maintenance_one_overage_per_month"),
            migrations.AddConstraint(
                model_name="serviceoverage",
                constraint=models.UniqueConstraint(fields=("service", "month"), name="maintenance_one_overage_per_month"),
            ),
            migrations.RemoveConstraint(model_name="servicereport", name="maintenance_one_report_per_month"),
            migrations.AddConstraint(
                model_name="servicereport",
                constraint=models.UniqueConstraint(fields=("service", "month"), name="maintenance_one_report_per_month"),
            ),
        ]),
        migrations.AlterField(
            model_name="service",
            name="client",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="services", to="clients.client",
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="project",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT, related_name="service", to="projects.project",
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="recurring_invoice",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="service", to="invoices.recurringinvoice",
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="sites",
            field=models.ManyToManyField(blank=True, related_name="services", to="maintenance.site"),
        ),
        migrations.AlterField(
            model_name="service",
            name="description",
            field=models.TextField(blank=True, help_text="What the service covers."),
        ),
        migrations.CreateModel(
            name="ServiceType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                (
                    "frequency",
                    models.CharField(
                        choices=[("monthly", "Monthly"), ("quarterly", "Every 3 months"), ("yearly", "Yearly")],
                        default="monthly", max_length=10,
                    ),
                ),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("included_hours", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("overage_rate", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("checklist_title", models.CharField(blank=True, default="Checks", max_length=200)),
                ("checklist", models.TextField(blank=True)),
                ("position", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["position", "name"]},
        ),
        migrations.AddField(
            model_name="service",
            name="service_type",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="services", to="maintenance.servicetype",
            ),
        ),
    ]
