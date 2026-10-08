import json
import re
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.db.models.deletion import RestrictedError
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.models import User
from apps.clients.models import Client, visible_clients
from apps.tasks.listview import (
    apply_url_headers,
    archived_matching,
    build_groups,
    filter_options,
    group_choices,
    group_slots,
    project_assignees,
    render_task_row,
    resolve_view,
)
from apps.tasks.models import (
    Label,
    Task,
    TaskActivity,
    can_create_task,
    can_edit_tasks_on,
    visible_tasks,
)
from apps.tasks.viewspec import LIMIT_STEP, TaskViewOptions, column_choices, sort_choices

from .forms import LabelForm, ProjectForm, StatusForm
from .keys import KEY_REGEX
from .models import (
    Project,
    ProjectAccess,
    ProjectTaskView,
    Status,
    can_access_project,
    can_edit_project,
    visible_projects,
)

PROJECTS_PER_PAGE = 20


def _status_item_context(project, status):
    return {'status': status, 'project': project, 'category_choices': Status.CATEGORY_CHOICES}


def _can_join_project(user):
    """Active people who can open the projects module.

    Admins qualify without a preset because ``has_app_permission`` bypasses it.
    """
    return user.is_active and user.has_app_permission('access_projects')


def _addable_users(project):
    """Active users with the projects module who are not already on the project."""
    on_project = ProjectAccess.objects.filter(project=project).values('user_id')
    return (
        User.objects.filter(is_active=True)
        .filter(Q(role='admin') | Q(permission_preset__access_projects=True))
        .exclude(pk__in=on_project)
        .order_by('name', 'email')
    )


@login_required
@require_permission('access_projects')
def project_list(request):
    projects_qs = visible_projects(request.user).select_related('client').order_by('name')
    clients = Client.objects.none()
    client_filter = None
    if request.user.has_app_permission('access_clients'):
        client_filter = request.GET.get('client')
        if client_filter:
            projects_qs = projects_qs.filter(client_id=client_filter)
        clients = visible_clients(request.user).order_by('name')

    paginator = Paginator(projects_qs, PROJECTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'projects/project_list.html', {
        'projects': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'clients': clients,
        'client_filter': client_filter,
    })


@login_required
@require_permission('access_projects')
def project_create(request):
    if not request.user.has_app_permission('projects_create'):
        return HttpResponseForbidden("You can't create projects")

    initial = {}
    if request.GET.get('client'):
        initial['client'] = request.GET.get('client')

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            ProjectAccess.objects.create(project=project, user=request.user)
            return redirect('project_tasks', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)
    return render(request, 'projects/project_form.html', {'form': form})


@login_required
@require_permission('access_projects')
def project_detail(request, pk):
    """Project detail page with overview, tasks, notes, and team tabs."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")

    # Calculate stats. "Done" is whatever the project files under the completed status type,
    # so renaming a column cannot break these numbers. These counts stay on every
    # visible task; the Tasks page has its own filters and never changes them.
    tasks = visible_tasks(request.user, project).select_related('status', 'assignee')
    total_tasks = tasks.count()
    completed_tasks = tasks.done().count()
    active_tasks = tasks.active().count()
    overdue_tasks = tasks.overdue().count()

    # Recent activity (last 5 across tasks this person can view)
    recent_activities = TaskActivity.objects.filter(
        task__in=visible_tasks(request.user, project)
    ).select_related('user', 'task').order_by('-created_at')[:5]

    # Determine active tab based on URL
    url_name = request.resolver_match.url_name
    tab_mapping = {
        'project_detail_notes': 'notes',
        'project_detail_team': 'team',
    }
    active_tab = tab_mapping.get(url_name, 'overview')
    editable = can_edit_project(request.user, project)

    access_rows = []
    addable_users = []
    if active_tab == 'team':
        access_rows = project.access.select_related('user').order_by('user__name', 'user__email')
        if editable:
            addable_users = _addable_users(project)

    return render(request, 'projects/project_detail.html', {
        'project': project,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'active_tasks': active_tasks,
        'overdue_tasks': overdue_tasks,
        'recent_activities': recent_activities,
        'active_tab': active_tab,
        'can_edit_project': editable,
        'can_create_task': can_create_task(request.user, project),
        'access_rows': access_rows,
        'addable_users': addable_users,
    })


@login_required
@require_permission('access_projects')
def project_tasks(request, pk):
    """The project's Tasks page: one URL-driven view of its tasks."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")

    statuses = list(project.statuses.all())
    labels = list(project.labels.all())
    assignees = list(project_assignees(project))
    options = TaskViewOptions(
        status_ids=frozenset(status.pk for status in statuses),
        assignee_ids=frozenset(user.pk for user in assignees),
        label_ids=frozenset(label.pk for label in labels),
    )
    page_url = request.path

    resolved = resolve_view(
        request,
        options=options,
        model=ProjectTaskView,
        lookup={'user': request.user, 'project': project},
        page_url=page_url,
    )
    if isinstance(resolved, HttpResponseRedirect):
        return resolved
    spec, from_toolbar = resolved

    visible = visible_tasks(request.user, project)
    matching = visible.matching(spec)
    if 'row' in request.GET:
        return render_task_row(request, request.GET['row'], matching, spec, {
            'project': project,
            'quick_edit': can_edit_tasks_on(request.user, project),
        })
    total_matching = matching.count()
    archived = archived_matching(visible, spec)
    archived_count = archived.count()
    # "Hidden by filters" leaves archived tasks out: they have their own count.
    pool = visible if spec.archived else visible.not_archived()
    total_visible = pool.count() if (spec.has_filters or spec.q) else total_matching

    context = {
        'project': project,
        'spec': spec,
        'groups': [],
        'total_matching': total_matching,
        'total_visible': total_visible,
        'hidden_count': total_visible - total_matching,
        'archived_count': archived_count,
        'more_url': None,
        'page_url': page_url,
        'can_edit_project': can_edit_project(request.user, project),
        'can_create_task': can_create_task(request.user, project),
        # Asked once for the page; rows and cards only read it.
        'quick_edit': can_edit_tasks_on(request.user, project),
        'priority_choices': Task.PRIORITY_CHOICES,
        'sort_choices': sort_choices(options),
        'column_choices': column_choices(spec),
        'group_choices': group_choices(options),
        **filter_options(statuses, spec, assignees, labels),
    }
    if spec.layout == 'board':
        context.update(_board_context(project, spec, matching, archived))
    else:
        page = (
            matching.ordered_for(spec)
            .select_related('project', 'status', 'assignee')
            .prefetch_related('labels')[: spec.limit]
        )
        context['groups'] = build_groups(
            page, spec, visible.group_counts(spec), group_slots(spec, statuses, assignees)
        )
        if total_matching > spec.limit:
            more = spec.replace(limit=spec.limit + LIMIT_STEP).to_query_string()
            context['more_url'] = f'{page_url}?{more}'

    response = render(request, 'tasks/view/project_tasks.html', context)
    return apply_url_headers(response, request, spec, from_toolbar, page_url)


@login_required
@require_permission('access_projects')
@require_POST
def project_team_add(request, pk):
    """Add a ProjectAccess row. Same person twice is already on the project."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    raw_id = (request.POST.get('user') or '').strip()
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        return HttpResponse('That person cannot be added to this project', status=400)

    target = User.objects.filter(pk=user_id).first()
    if target is None or not _can_join_project(target):
        return HttpResponse('That person cannot be added to this project', status=400)

    try:
        with transaction.atomic():
            ProjectAccess.objects.create(project=project, user=target)
    except IntegrityError:
        # unique_together: a second add is already on the project.
        pass
    return redirect('project_detail_team', pk=project.pk)


@login_required
@require_permission('access_projects')
@require_POST
def project_team_remove(request, pk, user_pk):
    """Delete one ProjectAccess row, including your own and the last one."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    access = get_object_or_404(ProjectAccess, project=project, user_id=user_pk)
    # Instance delete so the post_delete signal in signals.py still runs.
    access.delete()
    return redirect('project_detail_team', pk=project.pk)


def _board_context(project, spec, matching, archived):
    """Columns and cards for the board layout.

    Columns are the statuses shown on the board, minus any the filter hides.
    Cards are the tasks that pass the filters, always in their manual order: grouping
    and sorting belong to the list. Every card is loaded; there is no paging here.
    """
    cards = (
        matching.select_related('assignee')
        .prefetch_related('labels')
        .annotate(
            subtask_total=Count('subtasks', distinct=True),
            subtask_done=Count('subtasks', filter=Q(subtasks__completed=True), distinct=True),
        )
        .order_by('order', '-created_at')
    )
    columns = (
        project.statuses.filter(visible_on_board=True)
        .exclude(pk__in=spec.hidden_statuses)
        .annotate(
            board_task_count=Count('tasks', filter=Q(tasks__in=matching), distinct=True),
            # So a column holding only archived tasks can say so.
            archived_task_count=Count('tasks', filter=Q(tasks__in=archived), distinct=True),
        )
        # Meta.ordering is ignored once a query aggregates, so say it.
        .order_by('order', 'pk')
        .prefetch_related(Prefetch('tasks', queryset=cards))
    )
    return {
        'visible_statuses': columns,
        'hidden_task_count': matching.filter(status__visible_on_board=False).count(),
    }


@login_required
def project_board(request, pk):
    """The board used to be its own page; it is a layout of the Tasks page now."""
    return redirect(f"{reverse('project_tasks', args=[pk])}?layout=board")


@login_required
@require_permission('access_projects')
def project_edit(request, pk):
    """Redirect to settings page - edit functionality has been consolidated."""
    return redirect('project_settings', pk=pk)


@login_required
@require_permission('access_projects')
@require_POST
def project_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    project = get_object_or_404(Project, pk=pk)
    project.delete()
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = '/projects/'
        return response
    return redirect('project_list')


@login_required
@require_permission('access_projects')
@require_POST
@transaction.atomic
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    try:
        data = json.loads(request.body)
        order = data.get('order', [])
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    if not isinstance(order, list):
        return HttpResponse('order must be a list', status=400)

    for i, status_id in enumerate(order):
        Status.objects.filter(pk=status_id, project=project).update(order=i)
    return HttpResponse(status=204)


@login_required
@require_permission('access_projects')
def project_settings(request, pk):
    """Unified project settings page with statuses and labels."""
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    # Determine back URL based on 'next' parameter
    next_page = request.GET.get('next')
    back_url = 'project_detail' if next_page == 'detail' else 'project_tasks'

    status_form = StatusForm()
    label_form = LabelForm()
    return render(request, 'projects/project_settings.html', {
        'project': project,
        'status_form': status_form,
        'category_choices': Status.CATEGORY_CHOICES,
        'label_form': label_form,
        'back_url': back_url,
        'can_edit_project': can_edit_project(request.user, project),
    })


def parse_hourly_rate(text):
    """Return ``(rate, error)`` for a typed hourly rate; empty means no rate."""
    text = text.strip().replace(',', '.')
    if not text:
        return None, None
    try:
        rate = Decimal(text)
    except InvalidOperation:
        return None, 'Enter a number such as 50 or 49.50.'
    if not rate.is_finite() or rate < 0 or rate >= Decimal('100000000') or rate != rate.quantize(Decimal('0.01')):
        return None, 'Enter a positive amount with at most 2 decimals.'
    return rate, None


@login_required
@require_permission('access_projects')
@require_POST
def project_settings_update(request, pk):
    """Handle General settings form submission via HTMX."""
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    github_repo_url = request.POST.get('github_repo_url', '').strip()
    # A form without the field keeps the key; an empty field is an error.
    key = request.POST.get('key', project.key).strip().upper()
    # A form without the field keeps the rate; an empty field clears it.
    rate_text = request.POST.get('hourly_rate')
    hourly_rate, rate_error = project.hourly_rate, None
    if rate_text is not None:
        hourly_rate, rate_error = parse_hourly_rate(rate_text)
        if rate_error:
            hourly_rate = rate_text.strip()  # shown back in the form, never saved

    # The form re-renders from ``project``, so an error keeps what was typed.
    project.name = name
    project.description = description
    project.github_repo_url = github_repo_url
    project.key = key
    project.hourly_rate = hourly_rate

    errors = {}
    if rate_error:
        errors['hourly_rate'] = rate_error
    if not name:
        errors['name'] = 'Name is required.'
    if not re.fullmatch(KEY_REGEX, key, flags=re.ASCII):
        errors['key'] = '2 to 6 capital letters or digits, starting with a letter.'
    elif Project.objects.filter(key=key).exclude(pk=project.pk).exists():
        errors['key'] = 'This key is already used by another project.'

    if not errors:
        try:
            with transaction.atomic():
                project.save(update_fields=[
                    'name', 'description', 'github_repo_url', 'key', 'hourly_rate', 'updated_at',
                ])
        except IntegrityError:
            # Another project took the key between the check and the save.
            errors['key'] = 'This key is already used by another project.'

    if errors:
        return render(request, 'projects/partials/settings_general_form.html', {
            'project': project,
            'errors': errors,
        })

    return render(request, 'projects/partials/settings_general_form.html', {
        'project': project,
        'success': True,
    })


@login_required
@require_permission('access_projects')
@require_POST
def label_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    form = LabelForm(request.POST)
    if form.is_valid():
        label = form.save(commit=False)
        label.project = project
        label.save()
        return render(request, 'projects/partials/label_item.html', {'label': label, 'project': project})
    return HttpResponse(status=400)


@login_required
@require_permission('access_projects')
@require_POST
def label_delete(request, pk, label_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    label = get_object_or_404(Label, pk=label_pk, project=project)
    label.delete()
    return HttpResponse('')


@login_required
@require_permission('access_projects')
@require_POST
@transaction.atomic
def status_create(request, pk):
    project = get_object_or_404(Project.objects.select_for_update(), pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    form = StatusForm(request.POST)
    if form.is_valid():
        status = form.save(commit=False)
        status.project = project
        # Use Max to safely get the next order value
        max_order = project.statuses.aggregate(Max('order'))['order__max']
        status.order = max_order + 1 if max_order is not None else 0
        try:
            with transaction.atomic():
                status.save()
        except IntegrityError:
            form.add_error('name', 'A status with this name already exists for this project.')
        else:
            response = render(
                request,
                'projects/partials/status_create_success.html',
                _status_item_context(project, status),
            )
            response['HX-Trigger'] = 'statusCreated'
            return response
    return render(
        request,
        'projects/partials/status_form_errors.html',
        {'form': form, 'project': project},
        status=200,
    )


@login_required
@require_permission('access_projects')
@require_POST
def status_delete(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    status = get_object_or_404(Status, pk=status_pk, project=project)

    # Prevent deleting status with tasks
    if status.task_count > 0:
        return HttpResponse('Cannot delete status with tasks', status=400)

    # TOCTOU backstop: a task may have been moved into this status since the check above.
    try:
        status.delete()
    except RestrictedError:
        return HttpResponse('Cannot delete status with tasks', status=400)
    return HttpResponse('')


@login_required
@require_permission('access_projects')
@require_POST
def status_toggle_visibility(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    with transaction.atomic():
        status = get_object_or_404(
            Status.objects.select_for_update(), pk=status_pk, project=project
        )
        status.visible_on_board = not status.visible_on_board
        status.save(update_fields=['visible_on_board'])
    return render(request, 'projects/partials/status_item.html', _status_item_context(project, status))


@login_required
@require_permission('access_projects')
@require_POST
def status_set_category(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    category = request.POST.get('category')
    if category not in dict(Status.CATEGORY_CHOICES):
        return HttpResponseBadRequest('Unknown status type')

    with transaction.atomic():
        status = get_object_or_404(
            Status.objects.select_for_update(), pk=status_pk, project=project
        )
        status.category = category
        # Status.save closes or reopens the tasks in the column.
        status.save(update_fields=['category'])
    return render(request, 'projects/partials/status_item.html', _status_item_context(project, status))
