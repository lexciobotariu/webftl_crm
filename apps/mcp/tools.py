"""The tools Claude can call on the MCP endpoint.

Each tool is a thin layer over ``apps.tasks.services``: it turns names Claude
knows (``CUST-12``, a project key, a status or label name, an email) into
rows, calls the service as the signed-in person, and answers with plain JSON.
Permissions are the services' own, so a tool can never do more than the same
person could do on screen. There are no delete tools and nothing about money.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project, get_assignable_users
from apps.tasks import services
from apps.tasks.durations import format_minutes, format_seconds, parse_duration
from apps.tasks.models import Label, Subtask, Task, TimeEntry, visible_tasks

READ = 'tasks:read'
WRITE = 'tasks:write'
TIME = 'time'


class ToolError(Exception):
    """A refusal Claude should read and relay: bad input, not found, not allowed."""


@dataclass
class Param:
    type: str  # string, integer, boolean, date, string[] (date is a YYYY-MM-DD string)
    description: str
    required: bool = False
    nullable: bool = False
    enum: tuple = ()

    def schema(self):
        if self.type == 'date':
            schema = {'type': 'string', 'format': 'date'}
        elif self.type == 'string[]':
            schema = {'type': 'array', 'items': {'type': 'string'}}
        else:
            schema = {'type': self.type}
        if self.enum:
            schema['enum'] = list(self.enum)
        if self.nullable:
            schema['type'] = [schema['type'], 'null']
        schema['description'] = self.description
        return schema


@dataclass
class Tool:
    name: str
    title: str
    description: str
    scopes: tuple
    handler: object
    params: dict = field(default_factory=dict)
    read_only: bool = False
    idempotent: bool = False

    def definition(self):
        return {
            'name': self.name,
            'title': self.title,
            'description': self.description,
            'inputSchema': {
                'type': 'object',
                'properties': {name: param.schema() for name, param in self.params.items()},
                'required': [name for name, param in self.params.items() if param.required],
                'additionalProperties': False,
            },
            'annotations': {
                'title': self.title,
                'readOnlyHint': self.read_only,
                'destructiveHint': False,
                'idempotentHint': self.read_only or self.idempotent,
                'openWorldHint': False,
            },
        }

    def clean(self, arguments):
        """Check ``arguments`` against the params; dates become ``date`` objects."""
        if not isinstance(arguments, dict):
            raise ToolError('Arguments must be an object.')
        unknown = set(arguments) - set(self.params)
        if unknown:
            raise ToolError(f'Unknown argument(s): {", ".join(sorted(unknown))}.')
        cleaned = {}
        for name, param in self.params.items():
            if name not in arguments:
                if param.required:
                    raise ToolError(f'{name} is required.')
                continue
            value = arguments[name]
            if value is None:
                if not param.nullable:
                    raise ToolError(f'{name} cannot be null.')
                cleaned[name] = None
                continue
            cleaned[name] = _check_type(name, param, value)
        return cleaned


def _check_type(name, param, value):
    kind = param.type
    if kind in ('string', 'date') and not isinstance(value, str):
        raise ToolError(f'{name} must be a string.')
    if kind == 'integer' and (not isinstance(value, int) or isinstance(value, bool)):
        raise ToolError(f'{name} must be a whole number.')
    if kind == 'boolean' and not isinstance(value, bool):
        raise ToolError(f'{name} must be true or false.')
    if kind == 'string[]' and (
        not isinstance(value, list) or not all(isinstance(item, str) for item in value)
    ):
        raise ToolError(f'{name} must be a list of strings.')
    if param.enum and value not in param.enum:
        raise ToolError(f'{name} must be one of: {", ".join(param.enum)}.')
    if kind == 'date':
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ToolError(f'{name} must be a date like 2026-10-25.') from None
    return value


# --- Lookups -----------------------------------------------------------------


def _task(user, identifier):
    try:
        return services.find_task(user, identifier)
    except Task.DoesNotExist:
        raise ToolError(f'No task {identifier} that you can see. Use an id like CUST-12.') from None


def task_projects(user, include_closed=False):
    """Projects whose tasks ``user`` may see (the same rule as ``visible_tasks``)."""
    projects = Project.objects.select_related('client')
    if not (user.is_admin or user.has_app_permission('tasks_view_all')):
        if not user.has_app_permission('access_tasks'):
            return projects.none()
        projects = projects.filter(access__user=user).distinct()
    if not include_closed:
        projects = projects.filter(status__in=Project.OPEN_STATUSES)
    return projects.order_by('name')


def _project(user, key):
    project = task_projects(user, include_closed=True).filter(key__iexact=(key or '').strip()).first()
    if project is None:
        raise ToolError(f'No project with key {key} that you can see. list_projects shows the keys.')
    return project


def _status(project, name):
    status = project.statuses.filter(name__iexact=(name or '').strip()).first()
    if status is None:
        names = ', '.join(project.statuses.values_list('name', flat=True))
        raise ToolError(f'{project.key} has no status called {name}. Its statuses: {names}.')
    return status


def _label(project, name):
    label = project.labels.filter(name__iexact=(name or '').strip()).first()
    if label is None:
        names = ', '.join(project.labels.values_list('name', flat=True)) or 'none yet'
        raise ToolError(
            f'{project.key} has no label called {name}. Its labels: {names}. '
            'create_label adds one.'
        )
    return label


def _person(user, project, who):
    """``me`` or an email (or a name) of someone who can be assigned tasks on ``project``."""
    if who.strip().lower() == 'me':
        return user
    people = get_assignable_users(project)
    person = (
        people.filter(email__iexact=who.strip()).first()
        or people.filter(name__iexact=who.strip()).first()
    )
    if person is None:
        raise ToolError(f'Nobody called {who} can be assigned tasks on {project.key}. get_project lists the people.')
    return person


def _minutes(text):
    try:
        return parse_duration(text, bare_unit='hours')
    except ValueError as error:
        raise ToolError(str(error)) from None


# --- Shapes returned to Claude -------------------------------------------------


def _url(request, task):
    return request.build_absolute_uri(
        reverse('task_full_page', kwargs={'project_pk': task.project_id, 'task_pk': task.pk})
    )


def task_summary(request, task):
    return {
        'id': task.identifier,
        'title': task.title,
        'project': task.project.key,
        'status': task.status.name,
        'status_category': task.status.category,
        'assignee': task.assignee.email if task.assignee else None,
        'priority': task.priority or None,
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'billable': task.billable,
        'labels': [label.name for label in task.labels.all()],
        'url': _url(request, task),
    }


def task_details(request, user, task):
    data = task_summary(request, task)
    seconds = services.logged_seconds_on_task(task)
    running = TimeEntry.objects.filter(task=task, user=user, ended_at__isnull=True).first()
    comments = task.activities.filter(activity_type='comment').select_related('user').order_by('-created_at')[:10]
    data.update({
        'description': task.description,
        'start_date': task.start_date.isoformat() if task.start_date else None,
        'estimate': format_minutes(task.estimate_minutes) or None,
        'logged': format_seconds(seconds) if seconds else None,
        'my_timer_running': running is not None,
        'subtasks': [
            {'id': subtask.pk, 'title': subtask.title, 'done': subtask.completed}
            for subtask in task.subtasks.order_by('order', 'pk')
        ],
        'recent_comments': [
            {
                'author': comment.user.name if comment.user else None,
                'at': timezone.localtime(comment.created_at).isoformat(timespec='minutes'),
                'text': comment.content,
            }
            for comment in reversed(comments)
        ],
        'created_at': timezone.localtime(task.created_at).isoformat(timespec='minutes'),
    })
    return data


def _entry(request, entry):
    if entry is None:
        return None
    data = {
        'task': entry.task.identifier,
        'task_title': entry.task.title,
        'started_at': timezone.localtime(entry.started_at).isoformat(timespec='minutes'),
        'url': _url(request, entry.task),
    }
    if entry.ended_at:
        data['ended_at'] = timezone.localtime(entry.ended_at).isoformat(timespec='minutes')
        data['duration'] = entry.duration_label
    else:
        data['running_for'] = format_seconds((timezone.now() - entry.started_at).total_seconds())
    return data


# --- Read tools ------------------------------------------------------------------


def list_projects(request, user, include_closed=False):
    projects = task_projects(user, include_closed)
    return {'projects': [
        {
            'key': project.key,
            'name': project.name,
            'client': project.client.name if project.client_id else None,
            'status': project.get_status_display(),
            'billing': project.get_billing_type_display(),
        }
        for project in projects
    ]}


def get_project(request, user, project):
    project = _project(user, project)
    return {
        'key': project.key,
        'name': project.name,
        'statuses': [
            {'name': status.name, 'category': status.category}
            for status in project.statuses.order_by('order', 'pk')
        ],
        'labels': [
            {'name': label.name, 'color': label.color} for label in project.labels.order_by('name')
        ],
        'people': [
            {'name': person.name, 'email': person.email}
            for person in get_assignable_users(project).order_by('name')
        ],
    }


SEARCH_LIMIT = 100


def search_tasks(request, user, text=None, project=None, assignee=None, status=None,
                 label=None, include_closed=False, overdue=False, limit=25):
    tasks = visible_tasks(user).select_related('project', 'status', 'assignee').prefetch_related('labels')
    if project:
        project = _project(user, project)
        tasks = tasks.filter(project=project)
    if text:
        query = Q(title__icontains=text) | Q(description__icontains=text)
        # "CUST-12" or "12" typed as text should find that task too.
        number = text.rsplit('-', 1)[-1]
        if number.isdigit():
            query |= Q(number=int(number))
        tasks = tasks.filter(query)
    if assignee:
        if assignee.strip().lower() == 'me':
            tasks = tasks.filter(assignee=user)
        elif assignee.strip().lower() == 'nobody':
            tasks = tasks.filter(assignee__isnull=True)
        else:
            tasks = tasks.filter(Q(assignee__email__iexact=assignee) | Q(assignee__name__iexact=assignee))
    if status:
        tasks = tasks.filter(status__name__iexact=status)
    elif not include_closed:
        tasks = tasks.exclude(status__category__in=('completed', 'canceled'))
    if label:
        tasks = tasks.filter(labels__name__iexact=label)
    if overdue:
        tasks = tasks.overdue()
    limit = max(1, min(limit, SEARCH_LIMIT))
    rows = list(tasks.distinct().order_by('-updated_at')[:limit + 1])
    return {
        'tasks': [task_summary(request, task) for task in rows[:limit]],
        'more': len(rows) > limit,
    }


def get_task(request, user, task):
    return task_details(request, user, _task(user, task))


def my_timer(request, user):
    entry = TimeEntry.objects.filter(user=user, ended_at__isnull=True).select_related('task__project').first()
    now = timezone.now()
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    seconds = sum(
        services.entry_seconds(row, now)
        for row in TimeEntry.objects.filter(user=user, started_at__gte=start)
    )
    return {
        'running': _entry(request, entry),
        'logged_today': format_seconds(seconds) if seconds else '0m',
    }


# --- Write tools -----------------------------------------------------------------


def create_task(request, user, project, title, description='', status=None, assignee=None,
                priority=None, start_date=None, due_date=None, estimate=None, billable=True,
                labels=()):
    project = _project(user, project)
    task = services.create_task(
        project, user,
        title=title,
        description=description or '',
        status=_status(project, status) if status else None,
        assignee=_person(user, project, assignee) if assignee else None,
        priority=priority or '',
        start_date=start_date,
        due_date=due_date,
        estimate_minutes=_minutes(estimate) if estimate else None,
        billable=billable,
        labels=[_label(project, name) for name in labels or ()],
    )
    return task_summary(request, task)


def update_task(request, user, task, **changes):
    task = _task(user, task)
    values = {}
    for name, value in changes.items():
        if name == 'assignee':
            values['assignee'] = _person(user, task.project, value) if value else None
        elif name == 'estimate':
            values['estimate_minutes'] = _minutes(value) if value else None
        elif name == 'priority':
            values['priority'] = value or ''
        elif name == 'description':
            values['description'] = value or ''
        else:
            values[name] = value
    if not values:
        raise ToolError('Nothing to change: pass at least one field.')
    services.update_task(task, user, **values)
    return task_summary(request, task)


def move_task(request, user, task, status):
    task = _task(user, task)
    services.move_task(task, _status(task.project, status), user)
    return task_summary(request, task)


def add_label(request, user, task, label):
    task = _task(user, task)
    services.add_label(task, _label(task.project, label), user)
    return task_summary(request, task)


def remove_label(request, user, task, label):
    task = _task(user, task)
    services.remove_label(task, _label(task.project, label), user)
    return task_summary(request, task)


def create_label(request, user, project, name, color=None):
    project = _project(user, project)
    label = services.create_label(project, user, name, color or Label._meta.get_field('color').default)
    return {'project': project.key, 'name': label.name, 'color': label.color}


def add_comment(request, user, task, text):
    task = _task(user, task)
    if not text.strip():
        raise ToolError('The comment is empty.')
    services.add_comment(task, text, user)
    return {'task': task.identifier, 'commented': True, 'url': _url(request, task)}


def add_subtask(request, user, task, title):
    task = _task(user, task)
    if not services.can_add_subtask(user, task):
        raise PermissionDenied("You can't add subtasks to this task")
    title = title.strip()
    if not title:
        raise ToolError('The subtask needs a title.')
    subtask = services.create_subtask(task, title, user)
    return {'task': task.identifier, 'subtask': {'id': subtask.pk, 'title': subtask.title, 'done': False}}


def complete_subtask(request, user, task, subtask_id, done=True):
    task = _task(user, task)
    subtask = Subtask.objects.filter(task=task, pk=subtask_id).first()
    if subtask is None:
        raise ToolError(f'{task.identifier} has no subtask {subtask_id}. get_task lists them.')
    if subtask.completed != done:
        services.toggle_subtask(subtask, user)
    return {'task': task.identifier, 'subtask': {'id': subtask.pk, 'title': subtask.title, 'done': done}}


# --- Time tools ------------------------------------------------------------------


def start_timer(request, user, task):
    task = _task(user, task)
    return {'running': _entry(request, services.start_timer(task, user))}


def stop_timer(request, user):
    entry = services.stop_timer(user)
    if entry is None:
        return {'stopped': None, 'message': 'No timer was running.'}
    return {'stopped': _entry(request, entry)}


def log_time(request, user, task, duration, day=None, note=''):
    task = _task(user, task)
    try:
        minutes = parse_duration(duration)
    except ValueError as error:
        raise ToolError(str(error)) from None
    entry = services.log_duration(task, user, minutes, day or timezone.localdate(), note or '')
    return {'logged': {
        'task': task.identifier, 'duration': format_minutes(minutes),
        'day': timezone.localtime(entry.started_at).date().isoformat(), 'note': entry.note,
    }}


def start_work(request, user, task):
    task = _task(user, task)
    entry = services.start_work(task, user)
    task.refresh_from_db()
    return {'task': task_summary(request, task), 'running': _entry(request, entry)}


def finish_work(request, user, task):
    task = _task(user, task)
    entry = services.finish_work(task, user)
    task.refresh_from_db()
    return {'task': task_summary(request, task), 'stopped': _entry(request, entry)}


# --- Registry --------------------------------------------------------------------

TASK = Param('string', 'Task id, like CUST-12.', required=True)
PROJECT = Param('string', 'Project key, like CUST (list_projects shows them).', required=True)
PRIORITIES = tuple(value for value, _label in Task.PRIORITY_CHOICES)

_FIELDS = {
    'description': Param('string', 'Markdown text.', nullable=True),
    'assignee': Param('string', '"me", or the email or name of someone on the project.', nullable=True),
    'priority': Param('string', 'Priority.', nullable=True, enum=PRIORITIES),
    'start_date': Param('date', 'YYYY-MM-DD.', nullable=True),
    'due_date': Param('date', 'YYYY-MM-DD.', nullable=True),
    'estimate': Param('string', 'Estimated time, like "1h 30m" or "2h".', nullable=True),
    'billable': Param('boolean', 'Whether time on the task is billable to the client.'),
}

TOOLS = [
    Tool(
        'list_projects', 'List projects',
        'Projects whose tasks you can see, with the key used in task ids (CUST in CUST-12). '
        'Finished and cancelled projects are left out unless include_closed is true.',
        (READ,), list_projects, read_only=True,
        params={'include_closed': Param('boolean', 'Also list finished and cancelled projects.')},
    ),
    Tool(
        'get_project', 'Project statuses, labels and people',
        "A project's statuses (board columns, in order), labels, and the people who can be assigned its tasks.",
        (READ,), get_project, read_only=True, params={'project': PROJECT},
    ),
    Tool(
        'search_tasks', 'Search tasks',
        'Find tasks you can see, most recently updated first. Open tasks only unless include_closed '
        'is true or a status is given.',
        (READ,), search_tasks, read_only=True,
        params={
            'text': Param('string', 'Words in the title or description, or a task number.'),
            'project': Param('string', 'Project key.'),
            'assignee': Param('string', '"me", "nobody", or an email or name.'),
            'status': Param('string', 'Status name, like "In Progress".'),
            'label': Param('string', 'Label name.'),
            'include_closed': Param('boolean', 'Include completed and canceled tasks.'),
            'overdue': Param('boolean', 'Only open tasks past their due date.'),
            'limit': Param('integer', f'At most this many tasks (default 25, max {SEARCH_LIMIT}).'),
        },
    ),
    Tool(
        'get_task', 'Get a task',
        'Everything about one task: description, status, people, dates, labels, subtasks (with ids), '
        'time logged, whether your timer runs on it, and the latest comments.',
        (READ,), get_task, read_only=True, params={'task': TASK},
    ),
    Tool(
        'my_timer', 'My timer',
        'The timer you have running now, if any, and how much time you logged today.',
        (READ,), my_timer, read_only=True,
    ),
    Tool(
        'create_task', 'Create a task',
        'Create a task on a project. Without a status it goes in the first board column. '
        'Labels must already exist on the project (create_label adds one).',
        (WRITE,), create_task,
        params={
            'project': PROJECT,
            'title': Param('string', 'Title.', required=True),
            'status': Param('string', 'Status name (get_project lists them).'),
            'labels': Param('string[]', 'Label names.'),
            **_FIELDS,
        },
    ),
    Tool(
        'update_task', 'Update a task',
        'Change fields of a task; only the fields you pass change. null clears a field. '
        'Use move_task for the status and add_label / remove_label for labels.',
        (WRITE,), update_task,
        params={'task': TASK, 'title': Param('string', 'New title.'), **_FIELDS},
    ),
    Tool(
        'move_task', 'Move a task to a status',
        'Move a task to another status (board column) of its project, at the bottom of that column.',
        (WRITE,), move_task, idempotent=True,
        params={'task': TASK, 'status': Param('string', 'Status name, like "Done".', required=True)},
    ),
    Tool(
        'add_label', 'Add a label to a task', 'Put an existing label of the project on a task. Nothing changes if it is already there.',
        (WRITE,), add_label, idempotent=True,
        params={'task': TASK, 'label': Param('string', 'Label name.', required=True)},
    ),
    Tool(
        'remove_label', 'Remove a label from a task', 'Take a label off a task. Nothing changes if it is not there.',
        (WRITE,), remove_label, idempotent=True,
        params={'task': TASK, 'label': Param('string', 'Label name.', required=True)},
    ),
    Tool(
        'create_label', 'Create a label',
        'Add a label to a project (needs the right to edit the project, as in project settings).',
        (WRITE,), create_label,
        params={
            'project': PROJECT,
            'name': Param('string', 'Label name, at most 50 characters.', required=True),
            'color': Param('string', 'Hex color like #ef4444 (default indigo).'),
        },
    ),
    Tool(
        'add_comment', 'Comment on a task',
        'Add a comment (Markdown) to a task, shown under the signed-in person\'s name. Write it as '
        'they would, in the first person, for their colleagues: a result, a blocker or a decision. '
        'Not for changes you can make to the task itself, progress notes or retelling the chat.',
        (WRITE,), add_comment,
        params={'task': TASK, 'text': Param('string', 'The comment.', required=True)},
    ),
    Tool(
        'add_subtask', 'Add a subtask', 'Add a subtask at the end of a task\'s checklist.',
        (WRITE,), add_subtask,
        params={'task': TASK, 'title': Param('string', 'Subtask title.', required=True)},
    ),
    Tool(
        'complete_subtask', 'Tick a subtask', 'Mark a subtask done (or not done with done=false). get_task gives the ids.',
        (WRITE,), complete_subtask, idempotent=True,
        params={
            'task': TASK,
            'subtask_id': Param('integer', 'Subtask id from get_task.', required=True),
            'done': Param('boolean', 'Done (default true) or not done.'),
        },
    ),
    Tool(
        'start_timer', 'Start my timer', 'Start your timer on a task. A timer running on another task stops first.',
        (TIME,), start_timer, params={'task': TASK},
    ),
    Tool(
        'stop_timer', 'Stop my timer', 'Stop your running timer, wherever it runs.',
        (TIME,), stop_timer,
    ),
    Tool(
        'log_time', 'Log time', 'Log time you already worked on a task, as a duration on a day.',
        (TIME,), log_time,
        params={
            'task': TASK,
            'duration': Param('string', 'Like "1h 30m", "45m" or "1.5h".', required=True),
            'day': Param('date', 'Day worked, YYYY-MM-DD (default today).'),
            'note': Param('string', 'What you did.'),
        },
    ),
    Tool(
        'start_work', 'Start working on a task',
        'Begin work on a task in one step: assign it to you if nobody has it, move it to the '
        "project's first in-progress status, and start your timer.",
        (WRITE, TIME), start_work, params={'task': TASK},
    ),
    Tool(
        'finish_work', 'Finish a task',
        "Stop your timer on the task (if it runs there) and move the task to the project's first completed status.",
        (WRITE, TIME), finish_work, params={'task': TASK},
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tools_for(scopes):
    """The tools a token with ``scopes`` may call."""
    return [tool for tool in TOOLS if set(tool.scopes) <= set(scopes)]


def call(tool, request, user, arguments):
    """Run ``tool``. Returns the result dict, or raises ToolError with a message for Claude."""
    cleaned = tool.clean(arguments or {})
    try:
        return tool.handler(request, user, **cleaned)
    except PermissionDenied as error:
        raise ToolError(str(error) or 'You are not allowed to do that.') from None
    except (services.TaskValidationError, services.TimeEntryValidationError) as error:
        raise ToolError(str(error)) from None
