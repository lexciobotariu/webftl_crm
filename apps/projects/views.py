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
from django.utils.dateparse import parse_date
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

from .forms import LabelForm, ProjectForm, StatusForm, deadline_error, project_field_errors
from .keys import KEY_REGEX
from .models import (
    Project,
    ProjectAccess,
    ProjectTaskView,
    Status,
    can_access_project,
    can_edit_project,
    project_delete_blocker,
    visible_projects,
)
from .services import with_task_counts

PROJECTS_PER_PAGE = 20


def _status_item_context(project, status):
    return {'status': status, 'project': project, 'category_choices': Status.CATEGORY_CHOICES}


def _client_linkable(user, project):
    """Whether the project's client name may link to the client page.

    A project can be visible (``projects_view_all``) while its client is not;
    then the name stays plain text instead of leading to a 404.
    """
    return (
        user.has_app_permission('access_clients')
        and visible_clients(user).filter(pk=project.client_id).exists()
    )


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
    projects_qs = (
        with_task_counts(visible_projects(request.user), request.user)
        .select_related('client')
        .order_by('name')
    )
    # Finished and cancelled projects stay out of the way unless asked for.
    show_closed = request.GET.get('closed') == '1'
    clients = Client.objects.none()
    client_filter = None
    linkable_client_ids = set()
    if request.user.has_app_permission('access_clients'):
        client_filter = request.GET.get('client')
        if client_filter and client_filter.isdigit():
            projects_qs = projects_qs.filter(client_id=client_filter)
        else:
            client_filter = None
        clients = visible_clients(request.user).order_by('name')
        # A project can be visible while its client is not; that name stays plain text.
        linkable_client_ids = set(clients.values_list('pk', flat=True))

    open_q = Q(status__in=Project.OPEN_STATUSES)
    closed_count = projects_qs.exclude(open_q).count()
    projects_qs = projects_qs.exclude(open_q) if show_closed else projects_qs.filter(open_q)

    paginator = Paginator(projects_qs, PROJECTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'projects/project_list.html', {
        'projects': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'clients': clients,
        'client_filter': client_filter,
        'linkable_client_ids': linkable_client_ids,
        'show_closed': show_closed,
        'closed_count': closed_count,
        # ``?new=1`` (an old link to the create page) opens the New Project drawer.
        'open_create_drawer': (
            request.GET.get('new') == '1' and request.user.has_app_permission('projects_create')
        ),
        'new_client': request.GET.get('new_client', '') if request.GET.get('new_client', '').isdigit() else '',
    })


@login_required
@require_permission('access_projects')
def project_create(request):
    """The New Project drawer opened from the projects page.

    The same drawer the client page opens, with a client picker. Opened as a
    page (an old link or a new tab), it lands on the projects list with the
    drawer open.
    """
    if not request.user.has_app_permission('projects_create'):
        return HttpResponseForbidden("You can't create projects")

    if request.method == 'POST':
        form = ProjectForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save()
            ProjectAccess.objects.create(project=project, user=request.user)
            target = reverse('project_tasks', args=[project.pk])
            if request.htmx:
                response = HttpResponse('')
                response['HX-Redirect'] = target
                return response
            return redirect(target)
        return render(request, 'projects/partials/project_create_drawer.html', {
            'form': form,
            'clients': form.fields['client'].queryset,
            'error': next(iter(form.errors.values()))[0],
            'form_client': form.data.get('client', ''),
            'form_name': form.data.get('name', ''),
            'form_description': form.data.get('description', ''),
            'form_github_repo_url': form.data.get('github_repo_url', ''),
            'form_start_date': form.data.get('start_date', ''),
            'form_deadline': form.data.get('deadline', ''),
        })

    client_id = request.GET.get('client', '')
    client_id = client_id if client_id.isdigit() else ''
    if not request.htmx:
        query = '?new=1' + (f'&new_client={client_id}' if client_id else '')
        return redirect(reverse('project_list') + query)
    form = ProjectForm(user=request.user)
    return render(request, 'projects/partials/project_create_drawer.html', {
        'form': form,
        'clients': form.fields['client'].queryset,
        'form_client': client_id,
    })


@login_required
@require_permission('access_projects')
def project_detail(request, pk):
    """Project detail page with overview, tasks, notes, and team tabs."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project):
        return HttpResponseForbidden("You don't have access to this project")

    # Calculate stats. "Done" is whatever the project files under the completed status type,
    # so renaming a column cannot break these numbers. Archived tasks are left out, as on
    # the Tasks page and in the project lists, and counted on their own.
    visible = visible_tasks(request.user, project)
    tasks = visible.not_archived()
    total_tasks = tasks.count()
    completed_tasks = tasks.done().count()
    active_tasks = tasks.active().count()
    overdue_tasks = tasks.overdue().count()
    archived_tasks = visible.archived().count()

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

    figures = None
    project_invoices = None
    if active_tab == 'overview':
        from .figures import project_figures
        figures = project_figures(request.user, project, tasks)
        if request.user.has_app_permission('access_invoices'):
            from apps.invoices.models import visible_invoices
            project_invoices = visible_invoices(request.user).filter(project=project).order_by('-issue_date', '-number')

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
        'archived_tasks': archived_tasks,
        'figures': figures,
        'project_invoices': project_invoices,
        'recent_activities': recent_activities,
        'active_tab': active_tab,
        'can_edit_project': editable,
        'can_create_task': can_create_task(request.user, project),
        'client_linkable': _client_linkable(request.user, project),
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
        'client_linkable': _client_linkable(request.user, project),
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
    with transaction.atomic():
        project = get_object_or_404(Project.objects.select_for_update(), pk=pk)
        blocker = project_delete_blocker(project)
        if blocker:
            return HttpResponse(blocker, status=400)
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
        'client_linkable': _client_linkable(request.user, project),
        'can_edit_project': can_edit_project(request.user, project),
        'status_choices': Project.STATUS_CHOICES,
        'billing_choices': Project.BILLING_CHOICES,
        'delete_blocker': project_delete_blocker(project),
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


def _posted_date(data, name, current):
    """Return ``(value, error)`` for a date field; missing keeps ``current``, empty clears it.

    An invalid value is returned as typed so the form shows it back.
    """
    if name not in data:
        return current, None
    text = data.get(name, '').strip()
    if not text:
        return None, None
    try:
        value = parse_date(text)
    except ValueError:
        value = None
    if value is None:
        return text, 'Enter a date such as 2026-10-31.'
    return value, None


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
    # A form without the sync checkbox keeps the setting; without a repository, sync is off.
    if 'github_sync_field' in request.POST:
        github_sync_enabled = request.POST.get('github_sync_enabled') == 'on'
    else:
        github_sync_enabled = project.github_sync_enabled
    github_sync_enabled = github_sync_enabled and bool(github_repo_url)
    # A form without the field keeps the rate; an empty field clears it.
    rate_text = request.POST.get('hourly_rate')
    hourly_rate, rate_error = project.hourly_rate, None
    if rate_text is not None:
        hourly_rate, rate_error = parse_hourly_rate(rate_text)
        if rate_error:
            hourly_rate = rate_text.strip()  # shown back in the form, never saved

    # A form without the field keeps the status.
    status = request.POST.get('status', project.status)
    billing_type = request.POST.get('billing_type', project.billing_type)
    # Like the rate: a form without the field keeps the price; an empty field clears it.
    price_text = request.POST.get('fixed_price')
    fixed_price, price_error = project.fixed_price, None
    if price_text is not None:
        fixed_price, price_error = parse_hourly_rate(price_text)
        if price_error:
            fixed_price = price_text.strip()
    start_date, start_error = _posted_date(request.POST, 'start_date', project.start_date)
    deadline, deadline_parse_error = _posted_date(request.POST, 'deadline', project.deadline)

    # The form re-renders from ``project``, so an error keeps what was typed.
    status_known = status in dict(Project.STATUS_CHOICES)
    if status_known:
        project.status = status
    billing_known = billing_type in dict(Project.BILLING_CHOICES)
    if billing_known:
        project.billing_type = billing_type
    project.fixed_price = fixed_price
    project.start_date = start_date
    project.deadline = deadline
    project.name = name
    project.description = description
    project.github_repo_url = github_repo_url
    project.github_sync_enabled = github_sync_enabled
    project.key = key
    project.hourly_rate = hourly_rate

    errors = project_field_errors(name, github_repo_url)
    if not status_known:
        errors['status'] = 'Choose a status from the list.'
    if not billing_known:
        errors['billing_type'] = 'Choose a billing type from the list.'
    if price_error:
        errors['fixed_price'] = price_error
    if start_error:
        errors['start_date'] = start_error
    if deadline_parse_error:
        errors['deadline'] = deadline_parse_error
    elif not start_error and deadline_error(start_date, deadline):
        errors['deadline'] = deadline_error(start_date, deadline)
    if rate_error:
        errors['hourly_rate'] = rate_error
    if not re.fullmatch(KEY_REGEX, key, flags=re.ASCII):
        errors['key'] = '2 to 6 capital letters or digits, starting with a letter.'
    elif Project.objects.filter(key=key).exclude(pk=project.pk).exists():
        errors['key'] = 'This key is already used by another project.'

    if not errors:
        try:
            with transaction.atomic():
                project.save(update_fields=[
                    'name', 'description', 'github_repo_url', 'github_sync_enabled', 'key',
                    'hourly_rate', 'status', 'billing_type', 'fixed_price', 'start_date',
                    'deadline', 'updated_at',
                ])
        except IntegrityError:
            # Another project took the key between the check and the save.
            errors['key'] = 'This key is already used by another project.'

    if errors:
        return render(request, 'projects/partials/settings_general_form.html', {
            'project': project,
            'errors': errors,
            'status_choices': Project.STATUS_CHOICES,
        'billing_choices': Project.BILLING_CHOICES,
        })

    return render(request, 'projects/partials/settings_general_form.html', {
        'project': project,
        'success': True,
        'status_choices': Project.STATUS_CHOICES,
        'billing_choices': Project.BILLING_CHOICES,
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
