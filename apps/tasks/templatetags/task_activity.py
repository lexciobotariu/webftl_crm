from django import template

from apps.tasks.models import can_edit_task

register = template.Library()


@register.simple_tag
def task_activities(task, user):
    """A task's activity with authors loaded, each marked ``can_change``.

    One query for the rows, and at most one more to ask whether ``user`` may
    still edit the task, instead of a query per comment.
    """
    activities = list(task.activities.select_related('user'))
    may_edit = None
    for activity in activities:
        activity.can_change = False
        if activity.activity_type != 'comment':
            continue
        if user.is_admin:
            activity.can_change = True
        elif activity.user_id == user.pk:
            if may_edit is None:
                may_edit = can_edit_task(user, task)
            activity.can_change = may_edit
    return activities
