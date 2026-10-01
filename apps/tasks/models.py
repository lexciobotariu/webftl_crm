from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import Case, Count, Exists, F, OuterRef, Q, Value, When
from django.db.models.functions import Lower
from django.utils import timezone

from apps.projects.models import Project, ProjectAccess, Status

from .durations import format_minutes, format_seconds


class Label(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='labels')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6366f1')  # Hex color

    class Meta:
        unique_together = ['project', 'name']

    def __str__(self):
        return self.name


# Sentinel a priority filter uses for tasks with no priority (stored as '').
PRIORITY_NONE = 'none'
PRIORITY_FILTER_CHOICES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('urgent', 'Urgent'),
    (PRIORITY_NONE, 'No priority'),
]


def clean_priorities(values):
    """Keep only known priority filter values, once each, in display order."""
    wanted = {str(value) for value in values or []}
    return [value for value, _label in PRIORITY_FILTER_CHOICES if value in wanted]


def priorities_to_store(values):
    """What to save for a set of checked priorities: nothing when it is all of them."""
    cleaned = clean_priorities(values)
    return [] if len(cleaned) == len(PRIORITY_FILTER_CHOICES) else cleaned


def priority_filter_options(selected):
    """Checkbox options for a priority filter. An empty selection checks everything."""
    chosen = set(selected or [])
    return [
        {'value': value, 'label': label, 'checked': not chosen or value in chosen}
        for value, label in PRIORITY_FILTER_CHOICES
    ]


def _priority_rank():
    """0 for urgent down to 4 for no priority, so "most urgent first" is ascending."""
    return Case(
        When(priority='urgent', then=Value(0)),
        When(priority='high', then=Value(1)),
        When(priority='medium', then=Value(2)),
        When(priority='low', then=Value(3)),
        default=Value(4),
    )


def _category_rank():
    """Position of the status type in ``Status.CATEGORY_CHOICES``: backlog first."""
    return Case(
        *[
            When(status__category=value, then=Value(rank))
            for rank, (value, _label) in enumerate(Status.CATEGORY_CHOICES)
        ],
        default=Value(len(Status.CATEGORY_CHOICES)),
    )


def archive_cutoff(now=None):
    return (now or timezone.now()) - timedelta(days=settings.TASK_ARCHIVE_AFTER_DAYS)


class TaskQuerySet(models.QuerySet):
    """Keeps the definitions of "done", "active" and "overdue" in one place.

    ``Task.is_overdue`` is the per-instance version of :meth:`overdue`; the two
    must agree, so anything counting overdue tasks should go through here rather
    than re-deriving the filter.
    """

    def done(self):
        return self.filter(status__category=Status.COMPLETED)

    def active(self):
        """Tasks in a status that is not completed or canceled."""
        return self.exclude(status__category__in=Status.CLOSED_CATEGORIES)

    def archived(self, now=None):
        """Closed, and closed longer ago than ``TASK_ARCHIVE_AFTER_DAYS``."""
        return self.filter(
            status__category__in=Status.CLOSED_CATEGORIES, closed_at__lt=archive_cutoff(now)
        )

    def not_archived(self, now=None):
        # Spelled out rather than ``exclude(...)`` so a closed task with no
        # ``closed_at`` (nothing to measure from) is plainly kept.
        return self.filter(
            ~Q(status__category__in=Status.CLOSED_CATEGORIES)
            | Q(closed_at__isnull=True)
            | Q(closed_at__gte=archive_cutoff(now))
        )

    def overdue(self, today=None):
        if today is None:
            today = timezone.localdate()
        return self.active().filter(due_date__lt=today)

    def with_priorities(self, values):
        """Only tasks with one of ``values``; ``PRIORITY_NONE`` means no priority.

        An empty or unrecognised selection is no filter, so the list never goes
        blank because of a stale value.
        """
        values = clean_priorities(values)
        if not values:
            return self
        query = Q(priority__in=[value for value in values if value != PRIORITY_NONE])
        if PRIORITY_NONE in values:
            query |= Q(priority='')
        return self.filter(query)

    def matching(self, spec):
        """Tasks that pass every filter of a :class:`~apps.tasks.viewspec.TaskViewSpec`.

        Labels use ``Exists`` rather than ``labels__in`` plus ``distinct()``, so a
        task with two matching labels is still one row and the query stays cheap.
        """
        qs = self
        if not spec.archived:
            qs = qs.not_archived()
        if spec.categories:
            qs = qs.filter(status__category__in=spec.categories)
        if spec.hidden_statuses:
            qs = qs.exclude(status_id__in=spec.hidden_statuses)
        qs = qs.with_priorities(spec.priorities)
        if spec.assignees:
            query = Q(assignee_id__in=[int(v) for v in spec.assignees if v != 'none'])
            if 'none' in spec.assignees:
                query |= Q(assignee__isnull=True)
            qs = qs.filter(query)
        if spec.labels:
            qs = qs.filter(
                Exists(
                    Task.labels.through.objects.filter(
                        task_id=OuterRef('pk'), label_id__in=spec.labels
                    )
                )
            )
        if spec.q:
            qs = qs.filter(title__icontains=spec.q)
        return qs

    def ordered_for(self, spec):
        """Group key first, then the sort key, then ``pk`` so ties never reshuffle."""
        ordering = []
        if spec.group == 'status':
            ordering.append('status__order')
            ordering.append('status_id')
        elif spec.group == 'assignee':
            ordering.append(Lower('assignee__name').asc(nulls_last=True))
            ordering.append(F('assignee_id').asc(nulls_last=True))
        elif spec.group == 'priority':
            ordering.append(_priority_rank().asc())
        elif spec.group == 'project':
            ordering.append(Lower('project__name').asc())
            ordering.append('project_id')
        elif spec.group == 'category':
            ordering.append(_category_rank().asc())

        descending = spec.dir == 'desc'
        if spec.sort == 'priority':
            key = _priority_rank()
            ordering.append(key.desc() if descending else key.asc())
        elif spec.sort == 'due':
            key = F('due_date')
            ordering.append(key.desc(nulls_last=True) if descending else key.asc(nulls_last=True))
        elif spec.sort == 'title':
            key = Lower('title')
            ordering.append(key.desc() if descending else key.asc())
        else:
            field = 'created_at' if spec.sort == 'created' else 'updated_at'
            ordering.append(f'-{field}' if descending else field)
        ordering.append('pk')
        return self.order_by(*ordering)

    def group_counts(self, spec):
        """``{group key: matching tasks}`` for every group, in one query.

        The list only loads the first page of rows, so headers take their counts
        from here. The keys are ``status_id``, ``assignee_id`` (``None`` for
        unassigned), the priority string, ``project_id`` or the status type;
        ``group=none`` has no groups.
        """
        field = {
            'status': 'status_id',
            'assignee': 'assignee_id',
            'priority': 'priority',
            'project': 'project_id',
            'category': 'status__category',
        }.get(spec.group)
        if field is None:
            return {}
        rows = self.matching(spec).order_by().values(field).annotate(total=Count('pk'))
        return {row[field]: row['total'] for row in rows}

    def open_for(self, user):
        """Tasks assigned to ``user`` that they can still view.

        Same rule as :func:`visible_tasks`: admin, ``tasks_view_all``, or
        ``access_tasks`` plus a ProjectAccess row. Assigned tasks on a
        project they cannot view stay out.
        """
        return visible_tasks(user).filter(assignee=user)


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    # 12 in CUST-12: counts up per project from 1 and is never reused.
    number = models.PositiveIntegerField(editable=False)
    status = models.ForeignKey(Status, on_delete=models.RESTRICT, related_name='tasks')
    title = models.CharField(max_length=1000)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimate_minutes = models.PositiveIntegerField(null=True, blank=True, help_text='Estimated time, in minutes')
    labels = models.ManyToManyField(Label, blank=True, related_name='tasks')
    order = models.PositiveIntegerField(default=0)

    # GitHub integration
    github_issue_id = models.PositiveIntegerField(null=True, blank=True)
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # When the task entered a completed or canceled status; cleared when it is
    # reopened. Set by ``save``, so every path that changes the status keeps it.
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ['order', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'github_issue_id'],
                condition=Q(github_issue_id__isnull=False),
                name='unique_github_issue_per_project',
            ),
            models.UniqueConstraint(
                fields=['project', 'number'],
                name='unique_task_number_per_project',
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or 'status' in update_fields:
            self._sync_closed_at()
            if update_fields is not None:
                # Otherwise a save(update_fields=['status']) would drop it.
                kwargs['update_fields'] = {*update_fields, 'closed_at'}
        if self.number is not None:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            # The UPDATE locks the project row until this transaction commits, so
            # a concurrent create waits and then reads the next value.
            projects = Project.objects.filter(pk=self.project_id)
            projects.update(task_counter=F('task_counter') + 1)
            self.number = projects.values_list('task_counter', flat=True).get()
            super().save(*args, **kwargs)

    def _sync_closed_at(self):
        """A stateless rule: closed with no date gets now, open gets none."""
        if self.status_id is None:
            return
        if self.status.is_closed:
            if self.closed_at is None:
                self.closed_at = timezone.now()
        else:
            self.closed_at = None

    @property
    def is_archived(self):
        return (
            self.closed_at is not None
            and self.status.is_closed
            and self.closed_at < archive_cutoff()
        )

    @property
    def identifier(self):
        """``CUST-12``. Loads the project unless it is already on the instance."""
        return f'{self.project.key}-{self.number}'

    @property
    def estimate_label(self):
        return format_minutes(self.estimate_minutes)

    @property
    def is_overdue(self):
        if not self.due_date:
            return False
        if self.status.is_closed:
            return False
        return self.due_date < timezone.localdate()

    @property
    def subtask_progress(self):
        # The board annotates both counts so a column of cards costs no extra queries.
        total = getattr(self, 'subtask_total', None)
        if total is None:
            total = self.subtasks.count()
            completed = self.subtasks.filter(completed=True).count() if total else 0
        else:
            completed = self.subtask_done
        if total == 0:
            return None
        return f"{completed}/{total}"


def _on_project(user, project):
    return ProjectAccess.objects.filter(project=project, user=user).exists()


def can_view_tasks_on(user, project):
    """Whether this person may see tasks on ``project``.

    Admin, ``tasks_view_all``, or ``access_tasks`` plus a ProjectAccess row.
    Project view and project edit do not grant this.
    """
    if user.is_admin or user.has_app_permission('tasks_view_all'):
        return True
    return user.has_app_permission('access_tasks') and _on_project(user, project)


def can_view_task(user, task):
    """Whether this person may open ``task``."""
    return can_view_tasks_on(user, task.project)


def can_create_task(user, project):
    """New tasks and subtasks.

    Admin, or ``tasks_create`` plus a ProjectAccess row. View-all is not enough.
    """
    if user.is_admin:
        return True
    return user.has_app_permission('tasks_create') and _on_project(user, project)


def can_edit_tasks_on(user, project):
    """Title, description, status, assignee, priority, due date, estimate,
    labels, subtasks, comments, attachments, and the person's own time.

    Admin, ``tasks_edit_all``, or ``tasks_edit_own`` plus a ProjectAccess row.
    Project edit flags do not grant this.
    """
    if user.is_admin or user.has_app_permission('tasks_edit_all'):
        return True
    return user.has_app_permission('tasks_edit_own') and _on_project(user, project)


def can_edit_task(user, task):
    """Whether this person may change ``task``."""
    return can_edit_tasks_on(user, task.project)


def editable_scope(user):
    """Where ``user`` may edit tasks, for a list that spans projects.

    Returns ``(everywhere, project_ids)``: when ``everywhere`` is true the ids are
    unused. A list asks this once and checks each row against the answer, instead of
    calling :func:`can_edit_tasks_on` (one query) per row. At most one query.
    """
    if user.is_admin or user.has_app_permission('tasks_edit_all'):
        return True, frozenset()
    if not user.has_app_permission('tasks_edit_own'):
        return False, frozenset()
    if not user.has_app_permission('tasks_view_all'):
        # Without view-all every task the person can see is on a project they have
        # an access row for, which is exactly what edit-own needs.
        return True, frozenset()
    ids = ProjectAccess.objects.filter(user=user).values_list('project_id', flat=True)
    return False, frozenset(ids)


def visible_tasks(user, project=None):
    """Tasks ``user`` may see.

    ``tasks_view_all`` is every task. Without it, tasks on projects where
    ``user`` has a ProjectAccess row, and only when ``access_tasks`` is on.
    ``role=admin`` bypasses the flags through ``User.has_app_permission``
    and the admin check.
    """
    qs = Task.objects.all()
    if project is not None:
        qs = qs.filter(project=project)
    if user.is_admin or user.has_app_permission('tasks_view_all'):
        return qs
    if user.has_app_permission('access_tasks'):
        return qs.filter(project__access__user=user)
    return qs.none()


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=255)
    completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


class TaskActivity(models.Model):
    """Tracks activity on tasks - comments, status changes, etc."""
    ACTIVITY_TYPES = [
        ('comment', 'Comment'),
        ('status_change', 'Status Changed'),
        ('assignee_change', 'Assignee Changed'),
        ('priority_change', 'Priority Changed'),
        ('created', 'Created'),
        ('due_date_change', 'Due Date Changed'),
        ('label_added', 'Label Added'),
        ('label_removed', 'Label Removed'),
        ('title_change', 'Title Changed'),
        ('description_change', 'Description Changed'),
        ('estimate_change', 'Estimate Changed'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    content = models.TextField(blank=True)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the author (or an admin) changes a comment's text.
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Task activities'

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.task}"


class TimeEntry(models.Model):
    """Logged time on a task.

    ``ended_at`` is null while a timer is running. Duration is
    ``ended_at - started_at`` and is not stored. A person has at most one
    open row; a manual entry may run longer than the 12-hour timer cap.
    """

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_entries')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='time_entries',
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    # When the entry was logged, which is where it sits in the activity timeline;
    # ``started_at`` is the day the work was done on.
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'started_at']),
            models.Index(fields=['task']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(ended_at__isnull=True),
                name='unique_open_timer_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.user} on {self.task} at {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def duration(self):
        if self.ended_at is None:
            return None
        return self.ended_at - self.started_at

    @property
    def duration_label(self):
        if self.duration is None:
            return 'Running'
        return format_seconds(self.duration.total_seconds())


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if not self.filename:
            self.filename = self.file.name
        super().save(*args, **kwargs)


class MyTasksView(models.Model):
    """The My Tasks setup one person last used.

    ``params`` is the canonical query string of a
    :class:`~apps.tasks.viewspec.TaskViewSpec` as a dict, without search text or
    paging, and is revalidated every time it is restored. It lives apart from
    ``ProjectTaskView`` because it belongs to no project.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='my_tasks_view',
    )
    params = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"My Tasks view - {self.user}"
