from django.conf import settings
from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.clients.models import Client

from .keys import KEY_MAX_LENGTH, KEY_REGEX, derive_key

KEY_DERIVE_ATTEMPTS = 3


class Project(models.Model):
    ACTIVE = 'active'
    ON_HOLD = 'on_hold'
    FINISHED = 'finished'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (ON_HOLD, 'On hold'),
        (FINISHED, 'Finished'),
        (CANCELLED, 'Cancelled'),
    ]
    # Open projects show on the projects page by default; closed ones behind a toggle.
    OPEN_STATUSES = (ACTIVE, ON_HOLD)

    HOURLY = 'hourly'
    FIXED = 'fixed'
    BILLING_CHOICES = [
        (HOURLY, 'Hourly'),
        (FIXED, 'Fixed price'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    github_repo_url = models.URLField(blank=True)
    github_sync_enabled = models.BooleanField(default=False)
    # db_default too, so rows written without the field (raw SQL, older code) are Active.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE, db_default=ACTIVE)
    # The prefix of every task id on this project ("CUST" in CUST-12). Derived
    # from the name when the project is created and never changed by a rename.
    key = models.CharField(
        max_length=KEY_MAX_LENGTH,
        unique=True,
        blank=True,
        validators=[RegexValidator(
            KEY_REGEX,
            '2 to 6 capital letters or digits, starting with a letter.',
        )],
    )
    # The last task number handed out. Only Task.save() moves it, with an
    # atomic increment; see ``save`` for why a full project save leaves it alone.
    task_counter = models.PositiveIntegerField(default=0, editable=False)
    # What an hour of billable time is worth, in the client's currency. Blank: no
    # amounts on the time page, only hours.
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Hourly: billable time is valued at ``hourly_rate``. Fixed price: the client pays
    # ``fixed_price`` whatever the hours, so time is shown in hours only.
    billing_type = models.CharField(
        max_length=10, choices=BILLING_CHOICES, default=HOURLY, db_default=HOURLY
    )
    fixed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.client.name})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        derived = not self.key
        if not self._state.adding and kwargs.get('update_fields') is None:
            # A project loaded before a task was created holds a stale counter;
            # writing it back would hand out the same task numbers again.
            kwargs['update_fields'] = [
                field.name for field in self._meta.concrete_fields
                if not field.primary_key and field.name != 'task_counter'
            ]
        if not derived:
            super().save(*args, **kwargs)
        else:
            self._save_with_derived_key(*args, **kwargs)
        if is_new:
            self._create_default_statuses()

    def _save_with_derived_key(self, *args, **kwargs):
        """Save under a key derived from the name.

        Two projects created at the same moment can derive the same key from the
        same snapshot of taken keys; the one that loses the unique constraint
        derives again from what is taken now.
        """
        def taken_keys():
            return set(Project.objects.exclude(pk=self.pk).values_list('key', flat=True))

        taken = taken_keys()
        for attempt in range(KEY_DERIVE_ATTEMPTS):
            self.key = derive_key(self.name, taken, pk=self.pk)
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                taken = taken_keys()
                if attempt == KEY_DERIVE_ATTEMPTS - 1 or self.key not in taken:
                    # Out of tries, or the failure was about something other than the key.
                    raise

    def _create_default_statuses(self):
        defaults = [
            ('Backlog', Status.BACKLOG),
            ('To Do', Status.UNSTARTED),
            ('In Progress', Status.STARTED),
            ('Review', Status.STARTED),
            ('Done', Status.COMPLETED),
        ]
        for i, (name, category) in enumerate(defaults):
            Status.objects.create(project=self, name=name, order=i, category=category)

    @property
    def github_link(self):
        """The repository address when it is safe to render as a link, else ''.

        Older rows were saved without validation, so a value that is not a web
        address is shown as text, never as an ``href``.
        """
        url = self.github_repo_url or ''
        return url if url.lower().startswith(('https://', 'http://')) else ''

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def billing_rate(self):
        """The rate billable time is valued at, or ``None`` (fixed price, or no rate)."""
        return self.hourly_rate if self.billing_type == self.HOURLY else None

    @property
    def is_overdue(self):
        """An open project past its deadline."""
        return bool(self.deadline) and self.is_open and self.deadline < timezone.localdate()

    @property
    def task_count(self):
        """Return total number of tasks across all statuses."""
        from apps.tasks.models import Task
        return Task.objects.filter(project=self).count()


def project_delete_blocker(project):
    """Why ``project`` cannot be deleted, or ''.

    Logged time and invoice lines are what a client is billed on, so a project
    holding either is marked finished or cancelled instead.
    """
    from apps.tasks.models import TimeEntry

    if TimeEntry.objects.filter(task__project=project).exists():
        return 'This project has logged time. Set its status to Finished or Cancelled instead.'
    if project.invoice_lines.exists():
        return 'This project is on an invoice. Set its status to Finished or Cancelled instead.'
    return ''


class Status(models.Model):
    BACKLOG = 'backlog'
    UNSTARTED = 'unstarted'
    STARTED = 'started'
    COMPLETED = 'completed'
    CANCELED = 'canceled'
    CATEGORY_CHOICES = [
        (BACKLOG, 'Backlog'),
        (UNSTARTED, 'Unstarted'),
        (STARTED, 'Started'),
        (COMPLETED, 'Completed'),
        (CANCELED, 'Canceled'),
    ]
    CLOSED_CATEGORIES = (COMPLETED, CANCELED)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    visible_on_board = models.BooleanField(default=True)
    # What a column means, whatever it is called: renaming "Done" cannot break
    # the done/active/overdue counts, and the icon follows the category.
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=UNSTARTED)

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Statuses'
        constraints = [
            models.UniqueConstraint(fields=['project', 'name'], name='unique_status_name_per_project'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        adding = self._state.adding
        super().save(*args, **kwargs)
        if not adding and (update_fields is None or 'category' in update_fields):
            self._sync_tasks_closed_at()

    def _sync_tasks_closed_at(self):
        """The rule Task.save applies to one task, for every task in this status.

        Changing a status's type closes or reopens the work in it. ``update()``
        leaves ``updated_at`` alone. Here, not in the settings view, so the admin
        (and anything else that saves a Status) keeps ``closed_at`` right too.
        """
        if self.is_closed:
            self.tasks.filter(closed_at__isnull=True).update(closed_at=timezone.now())
        else:
            self.tasks.filter(closed_at__isnull=False).update(closed_at=None)

    @property
    def is_completed(self):
        return self.category == self.COMPLETED

    @property
    def is_closed(self):
        """Completed or canceled: work here needs no more attention."""
        return self.category in self.CLOSED_CATEGORIES

    @property
    def task_count(self):
        return self.tasks.count()


class ProjectAccess(models.Model):
    """One row means this person has access to that project.

    The row opens the project. Seeing tasks on it also needs ``access_tasks``.
    Creating and editing tasks need their own flags. The row does not grant
    settings edits. Admins bypass the row through ``is_admin`` and
    ``has_app_permission``.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='access')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_access'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'user']
        ordering = ['project', 'user__name']

    def __str__(self):
        return f"{self.user.name} - {self.project.name}"


class ProjectTaskView(models.Model):
    """The Tasks page setup one person last used on one project.

    ``params`` is the canonical query string of a
    :class:`~apps.tasks.viewspec.TaskViewSpec` as a dict, without search text or
    paging. It is revalidated every time it is restored, so deleting a status or
    a label cannot leave a view pointing at something that is gone. Unique per
    person and project; it changes nothing for anyone else.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_task_views',
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='task_views'
    )
    params = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'project'],
                name='unique_task_view_per_user_project',
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.project.name}"


def _has_access_row(user, project):
    return ProjectAccess.objects.filter(project=project, user=user).exists()


def visible_projects(user):
    """Projects this user may see on the dashboard and in the project list.

    ``projects_view_all`` or ``projects_edit_all`` is every project, the same
    rule as :func:`can_access_project`. Without them, projects where ``user``
    has a ProjectAccess row. ``role=admin`` bypasses the flags through
    ``User.has_app_permission``.
    """
    if user.has_app_permission('projects_view_all') or user.has_app_permission('projects_edit_all'):
        return Project.objects.all()
    return Project.objects.filter(access__user=user).distinct()


def can_access_project(user, project):
    """Whether the user may open this project.

    Admin, a ProjectAccess row, ``projects_view_all``, or ``projects_edit_all``.
    """
    if user.is_admin:
        return True
    if _has_access_row(user, project):
        return True
    return user.has_app_permission('projects_view_all') or user.has_app_permission(
        'projects_edit_all'
    )


def can_edit_project(user, project):
    """Settings, statuses, labels, and the GitHub repo settings.

    Admin, ``projects_edit_all``, or ``projects_edit_own`` plus a ProjectAccess row.
    A row by itself does not grant edit.
    """
    if user.is_admin:
        return True
    if user.has_app_permission('projects_edit_all'):
        return True
    return user.has_app_permission('projects_edit_own') and _has_access_row(user, project)


def can_work_on_project(user, project):
    """Admin, or a ProjectAccess row.

    Task view, create, and edit use the task flags. Notes use ``access_notes``
    and :func:`can_access_project` instead. Project view-all and the project
    edit flags do not grant this.
    """
    if user.is_admin:
        return True
    return _has_access_row(user, project)


def get_assignable_users(project):
    """Users who can be assigned tasks on this project (access rows + admins)."""
    from apps.accounts.models import User

    access_ids = ProjectAccess.objects.filter(project=project).values_list('user_id', flat=True)
    return User.objects.filter(is_active=True).filter(
        models.Q(pk__in=access_ids) | models.Q(role='admin')
    )
