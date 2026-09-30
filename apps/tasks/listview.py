"""Turns a page of tasks plus a spec into what the list template draws.

Kept apart from the spec (which only knows about URLs) and from the queryset
(which only knows about SQL), so the view itself stays thin.
"""
from itertools import groupby

from django.db.models import Q
from django.db.models.functions import Lower

from apps.accounts.models import User
from apps.projects.models import get_assignable_users

from .models import PRIORITY_FILTER_CHOICES, Task, priority_filter_options

PRIORITY_LABELS = dict(PRIORITY_FILTER_CHOICES)
PRIORITY_LABELS[''] = PRIORITY_LABELS['none']


def build_groups(tasks, spec, counts):
    """Group ``tasks`` (already ordered for ``spec``) into header plus rows.

    ``counts`` is :meth:`TaskQuerySet.group_counts`: headers show how many tasks
    match the filters, while ``rows`` holds only the page that was loaded.
    Each group is a dict with ``key``, ``kind`` (what the header icon shows),
    ``label``, ``count``, and the ``status``/``user``/``priority`` it stands for.
    """
    tasks = list(tasks)
    if spec.group == 'none':
        return [{'key': 'all', 'kind': None, 'label': None, 'count': len(tasks), 'rows': tasks}]

    def key_of(task):
        if spec.group == 'status':
            return task.status_id
        if spec.group == 'assignee':
            return task.assignee_id
        return task.priority

    groups = []
    for key, rows in groupby(tasks, key=key_of):
        rows = list(rows)
        first = rows[0]
        group = {
            'key': f'{spec.group}-{key if key not in (None, "") else "none"}',
            'kind': spec.group,
            'count': counts.get(key, len(rows)),
            'rows': rows,
            'status': first.status if spec.group == 'status' else None,
            'user': first.assignee if spec.group == 'assignee' else None,
            'priority': first.priority if spec.group == 'priority' else None,
        }
        if spec.group == 'status':
            group['label'] = first.status.name
        elif spec.group == 'assignee':
            group['label'] = (
                (first.assignee.name or first.assignee.email) if first.assignee else 'Unassigned'
            )
        else:
            group['label'] = PRIORITY_LABELS[first.priority]
        groups.append(group)
    return groups


def filter_options(statuses, spec, assignable_users, labels):
    """Checkbox options for the Filter popover, reflecting ``spec``.

    Statuses read "checked means shown". Assignees and labels read "checked means
    only these"; none checked is no filter. ``statuses`` and ``labels`` are the
    project's rows, already loaded by the view.
    """
    wanted_assignees = set(spec.assignees)
    assignees = [{
        'value': 'none',
        'label': 'No assignee',
        'checked': 'none' in wanted_assignees,
    }]
    assignees += [
        {'value': str(user.pk), 'label': user.name or user.email, 'checked': str(user.pk) in wanted_assignees}
        for user in assignable_users
    ]
    return {
        'status_options': [
            {
                'value': status.pk,
                'label': status.name,
                'checked': status.pk not in spec.hidden_statuses,
            }
            for status in statuses
        ],
        'priority_options': priority_filter_options(spec.priorities),
        'assignee_options': assignees,
        'label_options': [
            {'value': label.pk, 'label': label.name, 'checked': label.pk in spec.labels}
            for label in labels
        ],
    }


def project_assignees(project):
    """People a task on ``project`` can be filtered by.

    Everyone who can be assigned now, plus anyone who still holds a task here,
    including people who have since been deactivated.
    """
    assignable = get_assignable_users(project).values('pk')
    holders = Task.objects.filter(project=project, assignee__isnull=False).values('assignee_id')
    # Same order as the assignee groups in the list (``TaskQuerySet.ordered_for``).
    return User.objects.filter(Q(pk__in=assignable) | Q(pk__in=holders)).order_by(
        Lower('name'), 'email'
    )
