from django.apps import AppConfig


class ServicesConfig(AppConfig):
    """Removed in 0.48.0; kept for its migrations only (see models.py)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.services'
    label = 'maintenance'
    verbose_name = 'Services (removed)'
