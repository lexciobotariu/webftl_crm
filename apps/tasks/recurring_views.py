"""Repeat in the task drawer: set, change or end a task's repeating series.

Changing it needs the right to edit the task and to create tasks on its
project, since the series creates tasks there.
"""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission

from . import recurring
from .models import Task, can_create_task, can_edit_task

REPEAT_CHOICES = {
    'repeat_frequencies': [
        ('never', 'Does not repeat'), ('daily', 'Daily'), ('weekly', 'Weekly'),
        ('monthly', 'Monthly'), ('yearly', 'Yearly'),
    ],
    'weekday_choices': list(enumerate(recurring.WEEKDAY_NAMES)),
    'month_days': range(1, 32),
}


def can_repeat(user, task):
    return can_edit_task(user, task) and can_create_task(user, task.project)


def repeat_context(task, can_edit):
    rule = task.recurring
    return {
        'task': task,
        'can_repeat': can_edit,
        'repeat_summary': recurring.summary(task),
        'repeat_rule': rule,
        'repeat_days': rule.weekday_list if rule else [],
        'repeat_next': rule.next_date if rule else None,
        **REPEAT_CHOICES,
    }


@login_required
@require_permission('access_tasks')
@require_POST
def task_update_repeat(request, pk):
    task = get_object_or_404(Task.objects.select_related('project', 'recurring'), pk=pk)
    if not can_repeat(request.user, task):
        return HttpResponseForbidden("You can't change how this task repeats")
    try:
        spec = recurring.parse_repeat(request.POST)
        rule = recurring.set_repeat(task, spec, request.user)
    except ValidationError as error:
        response = render(request, 'tasks/partials/repeat_property.html', {
            **repeat_context(task, True), 'repeat_error': error.messages[0],
        })
        return response
    if rule is None:
        message = 'This task no longer repeats.'
    else:
        every = recurring.describe(rule)
        every = every[0].lower() + every[1:]
        if rule.next_date:
            message = f'Repeats {every}. Next task on {rule.next_date:%-d %b %Y}.'
        else:
            message = f'Repeats {every}, but no date is left before it ends.'
    response = render(request, 'tasks/partials/repeat_property.html', repeat_context(task, True))
    response['HX-Trigger'] = json.dumps({
        'infoToast': {'target': 'body', 'message': message},
        f'taskUpdated-{pk}': {'target': 'body'},
    })
    return response
