"""Turns a page of tasks plus a spec into what the list template draws.

Kept apart from the spec (which only knows about URLs) and from the queryset
(which only knows about SQL), so the view itself stays thin.
"""
from itertools import groupby

from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import redirect
from django_htmx.http import push_url, replace_url

from apps.accounts.models import User
from apps.projects.models import Status, get_assignable_users

from .models import PRIORITY_FILTER_CHOICES, Task, priority_filter_options
from .viewspec import TaskViewSpec

PRIORITY_LABELS = dict(PRIORITY_FILTER_CHOICES)
PRIORITY_LABELS[''] = PRIORITY_LABELS['none']
CATEGORY_LABELS = dict(Status.CATEGORY_CHOICES)
GROUP_LABELS = {
    'status': 'Status',
    'assignee': 'Assignee',
    'priority': 'Priority',
    'project': 'Project',
    'category': 'Status type',
    'none': 'No grouping',
}

# Only requests sent by the toolbar form (its element id) remember the view. A link
# from a colleague, a refresh after an edit, search-as-you-type and "Show more" all
# render what the URL says without changing what this person last chose.
TOOLBAR_TRIGGER = 'task-toolbar'


def resolve_view(request, *, options, model, lookup, page_url):
    """The plumbing every URL-driven task page shares.

    ``model`` holds one row per ``lookup`` (a ``ProjectTaskView`` for a project
    and person, a ``MyTasksView`` for a person) with the last view as ``params``.
    Returns a redirect for a bare URL, or ``(spec, from_toolbar)`` after saving
    (or dropping) the remembered view when the toolbar sent the request.

    A bare URL never renders. It resolves to the view this person last used, or to
    the default, so every entry in browser history says in full what it showed;
    Back can then never land on "whatever is saved now".
    """
    if not request.GET:
        saved = model.objects.filter(**lookup).first()
        restored = TaskViewSpec.from_params(saved.params if saved else {}, options)
        if saved is not None and restored.is_default:
            saved.delete()
        return redirect(f'{page_url}?{restored.to_query_string()}')

    spec = TaskViewSpec.from_params(request.GET, options)
    from_toolbar = bool(request.htmx) and request.htmx.trigger == TOOLBAR_TRIGGER
    if from_toolbar:
        if spec.is_default:
            model.objects.filter(**lookup).delete()
        else:
            model.objects.update_or_create(**lookup, defaults={'params': spec.to_saved_params()})
    return spec, from_toolbar


def apply_url_headers(response, request, spec, from_toolbar, page_url):
    """Tell htmx which URL the swapped page now stands for.

    A toolbar change is a new history entry; anything else (a refresh after an
    edit, search-as-you-type, "Show more") replaces the current one.
    """
    if request.htmx:
        canonical = f'{page_url}?{spec.to_query_string()}'
        (push_url if from_toolbar else replace_url)(response, canonical)
    return response


def build_groups(tasks, spec, counts):
    """Group ``tasks`` (already ordered for ``spec``) into header plus rows.

    ``counts`` is :meth:`TaskQuerySet.group_counts`: headers show how many tasks
    match the filters, while ``rows`` holds only the page that was loaded.
    Each group is a dict with ``key``, ``kind`` (what the header icon shows),
    ``label``, ``count``, and the ``status``/``user``/``priority``/``project``/
    ``category`` it stands for.
    """
    tasks = list(tasks)
    if spec.group == 'none':
        return [{'key': 'all', 'kind': None, 'label': None, 'count': len(tasks), 'rows': tasks}]

    def key_of(task):
        if spec.group == 'status':
            return task.status_id
        if spec.group == 'assignee':
            return task.assignee_id
        if spec.group == 'project':
            return task.project_id
        if spec.group == 'category':
            return task.status.category
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
            'project': first.project if spec.group == 'project' else None,
            'category': first.status.category if spec.group == 'category' else None,
        }
        if spec.group == 'status':
            group['label'] = first.status.name
        elif spec.group == 'assignee':
            group['label'] = (
                (first.assignee.name or first.assignee.email) if first.assignee else 'Unassigned'
            )
        elif spec.group == 'project':
            group['label'] = first.project.name
        elif spec.group == 'category':
            group['label'] = CATEGORY_LABELS[first.status.category]
        else:
            group['label'] = PRIORITY_LABELS[first.priority]
        groups.append(group)
    return groups


def filter_options(statuses, spec, assignable_users, labels, categories=()):
    """Checkbox options for the Filter popover, reflecting ``spec``.

    Statuses read "checked means shown". Status types read "checked means exactly
    these". Assignees and labels read "checked means only these"; none checked is
    no filter. A group the page has no use for is left out of the result, and the
    toolbar leaves out its popover section: ``statuses`` and ``labels`` are the
    project's rows, already loaded by the view, ``categories`` the status types
    the page filters by, and the assignee group follows the page's options.
    """
    options = {
        'priority_options': priority_filter_options(spec.priorities),
        'label_options': [
            {'value': label.pk, 'label': label.name, 'checked': label.pk in spec.labels}
            for label in labels
        ],
    }
    if statuses:
        options['status_options'] = [
            {
                'value': status.pk,
                'label': status.name,
                'checked': status.pk not in spec.hidden_statuses,
            }
            for status in statuses
        ]
    if categories:
        options['category_options'] = [
            {'value': value, 'label': label, 'checked': value in spec.categories}
            for value, label in Status.CATEGORY_CHOICES
            if value in categories
        ]
    if spec.options.has_assignee_filter:
        wanted_assignees = set(spec.assignees)
        options['assignee_options'] = [
            {'value': 'none', 'label': 'No assignee', 'checked': 'none' in wanted_assignees}
        ] + [
            {
                'value': str(user.pk),
                'label': user.name or user.email,
                'checked': str(user.pk) in wanted_assignees,
            }
            for user in assignable_users
        ]
    return options


def group_choices(options):
    """``(value, label)`` for the Display menu's "Group by", as the page allows."""
    return [(value, GROUP_LABELS[value]) for value in options.groups]


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
