from django import template
from django.utils import timezone

from apps.tasks import services
from apps.tasks.durations import format_seconds
from apps.tasks.models import can_edit_task

register = template.Library()


@register.simple_tag
def task_activities(task, user):
    """A task's activity and the time ``user`` may see on it, in one list, oldest first.

    Every item has an ``item_type`` ('activity' or 'work') and a ``can_change`` flag.
    Time sits where it was logged (``created_at``), so an entry logged now for
    yesterday is next to today's activity. Two queries for the rows, and at most one
    more to ask whether ``user`` may still edit the task, instead of one per row.
    """
    activities = list(task.activities.select_related('user'))
    entries = list(services.entries_on_task(user, task))
    may_edit = None
    for activity in activities:
        activity.item_type = 'activity'
        activity.can_change = False
        if activity.activity_type != 'comment':
            continue
        if user.is_admin:
            activity.can_change = True
        elif activity.user_id == user.pk:
            if may_edit is None:
                may_edit = can_edit_task(user, task)
            activity.can_change = may_edit
    for entry in entries:
        entry.item_type = 'work'
        entry.can_change = False
        # Editing a running timer is not a thing: stop it first. Deleting it is.
        if user.is_admin:
            entry.can_change = True
        elif entry.user_id == user.pk:
            if may_edit is None:
                may_edit = can_edit_task(user, task)
            entry.can_change = may_edit
    # Activity before time at the same instant, then by id: a steady order.
    return sorted(
        [*activities, *entries],
        key=lambda item: (item.created_at, item.item_type == 'work', item.pk),
    )


@register.simple_tag
def work_log_totals(task, items, user):
    """The Work log's opening lines: time per person, from the entries already read.

    What ``user`` is not allowed to see is one "Others" line, worked out from the task's
    full total, so the sum matches the Time property. None when there is no time at all.
    """
    now = None
    people = {}
    seen = 0
    for item in items:
        if item.item_type != 'work':
            continue
        if now is None:
            now = timezone.now()
        seconds = services.entry_seconds(item, now)
        seen += seconds
        name = item.user.name or item.user.email
        people[name] = people.get(name, 0) + seconds

    total = seen
    others = 0
    if not (user.is_admin or user.has_app_permission('tasks_view_all')):
        total = services.logged_seconds_on_task(task)
        others = max(total - seen, 0)
    if not total:
        return None

    rows = [
        {'name': name, 'label': format_seconds(seconds, zero='0m')}
        for name, seconds in sorted(people.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    if others:
        rows.append({'name': 'Others', 'label': format_seconds(others)})
    return {'rows': rows, 'total': format_seconds(total, zero='0m')}


@register.simple_tag
def mention_people(task, user):
    """Who the @ menu in the comment box offers: people who can see ``task``, minus you."""
    from apps.notifications.services import people_who_can_see

    return [
        {'id': person.pk, 'name': person.name}
        for person in people_who_can_see(task).exclude(pk=user.pk)
        if person.name
    ]
