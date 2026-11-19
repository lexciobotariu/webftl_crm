from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.services'
    # The module began as "Maintenance": the label keeps its tables and migrations.
    label = 'maintenance'
    verbose_name = 'Services'
