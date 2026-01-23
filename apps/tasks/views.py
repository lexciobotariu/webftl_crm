import os

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

TASKS_PER_PAGE = 20

# File upload security settings
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.txt', '.csv', '.zip'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

from apps.accounts.models import User
from apps.projects.models import Project, Status, can_access_project
from apps.tasks.models import Label
from .forms import TaskForm, SubtaskForm
from .models import Task, Subtask, Attachment, TaskActivity


@login_required
def my_tasks(request):
    # Determine active tab from URL
    active_tab = 'todos' if request.resolver_match.url_name == 'my_tasks_todos' else 'tasks'

    tasks_qs = Task.objects.filter(assignee=request.user).select_related('project', 'status').order_by('-created_at')
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
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_access_project(request.user, project, 'editor'):
        return HttpResponseForbidden("Editor access required to create tasks")

    # Get status from query param or default to first status
    status_pk = request.GET.get('status') or request.POST.get('status_id')
    if status_pk:
        status = get_object_or_404(Status, pk=status_pk, project=project)
    else:
        status = project.statuses.first()

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
                # Re-render the entire kanban board after task creation
                statuses = project.statuses.prefetch_related('tasks')
                response = render(request, 'projects/partials/kanban_board.html', {'project': project})
                response['HX-Trigger'] = 'closeSlideOver'
                return response
            return redirect('project_board', pk=project.pk)
    else:
        form = TaskForm(project)

    # Return slide-over for HTMX, full page otherwise
    if request.htmx:
        return render(request, 'tasks/task_create_slideover.html', {
            'form': form,
            'project': project,
            'selected_status': status,
        })
    return render(request, 'tasks/task_form.html', {'form': form, 'project': project})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'attachments', 'labels', 'project__labels'),
        pk=pk
    )
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    subtask_form = SubtaskForm()
    team_members = User.objects.all()
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'subtask_form': subtask_form,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })


@login_required
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
                return render(request, 'tasks/task_detail.html', {'task': task, 'subtask_form': SubtaskForm(), 'comment_form': CommentForm()})
            return redirect('project_board', pk=task.project.pk)
    else:
        form = TaskForm(task.project, instance=task)
    return render(request, 'tasks/task_form.html', {'form': form, 'task': task, 'project': task.project})


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to delete tasks")
    project_pk = task.project.pk
    task.delete()
    if request.htmx:
        return HttpResponse('')
    return redirect('project_board', pk=project_pk)


@login_required
@require_POST
@transaction.atomic
def task_move(request):
    task_id = request.POST.get('task_id')
    status_id = request.POST.get('status_id')
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to move tasks")
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task._changed_by = request.user
    task.save()
    return HttpResponse(status=204)


@login_required
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to update tasks")
    status_id = request.POST.get('status_id')
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task._changed_by = request.user
    task.save()
    response = render(request, 'tasks/partials/status_dropdown.html', {'task': task})
    response['HX-Trigger'] = 'taskStatusChanged, activityUpdated'
    return response


@login_required
@require_POST
@transaction.atomic
def subtask_create(request, pk):
    task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to create subtasks")
    form = SubtaskForm(request.POST)
    if form.is_valid():
        subtask = form.save(commit=False)
        subtask.task = task
        # Use Max to safely get the next order value
        max_order = task.subtasks.aggregate(Max('order'))['order__max']
        subtask.order = (max_order or -1) + 1
        subtask.save()
        # Return both subtask item and updated counter (OOB swap)
        html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
        counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
        return HttpResponse(html + counter_html)
    return HttpResponse(status=400)


@login_required
@require_POST
def subtask_toggle(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    if not can_access_project(request.user, subtask.task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to update subtasks")
    subtask.completed = not subtask.completed
    subtask.save()
    # Return both subtask item and updated counter (OOB swap)
    task = subtask.task
    html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(html + counter_html)


@login_required
@require_POST
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    if not can_access_project(request.user, subtask.task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to delete subtasks")
    task = subtask.task
    subtask.delete()
    # Return updated counter (OOB swap)
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(counter_html)


@login_required
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    content = request.POST.get('content', '').strip()
    if content:
        activity = TaskActivity.objects.create(
            task=task,
            user=request.user,
            activity_type='comment',
            content=content
        )
        return render(request, 'tasks/partials/activity_item.html', {'activity': activity})
    return HttpResponse(status=400)


@login_required
def task_activity_list(request, pk):
    """Return just the activity list for a task (for HTMX refresh)."""
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    return render(request, 'tasks/partials/activity_list.html', {'task': task})


@login_required
@require_POST
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to upload attachments")
    file = request.FILES.get('file')

    if not file:
        return HttpResponse('No file provided', status=400)

    # Validate file extension
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return HttpResponse(f'File type not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}', status=400)

    # Validate file size
    if file.size > MAX_FILE_SIZE:
        return HttpResponse('File too large. Maximum size is 10MB.', status=400)

    # Sanitize filename to prevent path traversal
    safe_filename = get_valid_filename(file.name)

    attachment = Attachment.objects.create(
        task=task,
        file=file,
        filename=safe_filename,
        uploaded_by=request.user
    )
    return render(request, 'tasks/partials/attachment_item.html', {'attachment': attachment})


@login_required
def task_full_page(request, project_pk, task_pk):
    """Full page task view with properties sidebar."""
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'labels', 'project__labels'),
        pk=task_pk, project_id=project_pk
    )
    if not can_access_project(request.user, task.project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this task")
    team_members = User.objects.all()
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_full_page.html', {
        'task': task,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })


@login_required
@require_POST
def task_update_assignee(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        assignee_id = request.POST.get('assignee_id')
        assignee = User.objects.get(pk=assignee_id) if assignee_id else None
        services.update_task_field(task, 'assignee', assignee, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    team_members = User.objects.all()
    response = render(request, 'tasks/partials/assignee_dropdown.html', {
        'task': task, 'team_members': team_members
    })
    response['HX-Trigger'] = 'activityUpdated'
    return response


@login_required
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
    response['HX-Trigger'] = 'activityUpdated'
    return response


@login_required
@require_POST
def task_update_due_date(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        due_date = request.POST.get('due_date')
        services.update_task_field(
            task, 'due_date',
            due_date if due_date else None,
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/due_date_picker.html', {'task': task})
    response['HX-Trigger'] = 'activityUpdated'
    return response


@login_required
@require_POST
def task_update_estimate(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        estimate = request.POST.get('time_estimate')
        services.update_task_field(
            task, 'time_estimate',
            int(estimate) if estimate else None,
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return render(request, 'tasks/partials/estimate_input.html', {'task': task})


@login_required
@require_POST
def task_toggle_label(request, pk, label_pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, 'editor'):
        return HttpResponseForbidden("Editor access required to update tasks")
    label = get_object_or_404(Label, pk=label_pk, project=task.project)
    if label in task.labels.all():
        task.labels.remove(label)
    else:
        task.labels.add(label)
    project_labels = task.project.labels.all()
    return render(request, 'tasks/partials/labels_selector.html', {
        'task': task, 'project_labels': project_labels
    })


@login_required
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
        return render(request, template, {'task': task})
    template = 'tasks/partials/title_edit_full.html' if is_full else 'tasks/partials/title_edit.html'
    return render(request, template, {'task': task})
