import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.db.models.deletion import RestrictedError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.models import User
from apps.clients.models import Client, visible_clients
from apps.tasks.models import Label, TaskActivity, can_create_task, visible_tasks

from .forms import LabelForm, ProjectForm, StatusForm
from .models import (
    Project,
    ProjectAccess,
    Status,
    can_access_project,
    can_edit_project,
    visible_projects,
)

PROJECTS_PER_PAGE = 20


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
            return redirect('project_board', pk=project.pk)
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

    # Calculate stats. "Done" is whatever the project marks with Status.is_done,
    # so renaming a column cannot break these numbers.
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
        'project_detail_tasks': 'tasks',
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
        'tasks': tasks,
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


@login_required
@require_permission('access_projects')
def project_board(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")

    shown = visible_tasks(request.user, project)
    visible_statuses = (
        project.statuses.filter(visible_on_board=True)
        .annotate(board_task_count=Count('tasks', filter=Q(tasks__in=shown)))
        .prefetch_related(
            Prefetch(
                'tasks',
                queryset=shown.select_related('assignee').prefetch_related('labels').order_by(
                    'order', '-created_at'
                ),
            )
        )
    )
    hidden_task_count = shown.filter(status__visible_on_board=False).count()

    context = {
        'project': project,
        'visible_statuses': visible_statuses,
        'hidden_task_count': hidden_task_count,
        'can_edit_project': can_edit_project(request.user, project),
        'can_create_task': can_create_task(request.user, project),
    }

    if request.htmx:
        return render(request, 'projects/partials/kanban_board.html', context)
    return render(request, 'projects/project_board.html', context)


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
    next_page = request.GET.get('next', 'board')
    if next_page == 'detail':
        back_url = 'project_detail'
    else:
        back_url = 'project_board'

    status_form = StatusForm()
    label_form = LabelForm()
    return render(request, 'projects/project_settings.html', {
        'project': project,
        'status_form': status_form,
        'label_form': label_form,
        'back_url': back_url,
        'can_edit_project': can_edit_project(request.user, project),
    })


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

    errors = {}
    if not name:
        errors['name'] = 'Name is required.'

    if errors:
        return render(request, 'projects/partials/settings_general_form.html', {
            'project': project,
            'errors': errors,
        })

    project.name = name
    project.description = description
    project.github_repo_url = github_repo_url
    project.save()

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
                {'status': status, 'project': project},
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
    return render(request, 'projects/partials/status_item.html', {'status': status, 'project': project})


@login_required
@require_permission('access_projects')
@require_POST
def status_toggle_done(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_edit_project(request.user, project):
        return HttpResponseForbidden("You can't edit this project")

    with transaction.atomic():
        status = get_object_or_404(
            Status.objects.select_for_update(), pk=status_pk, project=project
        )
        status.is_done = not status.is_done
        status.save(update_fields=['is_done'])
    return render(request, 'projects/partials/status_item.html', {'status': status, 'project': project})
