"""Turns a page of tasks plus a spec into what the list template draws.

Kept apart from the spec (which only knows about URLs) and from the queryset
(which only knows about SQL), so the view itself stays thin.
"""
from itertools import groupby

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django_htmx.http import push_url, replace_url

from apps.accounts.models import User
from apps.projects.models import Status, get_assignable_users

from .models import PRIORITY_FILTER_CHOICES, Task, priority_filter_options
from .viewspec import ASSIGNEE_NONE, CATEGORIES, TaskViewSpec, default_show_empty, default_sort

PRIORITY_LABELS = dict(PRIORITY_FILTER_CHOICES)
PRIORITY_LABELS[''] = PRIORITY_LABELS['none']
CATEGORY_LABELS = dict(Status.CATEGORY_CHOICES)
# Priority groups in list order (``_priority_rank``), with the filter's token for each.
PRIORITY_GROUP_ORDER = (
    ('urgent', 'urgent'), ('high', 'high'), ('medium', 'medium'), ('low', 'low'), ('', 'none'),
)
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


def _group_object(spec, task):
    """What a task's group stands for: a status, a user (or None), a project, a status type or a priority."""
    if spec.group == 'status':
        return task.status_id, task.status
    if spec.group == 'assignee':
        return task.assignee_id, task.assignee
    if spec.group == 'project':
        return task.project_id, task.project
    if spec.group == 'category':
        return task.status.category, task.status.category
    return task.priority, task.priority


def _make_group(spec, key, obj, rows, count):
    group = {
        'key': f'{spec.group}-{key if key not in (None, "") else "none"}',
        'kind': spec.group,
        'count': count,
        'rows': rows,
        'status': obj if spec.group == 'status' else None,
        'user': obj if spec.group == 'assignee' else None,
        'priority': obj if spec.group == 'priority' else None,
        'project': obj if spec.group == 'project' else None,
        'category': obj if spec.group == 'category' else None,
    }
    if spec.group == 'status':
        group['label'] = obj.name
    elif spec.group == 'assignee':
        group['label'] = (obj.name or obj.email) if obj else 'Unassigned'
    elif spec.group == 'project':
        group['label'] = obj.name
    elif spec.group == 'category':
        group['label'] = CATEGORY_LABELS.get(obj, obj)
    else:
        group['label'] = PRIORITY_LABELS[obj]
    # What the "+" on the header fills in for a new task. None for a group a
    # task cannot be created into (a project of My Tasks, a status type).
    if spec.group == 'status':
        group['create_query'] = f'status={key}'
    elif spec.group == 'priority':
        group['create_query'] = f'priority={key}' if key else ''
    elif spec.group == 'assignee':
        group['create_query'] = f'assignee={key}' if key else ''
    else:
        group['create_query'] = None
    return group


def row_keys(task, spec):
    """``"<group>|<sort>"``: where a row sits in the list for ``spec``.

    After a quick edit the page asks for the changed row alone (:func:`render_task_row`)
    and swaps it in place only when this string is unchanged; a row that moved to
    another group or another place in its group needs the whole view again. On the
    board a card's place is its column.
    """
    if spec.layout == 'board':
        return str(task.status_id)
    group = '' if spec.group == 'none' else _group_object(spec, task)[0]
    if spec.sort == 'manual':
        sort = f'{task.status_id}:{task.order}'
    elif spec.sort == 'due':
        sort = task.due_date
    elif spec.sort == 'title':
        sort = task.title.lower()
    elif spec.sort == 'created':
        sort = task.created_at.isoformat()
    elif spec.sort == 'updated':
        sort = task.updated_at.isoformat()
    else:
        sort = task.priority
    return f'{group}|{sort}'


def render_task_row(request, pk, matching, spec, context):
    """The one row (or card) ``pk`` as the page would draw it, or 204 when it left the view.

    ``?row=<pk>`` on a task page: what the quick menu asks for after an edit, so an
    edit that keeps the row where it was does not re-render the whole list.
    """
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return HttpResponse(status=400)
    tasks = matching.filter(pk=pk).select_related('project', 'status', 'assignee').prefetch_related('labels')
    if spec.layout == 'board':
        tasks = tasks.annotate(
            subtask_total=Count('subtasks', distinct=True),
            subtask_done=Count('subtasks', filter=Q(subtasks__completed=True), distinct=True),
        )
    task = tasks.first()
    if task is None:
        return HttpResponse(status=204)
    template = 'projects/partials/task_card.html' if spec.layout == 'board' else 'tasks/view/_list_row.html'
    return render(request, template, {**context, 'task': task, 'spec': spec})


def group_slots(spec, statuses=(), assignees=()):
    """``[(key, object)]``: every group the view could show, in list order, filters applied.

    What "Show empty groups" fills in. ``statuses`` and ``assignees`` are the
    project's rows (empty on My Tasks). Projects have no slots: My Tasks only
    lists the projects that hold one of the person's tasks.
    """
    if spec.group == 'status':
        return [
            (status.pk, status)
            for status in statuses
            if status.pk not in spec.hidden_statuses
            and (not spec.categories or status.category in spec.categories)
        ]
    if spec.group == 'assignee':
        wanted = set(spec.assignees)
        slots = [(user.pk, user) for user in assignees if not wanted or str(user.pk) in wanted]
        if not wanted or ASSIGNEE_NONE in wanted:
            slots.append((None, None))
        return slots
    if spec.group == 'priority':
        wanted = set(spec.priorities)
        return [
            (value, value)
            for value, token in PRIORITY_GROUP_ORDER
            if not wanted or token in wanted
        ]
    if spec.group == 'category':
        return [(value, value) for value in CATEGORIES if not spec.categories or value in spec.categories]
    return []


def build_groups(tasks, spec, counts, slots=()):
    """Group ``tasks`` (already ordered for ``spec``) into header plus rows.

    ``counts`` is :meth:`TaskQuerySet.group_counts`: headers show how many tasks
    match the filters, while ``rows`` holds only the page that was loaded.
    Each group is a dict with ``key``, ``kind`` (what the header icon shows),
    ``label``, ``count``, and the ``status``/``user``/``priority``/``project``/
    ``category`` it stands for.

    With ``spec.show_empty``, the ``slots`` (:func:`group_slots`) that have no
    task are listed too, in their place. When only a page of the tasks is loaded,
    empty groups after the last loaded one are left out: the groups still to
    come are not known yet.
    """
    tasks = list(tasks)
    if spec.group == 'none':
        return [{'key': 'all', 'kind': None, 'label': None, 'count': len(tasks), 'rows': tasks}]

    groups = []
    for key, rows in groupby(tasks, key=lambda task: _group_object(spec, task)[0]):
        rows = list(rows)
        _key, obj = _group_object(spec, rows[0])
        groups.append((key, _make_group(spec, key, obj, rows, counts.get(key, len(rows)))))

    if not (spec.show_empty and slots):
        return [group for _key, group in groups]

    present = {key for key, _group in groups}
    position = {key: index for index, (key, _obj) in enumerate(slots)}

    def empties(start, stop):
        return [
            _make_group(spec, key, obj, [], 0)
            for key, obj in slots[start:stop]
            if key not in present and not counts.get(key)
        ]

    merged = []
    done = 0
    for key, group in groups:
        if key in position and position[key] >= done:
            merged.extend(empties(done, position[key]))
            done = position[key] + 1
        merged.append(group)
    if sum(counts.values()) <= len(tasks):
        merged.extend(empties(done, len(slots)))
    return merged


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
        'archive_after_days': settings.TASK_ARCHIVE_AFTER_DAYS,
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
    """``(value, label, default sort, shows empty groups by default)`` for "Group by".

    Only the groupings the page allows. The defaults let the menu reset the sort
    and the empty-groups switch the way the server would read a fresh URL.
    """
    return [
        (value, GROUP_LABELS[value], default_sort(value, options), default_show_empty(value))
        for value in options.groups
    ]


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


def archived_matching(tasks, spec):
    """The archived tasks a view leaves out that pass its other filters.

    Empty when the view already shows archived tasks.
    """
    if spec.archived:
        return tasks.none()
    return tasks.matching(spec.replace(archived=True)).archived()
