import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import Client

from .forms import TodoForm
from .models import Todo


def _set_todo_triggers(response, *, has_client=False, close=False):
    """
    Attach HX-Trigger header so any page showing todos can refresh via HTMX.
    """
    triggers = {'refreshPersonalTodos': True}
    if has_client:
        triggers['refreshClientTodos'] = True
    if close:
        triggers['closeSlideOver'] = True
    response['HX-Trigger'] = json.dumps(triggers)
    return response


@login_required
@require_permission('access_todos')
def todo_list(request):
    """Personal to-dos list (HTMX partial)."""
    todos_qs = Todo.objects.filter(owner=request.user).select_related('client')

    # Filter by show_completed param (default False to hide completed)
    show_completed = request.GET.get('show_completed', '').lower() == 'true'
    if not show_completed:
        todos_qs = todos_qs.filter(is_completed=False)

    return render(request, 'todos/partials/todo_list.html', {
        'todos': todos_qs,
        'show_completed': show_completed,
        'today': timezone.now().date(),
    })


@login_required
@require_permission('access_todos')
def todo_create(request):
    """Create personal to-do (drawer). GET renders form, POST creates todo."""
    if request.method == 'POST':
        form = TodoForm(request.POST, user=request.user)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.owner = request.user
            todo.save()
            response = HttpResponse('')
            return _set_todo_triggers(response, has_client=bool(todo.client_id), close=True)
        # If form invalid, re-render drawer with errors
        return render(request, 'todos/partials/todo_create_drawer.html', {'form': form})

    form = TodoForm(user=request.user)
    return render(request, 'todos/partials/todo_create_drawer.html', {'form': form})


@login_required
@require_permission('access_todos')
def todo_detail(request, pk):
    """View/edit to-do (drawer)."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    form = TodoForm(instance=todo, user=request.user)
    return render(request, 'todos/partials/todo_detail_drawer.html', {
        'todo': todo,
        'form': form,
    })


@login_required
@require_permission('access_todos')
@require_POST
def todo_edit(request, pk):
    """Update to-do fields. Returns HTMX response."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    form = TodoForm(request.POST, instance=todo, user=request.user)
    if form.is_valid():
        todo_obj = form.save(commit=False)
        is_completed = request.POST.get('is_completed') is not None
        todo_obj.is_completed = is_completed
        if is_completed:
            todo_obj.completed_at = todo_obj.completed_at or timezone.now()
        else:
            todo_obj.completed_at = None
        todo_obj.save()
        response = HttpResponse('')
        return _set_todo_triggers(response, has_client=bool(todo_obj.client_id), close=True)
    # If form invalid, re-render drawer with errors
    return render(request, 'todos/partials/todo_detail_drawer.html', {
        'todo': todo,
        'form': form,
    })


@login_required
@require_permission('access_todos')
@require_POST
def todo_toggle(request, pk):
    """Toggle completed status, sets completed_at. Returns updated todo item partial."""
    with transaction.atomic():
        todo = get_object_or_404(
            Todo.objects.select_for_update(), pk=pk, owner=request.user
        )
        todo.is_completed = not todo.is_completed
        todo.completed_at = timezone.now() if todo.is_completed else None
        todo.save(update_fields=['is_completed', 'completed_at'])
    response = render(request, 'todos/partials/todo_item.html', {
        'todo': todo,
        'today': timezone.now().date(),
    })
    return _set_todo_triggers(response, has_client=bool(todo.client_id))


@login_required
@require_permission('access_todos')
@require_POST
def todo_delete(request, pk):
    """Delete to-do. Returns HTMX response."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    has_client = bool(todo.client_id)
    todo.delete()
    response = HttpResponse('')
    return _set_todo_triggers(response, has_client=has_client, close=True)


@login_required
@require_permission('access_todos')
@require_permission('access_clients')
def client_todo_list(request, pk):
    """Client's to-dos (HTMX partial)."""
    client = get_object_or_404(Client, pk=pk)
    todos_qs = Todo.objects.filter(owner=request.user, client=client)

    # Filter by show_completed param (default False to hide completed)
    show_completed = request.GET.get('show_completed', '').lower() == 'true'
    if not show_completed:
        todos_qs = todos_qs.filter(is_completed=False)

    return render(request, 'todos/partials/todo_list.html', {
        'todos': todos_qs,
        'client': client,
        'show_completed': show_completed,
        'today': timezone.now().date(),
    })


@login_required
@require_permission('access_todos')
@require_permission('access_clients')
def client_todo_create(request, pk):
    """Create client to-do (drawer). Pre-fills client field."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        form = TodoForm(request.POST, user=request.user)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.owner = request.user
            todo.client = client
            todo.save()
            response = HttpResponse('')
            return _set_todo_triggers(response, has_client=True, close=True)
        # If form invalid, re-render drawer with errors
        return render(request, 'todos/partials/todo_create_drawer.html', {
            'form': form,
            'client': client,
        })

    form = TodoForm(initial={'client': client}, user=request.user)
    return render(request, 'todos/partials/todo_create_drawer.html', {
        'form': form,
        'client': client,
    })
