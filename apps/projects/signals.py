from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ProjectAccess
from .services import handle_access_removed


@receiver(post_delete, sender=ProjectAccess)
def access_removed(sender, instance, **kwargs):
    """Deleting access clears assignee and does not delete time entries."""
    handle_access_removed(instance.project_id, instance.user_id)
