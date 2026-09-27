import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.projects.models import Project, Status, can_access_project, get_assignable_users
from apps.tasks.models import Label

from .forms import SubtaskForm, TaskForm, TimeEntryForm
from .models import Subtask, Task, TimeEntry

TASKS_PER_PAGE = 20


def _time_context(user, task):
    """Close expired timers, then the entries, edit flag, and logged total."""
    from apps.tasks import services

    services.close_expired_timers()
    return {
        'time_entries': services.entries_on_task(user, task),
        'can_log_time': can_access_project(user, task.project, 'editor'),
        'logged_label': _format_duration(
            services.logged_seconds_on_task(task),
            empty='0h',
        ),
    }


def _monday(day):
    return day - timedelta(days=day.weekday())


def _format_duration(total_seconds, *, empty=None):
    """Week-total shape (``3h 05m``). ``empty`` replaces a zero total."""
    total_seconds = max(int(total_seconds), 0)
    if total_seconds == 0 and empty is not None:
        return empty
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f'{hours}h {minutes:02d}m'


def _format_total(entries):
    total_seconds = 0
    for entry in entries:
        if entry.duration is not None:
            total_seconds += max(int(entry.duration.total_seconds()), 0)
    return _format_duration(total_seconds)


@login_required
@require_permission('access_tasks')
def my_tasks(request):
    # Determine active tab from URL
    active_tab = 'todos' if request.resolver_match.url_name == 'my_tasks_todos' else 'tasks'

    tasks_qs = (
        Task.objects.open_for(request.user)
        .select_related('project', 'status')
        .order_by('-created_at')
    )
    priority = request.GET.get('priority')
    if priority:
        tasks_qs = tasks_qs.filter(priority=priority)
    status_filter = request.GET.get('status')
    if status_filter:
        tasks_qs = tasks_qs.filter(status__name=status_filter)

    paginator = Paginator(tasks_qs, TASKS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get user's todos
    from apps.todos.models import Todo
    show_completed_todos = request.GET.get('show_completed_todos', '').lower() == 'true'
    todos_qs = Todo.objects.filter(owner=request.user).select_related('client')
    todo_count = todos_qs.filter(is_completed=False).count()
    if not show_completed_todos:
        todos_qs = todos_qs.filter(is_completed=False)

    return render(request, 'tasks/my_tasks.html', {
        'tasks': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'priority_filter': priority,
        'status_filter': status_filter,
        'todos': todos_qs,
        'show_completed': show_completed_todos,
        'todo_count': todo_count,
        'today': timezone.now().date(),
        'active_tab': active_tab,
    })


@login_required
@require_permission('access_tasks')
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_access_project(request.user, project, 'editor'):
        return HttpResponseForbidden("Editor access required to create tasks")

    # Get status from query param or default to first status
    status_pk = request.GET.get('status') or request.POST.get('status_id')
    if status_pk:
        status = get_object_or_404(Status, pk=status_pk, project=project)
    else:
        status = project.statuses.filter(visible_on_board=True).first() or project.statuses.first()

    if request.method == 'POST':
        form = TaskForm(project, request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.status = status
            task._changed_by = request.user
            task.save()
            form.save_m2m()
            if request.htmx:
                response = HttpResponse('')
                response['HX-Trigger'] = json.dumps({
                    'closeSlideOver': True,
                    'taskStatusChanged': True,
                })
                return response
            return redirect('project_board', pk=project.pk)
        if request.htmx:
            team_members = get_assignable_users(project)
            project_labels = project.labels.all()
            priority_choices = Task.PRIORITY_CHOICES
            return render(request, 'tasks/task_create_slideover.html', {
                'form': form,
                'project': project,
                'selected_status': status,
                'team_members': team_members,
                'project_labels': project_labels,
                'priority_choices': priority_choices,
            })
    else:
        form = TaskForm(project)

    # Context for custom dropdown components
    team_members = get_assignable_users(project)
    project_labels = project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES

    # Return slide-over for HTMX, full page otherwise
    if request.htmx:
        return render(request, 'tasks/task_create_slideover.html', {
            'form': form,
            'project': project,
            'selected_status': status,
            'team_members': team_members,
            'project_labels': project_labels,
            'priority_choices': priority_choices,
        })
    return render(request, 'tasks/task_form.html', {
        'form': form,
        'project': project,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })


@login_required
@require_permission('access_tasks')
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'attachments', 'labels', 'project__labels'),
        pk=pk
    )
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    subtask_form = SubtaskForm()
    team_members = get_assignable_users(task.project)
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'subtask_form': subtask_form,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
        **_time_context(request.user, task),
    })


@login_required
@require_permission('access_tasks')
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to edit tasks")
    if request.method == 'POST':
        form = TaskForm(task.project, request.POST, instance=task)
        if form.is_valid():
            task._changed_by = request.user
            form.save()
            if request.htmx:
                return render(request, 'tasks/task_detail.html', {
                    'task': task,
                    'subtask_form': SubtaskForm(),
                    **_time_context(request.user, task),
                })
            return redirect('project_board', pk=task.project.pk)
    else:
        form = TaskForm(task.project, instance=task)

    team_members = get_assignable_users(task.project)
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_form.html', {
        'form': form,
        'task': task,
        'project': task.project,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })


@login_required
@require_permission('access_tasks')
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project_pk = task.project.pk
    try:
        from apps.tasks import services
        services.delete_task(task, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    if request.htmx:
        response = HttpResponse('')
        response['HX-Trigger'] = json.dumps({
            'closeSlideOver': True,
            'taskStatusChanged': True,
        })
        current_url = request.headers.get('HX-Current-URL', '')
        if f'/project/{project_pk}/{pk}/' in current_url:
            response['HX-Redirect'] = reverse('project_board', args=[project_pk])
        return response
    return redirect('project_board', pk=project_pk)


@login_required
@require_permission('access_tasks')
@require_POST
@transaction.atomic
def task_move(request):
    try:
        task_id = int(request.POST.get('task_id', ''))
        status_id = int(request.POST.get('status_id', ''))
    except (TypeError, ValueError):
        return HttpResponse('Invalid task or status', status=400)

    raw_position = request.POST.get('position')
    position = None
    if raw_position not in (None, ''):
        try:
            position = int(raw_position)
        except (TypeError, ValueError):
            return HttpResponse('Invalid position', status=400)

    # move_task takes the row locks itself, in a deadlock-safe order.
    task = get_object_or_404(Task, pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    try:
        from apps.tasks import services
        services.move_task(task, status, request.user, position=position)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    except Task.DoesNotExist:
        return HttpResponse('Task no longer exists', status=404)
    # The board is driven by a raw fetch(), which ignores HX-Trigger; the caller
    # dispatches the taskStatusChanged event itself.
    return HttpResponse(status=204)


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    status_id = request.POST.get('status_id')
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    try:
        from apps.tasks import services
        services.move_task(task, status, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    except Task.DoesNotExist:
        return HttpResponse('Task no longer exists', status=404)
    response = render(request, 'tasks/partials/status_dropdown.html', {'task': task})
    response['HX-Trigger'] = 'taskStatusChanged, activityUpdated'
    return response


@login_required
@require_permission('access_tasks')
@require_POST
@transaction.atomic
def subtask_create(request, pk):
    task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
    form = SubtaskForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=400)
    try:
        from apps.tasks import services
        subtask = services.create_subtask(task, form.cleaned_data['title'], request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(html + counter_html)


@login_required
@require_permission('access_tasks')
@require_POST
def subtask_toggle(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    try:
        from apps.tasks import services
        services.toggle_subtask(subtask, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    task = subtask.task
    html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(html + counter_html)


@login_required
@require_permission('access_tasks')
@require_POST
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    task = subtask.task
    try:
        from apps.tasks import services
        services.delete_subtask(subtask, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(counter_html)


@login_required
@require_permission('access_tasks')
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    content = request.POST.get('content', '').strip()
    if not content:
        return HttpResponse(status=400)
    try:
        from apps.tasks import services
        activity = services.add_comment(task, content, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return render(request, 'tasks/partials/activity_item.html', {'activity': activity})


@login_required
@require_permission('access_tasks')
def task_activity_list(request, pk):
    """Return just the activity list for a task (for HTMX refresh)."""
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    return render(request, 'tasks/partials/activity_list.html', {'task': task})


@login_required
@require_permission('access_tasks')
@require_POST
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        attachment = services.upload_attachment(task, request.FILES.get('file'), request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    except ValueError as e:
        return HttpResponse(str(e), status=400)
    return render(request, 'tasks/partials/attachment_item.html', {'attachment': attachment})


@login_required
@require_permission('access_tasks')
def task_full_page(request, project_pk, task_pk):
    """Full page task view with properties sidebar."""
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'labels', 'project__labels'),
        pk=task_pk, project_id=project_pk
    )
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    team_members = get_assignable_users(task.project)
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_full_page.html', {
        'task': task,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
        **_time_context(request.user, task),
    })


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_assignee(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        assignee_id = request.POST.get('assignee_id')
        assignee = None
        if assignee_id:
            # A non-numeric id makes the pk lookup raise ValueError, not return empty.
            try:
                assignee_pk = int(assignee_id)
            except (TypeError, ValueError):
                return HttpResponse('Invalid assignee', status=400)
            assignee = get_assignable_users(task.project).filter(pk=assignee_pk).first()
            if assignee is None:
                return HttpResponseForbidden('Invalid assignee')
        services.update_task_field(task, 'assignee', assignee, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    team_members = get_assignable_users(task.project)
    response = render(request, 'tasks/partials/assignee_dropdown.html', {
        'task': task, 'team_members': team_members
    })
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}'
    return response


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_priority(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        services.update_task_field(
            task, 'priority',
            request.POST.get('priority') or '',
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/priority_dropdown.html', {
        'task': task, 'priority_choices': Task.PRIORITY_CHOICES
    })
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}'
    return response


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_due_date(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        due_date = request.POST.get('due_date')
        # parse_date returns None for malformed input but raises ValueError for
        # well-formed-but-impossible dates such as 2026-02-30.
        try:
            parsed_date = parse_date(due_date) if due_date else None
        except ValueError:
            return HttpResponse('Invalid date', status=400)
        if due_date and parsed_date is None:
            return HttpResponse('Invalid date format', status=400)
        services.update_task_field(task, 'due_date', parsed_date, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/due_date_picker.html', {'task': task})
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}'
    return response


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_estimate(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        estimate = request.POST.get('time_estimate')
        try:
            value = int(estimate) if estimate else None
        except (ValueError, TypeError):
            return HttpResponse('Invalid time estimate', status=400)
        services.update_task_field(task, 'time_estimate', value, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/estimate_input.html', {'task': task})
    response['HX-Trigger'] = f'taskUpdated-{pk}'
    return response


@login_required
@require_permission('access_tasks')
@require_POST
def task_toggle_label(request, pk, label_pk):
    task = get_object_or_404(Task, pk=pk)
    label = get_object_or_404(Label, pk=label_pk, project=task.project)
    try:
        from apps.tasks import services
        services.toggle_label(task, label, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    project_labels = task.project.labels.all()
    response = render(request, 'tasks/partials/labels_selector.html', {
        'task': task, 'project_labels': project_labels
    })
    response['HX-Trigger'] = f'taskUpdated-{pk}'
    return response


@login_required
@require_permission('access_tasks')
def task_edit_description(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to edit tasks")
    # Return display template if cancel=1
    if request.GET.get('cancel') == '1':
        return render(request, 'tasks/partials/description_display.html', {'task': task})
    if request.method == 'POST':
        task.description = request.POST.get('description', '')
        task._changed_by = request.user
        task.save()
        return render(request, 'tasks/partials/description_display.html', {'task': task})
    return render(request, 'tasks/partials/description_edit.html', {'task': task})


@login_required
@require_permission('access_tasks')
def task_edit_title(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to edit tasks")
    is_full = request.GET.get('full') == '1' or request.POST.get('full') == '1'
    # Return display template if cancel=1
    if request.GET.get('cancel') == '1':
        template = 'tasks/partials/title_display_full.html' if is_full else 'tasks/partials/title_display.html'
        return render(request, template, {'task': task})
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if title:
            task.title = title
            task._changed_by = request.user
            task.save()
        template = 'tasks/partials/title_display_full.html' if is_full else 'tasks/partials/title_display.html'
        response = render(request, template, {'task': task})
        response['HX-Trigger'] = f'taskUpdated-{pk}'
        return response
    template = 'tasks/partials/title_edit_full.html' if is_full else 'tasks/partials/title_edit.html'
    return render(request, template, {'task': task})


@login_required
@require_permission('access_tasks')
def task_card(request, pk):
    """Return just the task card HTML for out-of-band swaps."""
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee').prefetch_related('labels'),
        pk=pk
    )
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    return render(request, 'projects/partials/task_card.html', {'task': task})


def _timer_changed(response):
    response['HX-Trigger'] = 'timerChanged'
    return response


def _require_task_viewer(user, task):
    if not can_access_project(user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    return None


@login_required
@require_permission('access_tasks')
def time_week(request):
    """The current user's week, optionally filtered to one project."""
    from apps.tasks import services

    services.close_expired_timers()

    week_param = request.GET.get('week')
    if week_param:
        week_date = parse_date(week_param)
        if week_date is None:
            return HttpResponse('Invalid week', status=400)
        week_date = _monday(week_date)
    else:
        week_date = _monday(timezone.localdate())

    project = None
    project_param = request.GET.get('project')
    if project_param:
        try:
            project_pk = int(project_param)
        except (TypeError, ValueError):
            return HttpResponse('Invalid project', status=400)
        project = get_object_or_404(Project, pk=project_pk)
        if not can_access_project(request.user, project, 'viewer'):
            return HttpResponseForbidden("You don't have access to this project")

    entries = list(services.entries_for_week(request.user, week_date, project=project))
    if request.user.is_admin:
        open_project_ids = None
    else:
        open_project_ids = set(
            Project.objects.filter(members__user=request.user).values_list('pk', flat=True)
        )
    for entry in entries:
        entry.can_open_task = (
            open_project_ids is None or entry.task.project_id in open_project_ids
        )
    sees_everyone = project is not None and can_access_project(
        request.user, project, 'manager'
    )
    return render(request, 'tasks/time_week.html', {
        'entries': entries,
        'week_start': week_date,
        'week_end': week_date + timedelta(days=6),
        'prev_week': week_date - timedelta(days=7),
        'next_week': week_date + timedelta(days=7),
        'project': project,
        'sees_everyone': sees_everyone,
        'total_label': _format_total(entries),
    })


@login_required
@require_permission('access_tasks')
def running_timer_indicator(request):
    """The layout timer bar. ``running_timer`` comes from the context processor."""
    from apps.tasks import services

    services.close_expired_timers()
    return render(request, 'components/running_timer.html')


@login_required
@require_permission('access_tasks')
def task_time_section(request, pk):
    task = get_object_or_404(Task.objects.select_related('project'), pk=pk)
    denied = _require_task_viewer(request.user, task)
    if denied:
        return denied
    return render(request, 'tasks/partials/time_section.html', {
        'task': task,
        **_time_context(request.user, task),
    })


@login_required
@require_permission('access_tasks')
def task_logged_total(request, pk):
    """Read-only logged-hours row. Viewers and above."""
    task = get_object_or_404(Task.objects.select_related('project'), pk=pk)
    denied = _require_task_viewer(request.user, task)
    if denied:
        return denied
    return render(request, 'tasks/partials/logged_total.html', {
        'task': task,
        **_time_context(request.user, task),
    })


@login_required
@require_permission('access_tasks')
@require_POST
def timer_start(request, pk):
    task = get_object_or_404(Task.objects.select_related('project'), pk=pk)
    try:
        from apps.tasks import services
        services.start_timer(task, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return _timer_changed(HttpResponse(status=204))


@login_required
@require_permission('access_tasks')
@require_POST
def timer_stop(request):
    from apps.tasks import services

    services.close_expired_timers()
    services.stop_timer(request.user)
    return _timer_changed(HttpResponse(status=204))


def _time_entry_drawer(request, task, form, *, heading, form_action):
    return render(request, 'tasks/partials/time_entry_drawer.html', {
        'task': task,
        'form': form,
        'heading': heading,
        'form_action': form_action,
    })


@login_required
@require_permission('access_tasks')
def time_log(request, pk):
    task = get_object_or_404(Task.objects.select_related('project'), pk=pk)
    denied = _require_task_viewer(request.user, task)
    if denied:
        return denied
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden('Editor access required')

    if request.method == 'POST':
        form = TimeEntryForm(request.POST)
        inline = request.POST.get('inline') == '1'
        if form.is_valid():
            try:
                from apps.tasks import services
                services.log_manual(
                    task,
                    request.user,
                    form.cleaned_data['started_at'],
                    form.cleaned_data['ended_at'],
                    form.cleaned_data.get('note') or '',
                )
            except PermissionDenied as e:
                return HttpResponseForbidden(str(e))
            except ValueError as e:
                form.add_error(None, str(e))
            else:
                response = HttpResponse('')
                response['HX-Trigger'] = json.dumps({
                    'closeSlideOver': True,
                    'timerChanged': True,
                })
                return response
        if inline:
            message = form.errors.get('__all__') or form.errors.get('ended_at') or form.errors.get('started_at')
            text = message[0] if message else 'Check the start and end.'
            return HttpResponse(text, status=400)
    else:
        form = TimeEntryForm()
    return _time_entry_drawer(
        request,
        task,
        form,
        heading='Log time',
        form_action=reverse('time_log', args=[task.pk]),
    )


@login_required
@require_permission('access_tasks')
def time_entry_edit(request, entry_pk):
    entry = get_object_or_404(
        TimeEntry.objects.select_related('task__project', 'user'),
        pk=entry_pk,
    )
    task = entry.task
    denied = _require_task_viewer(request.user, task)
    if denied:
        return denied
    try:
        from apps.tasks import services
        services.require_entry_edit(request.user, entry)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))

    if request.method == 'POST':
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            try:
                from apps.tasks import services
                services.update_entry(
                    entry,
                    request.user,
                    started_at=form.cleaned_data['started_at'],
                    ended_at=form.cleaned_data['ended_at'],
                    note=form.cleaned_data.get('note') or '',
                )
            except PermissionDenied as e:
                return HttpResponseForbidden(str(e))
            except ValueError as e:
                form.add_error(None, str(e))
            else:
                response = HttpResponse('')
                response['HX-Trigger'] = json.dumps({
                    'closeSlideOver': True,
                    'timerChanged': True,
                })
                return response
    else:
        form = TimeEntryForm(initial={
            'started_at': entry.started_at,
            'ended_at': entry.ended_at,
            'note': entry.note,
        })
    return _time_entry_drawer(
        request,
        task,
        form,
        heading='Edit time',
        form_action=reverse('time_entry_edit', args=[entry.pk]),
    )


@login_required
@require_permission('access_tasks')
@require_POST
def time_entry_delete(request, entry_pk):
    entry = get_object_or_404(
        TimeEntry.objects.select_related('task__project'),
        pk=entry_pk,
    )
    try:
        from apps.tasks import services
        services.delete_entry(entry, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return _timer_changed(HttpResponse(status=204))
