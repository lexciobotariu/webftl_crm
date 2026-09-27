from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ProjectMember
from .services import handle_member_removed


@receiver(post_delete, sender=ProjectMember)
def member_removed(sender, instance, **kwargs):
    """Deleting a membership clears assignee and does not delete time entries."""
    handle_member_removed(instance.project_id, instance.user_id)
