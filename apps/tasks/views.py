from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.projects.models import Project, Status
from .forms import TaskForm, SubtaskForm, CommentForm
from .models import Task, Subtask, Attachment


@login_required
def my_tasks(request):
    tasks = Task.objects.filter(assignee=request.user).select_related('project', 'status')
    priority = request.GET.get('priority')
    if priority:
        tasks = tasks.filter(priority=priority)
    status_filter = request.GET.get('status')
    if status_filter:
        tasks = tasks.filter(status__name=status_filter)
    return render(request, 'tasks/my_tasks.html', {'tasks': tasks})


@login_required
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    status = project.statuses.first()

    if request.method == 'POST':
        form = TaskForm(project, request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.status = status
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
        return render(request, 'tasks/task_create_slideover.html', {'form': form, 'project': project})
    return render(request, 'tasks/task_form.html', {'form': form, 'project': project})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'comments__author', 'attachments', 'labels'),
        pk=pk
    )
    subtask_form = SubtaskForm()
    comment_form = CommentForm()
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'subtask_form': subtask_form,
        'comment_form': comment_form,
    })


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = TaskForm(task.project, request.POST, instance=task)
        if form.is_valid():
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
    project_pk = task.project.pk
    task.delete()
    if request.htmx:
        return HttpResponse('')
    return redirect('project_board', pk=project_pk)


@login_required
@require_POST
def task_move(request):
    task_id = request.POST.get('task_id')
    status_id = request.POST.get('status_id')
    task = get_object_or_404(Task, pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()
    return HttpResponse(status=204)


@login_required
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    status_id = request.POST.get('status_id')
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()
    return render(request, 'tasks/partials/status_dropdown.html', {'task': task})


@login_required
@require_POST
def subtask_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = SubtaskForm(request.POST)
    if form.is_valid():
        subtask = form.save(commit=False)
        subtask.task = task
        subtask.order = task.subtasks.count()
        subtask.save()
        return render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask})
    return HttpResponse(status=400)


@login_required
@require_POST
def subtask_toggle(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    subtask.completed = not subtask.completed
    subtask.save()
    return render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask})


@login_required
@require_POST
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    subtask.delete()
    return HttpResponse('')


@login_required
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
        return render(request, 'tasks/partials/comment_item.html', {'comment': comment})
    return HttpResponse(status=400)


@login_required
@require_POST
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.FILES.get('file'):
        file = request.FILES['file']
        attachment = Attachment.objects.create(
            task=task,
            file=file,
            filename=file.name,
            uploaded_by=request.user
        )
        return render(request, 'tasks/partials/attachment_item.html', {'attachment': attachment})
    return HttpResponse(status=400)
