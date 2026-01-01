from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clients.models import Client
from .forms import TodoForm
from .models import Todo


@login_required
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
    })


@login_required
def todo_create(request):
    """Create personal to-do (drawer). GET renders form, POST creates todo."""
    if request.method == 'POST':
        form = TodoForm(request.POST)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.owner = request.user
            todo.save()
            # Return the new todo item and close drawer
            response = render(request, 'todos/partials/todo_item.html', {'todo': todo})
            response['HX-Trigger'] = 'closeSlideOver'
            return response
        # If form invalid, re-render drawer with errors
        return render(request, 'todos/partials/todo_create_drawer.html', {'form': form})

    form = TodoForm()
    return render(request, 'todos/partials/todo_create_drawer.html', {'form': form})


@login_required
def todo_detail(request, pk):
    """View/edit to-do (drawer)."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    form = TodoForm(instance=todo)
    return render(request, 'todos/partials/todo_detail_drawer.html', {
        'todo': todo,
        'form': form,
    })


@login_required
@require_POST
def todo_edit(request, pk):
    """Update to-do fields. Returns HTMX response."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    form = TodoForm(request.POST, instance=todo)
    if form.is_valid():
        form.save()
        # Return updated todo item and close drawer
        response = render(request, 'todos/partials/todo_item.html', {'todo': todo})
        response['HX-Trigger'] = 'closeSlideOver'
        return response
    # If form invalid, re-render drawer with errors
    return render(request, 'todos/partials/todo_detail_drawer.html', {
        'todo': todo,
        'form': form,
    })


@login_required
@require_POST
def todo_toggle(request, pk):
    """Toggle completed status, sets completed_at. Returns updated todo item partial."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    todo.is_completed = not todo.is_completed
    todo.completed_at = timezone.now() if todo.is_completed else None
    todo.save()
    return render(request, 'todos/partials/todo_item.html', {'todo': todo})


@login_required
@require_POST
def todo_delete(request, pk):
    """Delete to-do. Returns HTMX response."""
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    todo.delete()
    return HttpResponse('')


@login_required
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
    })


@login_required
def client_todo_create(request, pk):
    """Create client to-do (drawer). Pre-fills client field."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        form = TodoForm(request.POST)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.owner = request.user
            todo.client = client
            todo.save()
            # Return the new todo item and close drawer
            response = render(request, 'todos/partials/todo_item.html', {'todo': todo})
            response['HX-Trigger'] = 'closeSlideOver'
            return response
        # If form invalid, re-render drawer with errors
        return render(request, 'todos/partials/todo_create_drawer.html', {
            'form': form,
            'client': client,
        })

    form = TodoForm(initial={'client': client})
    return render(request, 'todos/partials/todo_create_drawer.html', {
        'form': form,
        'client': client,
    })
