"""Recurring tasks: the list on a project (and on its service's page), the drawer, and the actions.

Seeing them follows task view rights on the project; changing them needs the
right to create tasks there (``can_create_task``). Every change answers with a
toast and the ``recurringChanged`` event, which reloads the recurring panel
wherever it is shown.
"""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.projects.models import Project

from . import recurring
from .forms import RecurringTaskForm
from .models import RecurringTask, Task, can_create_task, can_view_task, can_view_tasks_on


def _events(response, message, *more):
    triggers = {'infoToast': {'target': 'body', 'message': message}, 'recurringChanged': {'target': 'body'}}
    for name in more:
        triggers[name] = {'target': 'body'}
    response['HX-Trigger'] = json.dumps(triggers)
    return response


def panel_context(user, project):
    """What the recurring panel shows for ``project``: each rule with its recent tasks."""
    rules = (
        RecurringTask.objects.filter(project=project)
        .select_related('assignee', 'status').order_by('paused', 'title', 'pk')
    )
    return {
        'project': project,
        'rows': [
            {'rule': rule, 'schedule': recurring.describe(rule), 'tasks': recurring.recent_tasks(rule, 3)}
            for rule in rules
        ],
        'can_manage': can_create_task(user, project),
    }


@login_required
def recurring_list(request, project_pk):
    project = get_object_or_404(Project.objects.select_related('client'), pk=project_pk)
    if not can_view_tasks_on(request.user, project):
        return HttpResponseForbidden("You don't have access to tasks")
    return render(request, 'tasks/recurring_list.html', panel_context(request.user, project))


@login_required
def recurring_panel(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_view_tasks_on(request.user, project):
        return HttpResponseForbidden("You don't have access to tasks")
    return render(request, 'tasks/partials/recurring_panel.html', panel_context(request.user, project))


def _save(request, project, form):
    rule = form.save(commit=False)
    rule.project = project
    if rule.pk is None:
        rule.created_by = request.user
    recurring.schedule(rule)
    rule.save()
    form.save_m2m()
    return rule


def _drawer(request, project, form, rule=None):
    return render(request, 'tasks/partials/recurring_drawer.html', {
        'project': project, 'form': form, 'rule': rule,
    })


@login_required
def recurring_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_create_task(request.user, project):
        return HttpResponseForbidden("You can't create tasks on this project")
    if request.method == 'POST':
        form = RecurringTaskForm(project, request.POST, instance=RecurringTask(project=project))
        if form.is_valid():
            rule = _save(request, project, form)
            response = HttpResponse('')
            first = rule.next_date
            when = f' The first task comes on {first:%-d %b %Y}.' if first else ''
            return _events(response, f'Recurring task saved: {rule.title}.{when}', 'closeSlideOver')
    else:
        initial = {}
        source = Task.objects.filter(pk=request.GET.get('from_task') or 0, project=project).first()
        if source is not None and can_view_task(request.user, source):
            initial = {
                'title': source.title, 'description': source.description, 'assignee': source.assignee_id,
                'priority': source.priority, 'billable': source.billable,
                'labels': list(source.labels.values_list('pk', flat=True)),
                'checklist': '\n'.join(source.subtasks.values_list('title', flat=True)),
            }
        form = RecurringTaskForm(project, initial=initial, instance=RecurringTask(project=project))
    return _drawer(request, project, form)


def _rule_or_403(request, pk):
    rule = get_object_or_404(RecurringTask.objects.select_related('project'), pk=pk)
    if not can_create_task(request.user, rule.project):
        return rule, HttpResponseForbidden("You can't change recurring tasks on this project")
    return rule, None


@login_required
def recurring_edit(request, pk):
    rule, denied = _rule_or_403(request, pk)
    if denied:
        return denied
    if request.method == 'POST':
        form = RecurringTaskForm(rule.project, request.POST, instance=rule)
        if form.is_valid():
            rule = _save(request, rule.project, form)
            return _events(HttpResponse(''), f'Recurring task saved: {rule.title}.', 'closeSlideOver')
    else:
        form = RecurringTaskForm(rule.project, instance=rule)
    return _drawer(request, rule.project, form, rule)


@login_required
@require_POST
def recurring_pause(request, pk):
    rule, denied = _rule_or_403(request, pk)
    if denied:
        return denied
    rule.paused = not rule.paused
    if not rule.paused:
        recurring.schedule(rule)
    rule.save(update_fields=['paused', 'next_date', 'updated_at'])
    message = f'Paused: {rule.title}' if rule.paused else f'Resumed: {rule.title}'
    return _events(HttpResponse(''), message)


@login_required
@require_POST
def recurring_run(request, pk):
    """Create the task of the current period now, instead of waiting for the daily job."""
    rule, denied = _rule_or_403(request, pk)
    if denied:
        return denied
    try:
        day, task = recurring.create_now(rule, request.user)
    except ValidationError as exc:
        return _events(HttpResponse(''), f'Nothing created: {exc.messages[0]}')
    if task is None:
        return _events(HttpResponse(''), f'"{recurring.task_title(rule, day)}" was already created.')
    return _events(HttpResponse(''), f'Created {task.identifier}: {task.title}', 'taskChanged')


@login_required
@require_POST
def recurring_delete(request, pk):
    rule, denied = _rule_or_403(request, pk)
    if denied:
        return denied
    title = rule.title
    rule.delete()
    return _events(HttpResponse(''), f'Deleted the recurring task {title}. Its tasks stay.')
