from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Task, TaskActivity


@receiver(pre_save, sender=Task)
def track_task_changes(sender, instance, **kwargs):
    """Store old values before save for comparison."""
    if instance.pk:
        try:
            old_task = Task.objects.select_related('status', 'assignee').get(pk=instance.pk)
            instance._old_status = old_task.status
            instance._old_assignee = old_task.assignee
            instance._old_priority = old_task.priority
            instance._old_due_date = old_task.due_date
        except Task.DoesNotExist:
            pass


@receiver(post_save, sender=Task)
def log_task_changes(sender, instance, created, **kwargs):
    """Log changes to TaskActivity after save."""
    user = getattr(instance, '_changed_by', None)

    if created:
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='created',
            content='created this task'
        )
        return

    # Check what changed
    if hasattr(instance, '_old_status') and instance._old_status != instance.status:
        old_name = instance._old_status.name if instance._old_status else 'None'
        new_name = instance.status.name if instance.status else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='status_change',
            old_value=old_name,
            new_value=new_name,
            content=f'changed status from {old_name} to {new_name}'
        )

    if hasattr(instance, '_old_assignee') and instance._old_assignee != instance.assignee:
        old_name = instance._old_assignee.name if instance._old_assignee else 'Unassigned'
        new_name = instance.assignee.name if instance.assignee else 'Unassigned'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='assignee_change',
            old_value=old_name,
            new_value=new_name,
            content=f'changed assignee from {old_name} to {new_name}'
        )

    if hasattr(instance, '_old_priority') and instance._old_priority != instance.priority:
        old_display = dict(Task.PRIORITY_CHOICES).get(instance._old_priority, 'None')
        new_display = dict(Task.PRIORITY_CHOICES).get(instance.priority, 'None')
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='priority_change',
            old_value=old_display,
            new_value=new_display,
            content=f'changed priority to {new_display}'
        )

    if hasattr(instance, '_old_due_date') and instance._old_due_date != instance.due_date:
        old_date = instance._old_due_date.strftime('%b %d') if instance._old_due_date else 'None'
        new_date = instance.due_date.strftime('%b %d') if instance.due_date else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='due_date_change',
            old_value=old_date,
            new_value=new_date,
            content=f'changed due date to {new_date}'
        )
