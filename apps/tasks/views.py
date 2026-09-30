import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.projects.models import (
    Project,
    Status,
    can_access_project,
    get_assignable_users,
)
from apps.tasks.models import Label, can_create_task, can_edit_task, can_view_task

from .forms import SubtaskForm, TaskForm, TimeEntryForm
from .listview import apply_url_headers, build_groups, filter_options, group_choices, resolve_view
from .models import MyTasksView, Subtask, Task, TimeEntry
from .viewspec import CATEGORIES, LIMIT_STEP, TaskViewOptions, sort_choices


def _time_context(user, task):
    """Close expired timers, then the entries, edit flag, and logged total."""
    from apps.tasks import services

    services.close_expired_timers()
    return {
        'time_entries': services.entries_on_task(user, task),
        'can_log_time': can_edit_task(user, task),
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


# The project Tasks page offers a board too; My Tasks cannot, because a column would be a
# status type and a drop would have to pick one concrete column in every project.
MY_TASKS_OPTIONS = TaskViewOptions(
    layouts=('list',),
    groups=('project', 'category', 'priority', 'none'),
    categories=frozenset(CATEGORIES),
    has_assignee_filter=False,
    default_group='project',
    default_categories=frozenset({Status.BACKLOG, Status.UNSTARTED, Status.STARTED}),
)


@login_required
@require_permission('access_tasks')
def my_tasks(request):
    """My Tasks: the tasks assigned to this person, in the URL-driven list view."""
    tasks_tab = request.resolver_match.url_name == 'my_tasks'
    assigned = Task.objects.open_for(request.user)
    # Needed on both tabs: the Assigned Tasks count in the top bar must not change
    # with the tab or the filters. It is the dashboard's "My Active Tasks" number.
    context = {
        'active_tab': 'tasks' if tasks_tab else 'todos',
        'total_count': assigned.active().count(),
    }

    # The To-Dos tab renders without a query string; only the Tasks tab restores a view.
    if tasks_tab:
        page_url = request.path
        resolved = resolve_view(
            request,
            options=MY_TASKS_OPTIONS,
            model=MyTasksView,
            lookup={'user': request.user},
            page_url=page_url,
        )
        if isinstance(resolved, HttpResponseRedirect):
            return resolved
        spec, from_toolbar = resolved

        matching = assigned.matching(spec)
        total_matching = matching.count()
        # What the default view leaves out is hidden too, so every page of this
        # view measures "hidden" against all of the person's tasks.
        total_visible = assigned.count()
        page = (
            matching.ordered_for(spec)
            .select_related('project', 'status', 'assignee')
            .prefetch_related('labels')[: spec.limit]
        )
        context.update({
            'spec': spec,
            'groups': build_groups(page, spec, assigned.group_counts(spec)),
            'total_matching': total_matching,
            'total_visible': total_visible,
            'hidden_count': total_visible - total_matching,
            'more_url': None,
            'show_all_url': None,
            'page_url': page_url,
            'show_project': True,
            'empty_message': 'No open tasks assigned to you',
            'sort_choices': sort_choices(),
            'group_choices': group_choices(MY_TASKS_OPTIONS),
            **filter_options(
                [], spec, [], [], categories=MY_TASKS_OPTIONS.categories
            ),
        })
        if total_matching > spec.limit:
            more = spec.replace(limit=spec.limit + LIMIT_STEP).to_query_string()
            context['more_url'] = f'{page_url}?{more}'
        everything = spec.replace(categories=MY_TASKS_OPTIONS.categories)
        context['show_all_url'] = f'{page_url}?{everything.to_query_string()}'

    from apps.todos.models import Todo
    todos_qs = Todo.objects.filter(owner=request.user, is_completed=False).select_related('client')
    context.update({
        'todos': todos_qs,
        'todo_count': todos_qs.count(),
        'show_completed': False,
        'today': timezone.now().date(),
    })

    response = render(request, 'tasks/my_tasks.html', context)
    if tasks_tab:
        apply_url_headers(response, request, spec, from_toolbar, page_url)
    return response


@login_required
@require_permission('access_tasks')
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_create_task(request.user, project):
        return HttpResponseForbidden("You can't create tasks on this project")

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
            return redirect('project_tasks', pk=project.pk)
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
    if not can_view_task(request.user, task):
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
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden("You can't edit this task")
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
            return redirect('project_tasks', pk=task.project.pk)
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
            response['HX-Redirect'] = reverse('project_tasks', args=[project_pk])
        return response
    return redirect('project_tasks', pk=project_pk)


@login_required
@require_permission('access_tasks')
@require_POST
@transaction.atomic
def task_move(request):
    from apps.tasks import services

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

    # "after_id" is the card dropped under: empty for the top of the column, absent
    # for the old append/position behaviour.
    after_id = services.AFTER_UNSET
    if 'after_id' in request.POST:
        raw_after = request.POST['after_id']
        if raw_after == '':
            after_id = None
        else:
            try:
                after_id = int(raw_after)
            except (TypeError, ValueError):
                return HttpResponse('Invalid anchor', status=400)

    # move_task takes the row locks itself, in a deadlock-safe order.
    task = get_object_or_404(Task, pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    try:
        services.move_task(task, status, request.user, position=position, after_id=after_id)
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
    if not can_view_task(request.user, task):
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
    if not can_view_task(request.user, task):
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
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}, taskChanged'
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
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}, taskChanged'
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
    response['HX-Trigger'] = f'activityUpdated, taskUpdated-{pk}, taskChanged'
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
    response['HX-Trigger'] = f'taskUpdated-{pk}, taskChanged'
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
    response['HX-Trigger'] = f'taskUpdated-{pk}, taskChanged'
    return response


@login_required
@require_permission('access_tasks')
def task_edit_description(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden("You can't edit this task")
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
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden("You can't edit this task")
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
        response['HX-Trigger'] = f'taskUpdated-{pk}, taskChanged'
        return response
    template = 'tasks/partials/title_edit_full.html' if is_full else 'tasks/partials/title_edit.html'
    return render(request, template, {'task': task})


def _timer_changed(response):
    response['HX-Trigger'] = 'timerChanged'
    return response


def _require_task_viewer(user, task):
    if not can_view_task(user, task):
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
        if not can_access_project(request.user, project):
            return HttpResponseForbidden("You don't have access to this project")

    entries = list(services.entries_for_week(request.user, week_date, project=project))
    for entry in entries:
        entry.can_open_task = can_view_task(request.user, entry.task)
    sees_everyone = project is not None and (
        request.user.is_admin or request.user.has_app_permission('tasks_view_all')
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
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden("You can't edit this task")

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
