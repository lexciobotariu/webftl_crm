from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.notifications.services import notify_assigned, withdraw_assigned

from .durations import format_minutes
from .models import Task, TaskActivity

# TaskActivity.old_value and new_value are 255 characters; titles go up to 1000.
VALUE_LENGTH = 255


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
            instance._old_start_date = old_task.start_date
            instance._old_billable = old_task.billable
            instance._old_title = old_task.title
            instance._old_description = old_task.description
            instance._old_estimate_minutes = old_task.estimate_minutes
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
        if user is not None:
            notify_assigned(instance, user)
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
        withdraw_assigned(instance, instance._old_assignee)
        if user is not None:
            notify_assigned(instance, user)

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
        # With the year: the row stays in the timeline long after the year turns.
        old_date = instance._old_due_date.strftime('%b %d, %Y') if instance._old_due_date else 'None'
        new_date = instance.due_date.strftime('%b %d, %Y') if instance.due_date else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='due_date_change',
            old_value=old_date,
            new_value=new_date,
            content=f'changed due date to {new_date}'
        )

    if hasattr(instance, '_old_start_date') and instance._old_start_date != instance.start_date:
        old_date = instance._old_start_date.strftime('%b %d, %Y') if instance._old_start_date else 'None'
        new_date = instance.start_date.strftime('%b %d, %Y') if instance.start_date else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='start_date_change',
            old_value=old_date,
            new_value=new_date,
            content=f'changed start date to {new_date}' if instance.start_date else 'removed the start date'
        )

    if hasattr(instance, '_old_billable') and instance._old_billable != instance.billable:
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='billable_change',
            old_value='Billable' if instance._old_billable else 'Non-billable',
            new_value='Billable' if instance.billable else 'Non-billable',
            content='marked the task billable' if instance.billable else 'marked the task non-billable'
        )

    if hasattr(instance, '_old_title') and instance._old_title != instance.title:
        new_title = instance.title[:VALUE_LENGTH]
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='title_change',
            old_value=instance._old_title[:VALUE_LENGTH],
            new_value=new_title,
            content=f'changed the title to {new_title}'
        )

    if hasattr(instance, '_old_description') and (
        (instance._old_description or '').strip() != (instance.description or '').strip()
    ):
        # No diff: descriptions are long, and the row only says that it changed.
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='description_change',
            content='updated the description'
        )

    if hasattr(instance, '_old_estimate_minutes') and instance._old_estimate_minutes != instance.estimate_minutes:
        old_label = format_minutes(instance._old_estimate_minutes)
        new_label = format_minutes(instance.estimate_minutes)
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='estimate_change',
            old_value=old_label,
            new_value=new_label,
            content=f'set the estimate to {new_label}' if new_label else 'removed the estimate'
        )
