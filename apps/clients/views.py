from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClientForm
from .models import Client

CLIENTS_PER_PAGE = 20


@login_required
def client_list(request):
    clients_qs = Client.objects.all().order_by('name')
    paginator = Paginator(clients_qs, CLIENTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'clients/client_list.html', {
        'clients': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
    })


@login_required
def client_create(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to create clients")

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            if request.htmx:
                return render(request, 'clients/partials/client_card.html', {'client': client})
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form})


@login_required
def client_create_drawer(request):
    """Create client via drawer (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to create clients")

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            # Return the new client row and close drawer
            response = render(request, 'clients/partials/client_row.html', {'client': client})
            response['HX-Trigger'] = 'closeSlideOver'
            return response
        # If form invalid, re-render drawer with errors
        return render(request, 'clients/partials/create_drawer.html', {'form': form})

    return render(request, 'clients/partials/create_drawer.html')


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)

    # Determine active tab from URL
    url_name = request.resolver_match.url_name
    tab_mapping = {
        'client_detail_todos': 'todos',
        'client_detail_projects': 'projects',
        'client_detail_notes': 'notes',
    }
    active_tab = tab_mapping.get(url_name, 'profile')

    from apps.todos.models import Todo
    from apps.notes.models import Note, can_view_note
    todos_qs = Todo.objects.filter(owner=request.user, client=client, is_completed=False).select_related('client')
    todo_count = todos_qs.count()

    # Get notes count (only notes user can see)
    notes_qs = client.note_objects.all()
    notes_count = sum(1 for note in notes_qs if can_view_note(request.user, note))

    return render(request, 'clients/client_detail.html', {
        'client': client,
        'todo_count': todo_count,
        'todos': todos_qs,
        'notes_count': notes_count,
        'show_completed': False,
        'today': timezone.now().date(),
        'active_tab': active_tab,
    })


@login_required
def client_edit(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to edit clients")

    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'clients/client_form.html', {'form': form, 'client': client})


@login_required
def client_edit_drawer(request, pk):
    """Edit client profile via drawer (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to edit clients")

    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            # Return updated profile content and close drawer
            response = render(request, 'clients/partials/profile_content.html', {'client': client})
            response['HX-Trigger'] = 'closeSlideOver, updateClientName'
            return response
        # If form invalid, re-render drawer with errors
        return render(request, 'clients/partials/edit_drawer.html', {'client': client, 'form': form})

    return render(request, 'clients/partials/edit_drawer.html', {'client': client})


@login_required
def client_edit_notes(request, pk):
    """Edit client notes inline (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to edit clients")

    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        # Limit notes length and use empty string instead of None
        notes = request.POST.get('notes', '')[:10000].strip()
        client.notes = notes if notes else ''
        client.save()
        return render(request, 'clients/partials/notes_display.html', {'client': client})

    return render(request, 'clients/partials/notes_edit.html', {'client': client})


@login_required
def client_create_project(request, pk):
    """Create a new project for this client via drawer (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to create projects")

    from apps.projects.models import Project

    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        github_repo_url = request.POST.get('github_repo_url', '').strip()

        if name:
            # Note: Default statuses are created automatically in Project.save()
            project = Project.objects.create(
                client=client,
                name=name,
                description=description,
                github_repo_url=github_repo_url,
            )

            # Redirect to the new project board
            from django.urls import reverse
            response = HttpResponse('')
            response['HX-Redirect'] = reverse('project_board', args=[project.pk])
            return response

    return render(request, 'clients/partials/project_create_drawer.html', {'client': client})


@login_required
def client_profile_notes(request, pk):
    """Return unified notes table for client profile (client + project notes)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    client = get_object_or_404(Client, pk=pk)

    from apps.notes.models import Note, can_view_note

    # Get client notes
    client_notes = list(
        Note.objects.filter(client=client)
        .select_related('created_by', 'modified_by')
    )

    # Get notes from all client's projects
    project_ids = client.projects.values_list('pk', flat=True)
    project_notes = list(
        Note.objects.filter(project_id__in=project_ids)
        .select_related('created_by', 'modified_by', 'project')
    )

    # Merge, filter visibility, sort by most recent
    all_notes = [n for n in client_notes + project_notes if can_view_note(request.user, n)]
    all_notes.sort(key=lambda n: n.updated_at, reverse=True)

    # Annotate each note with its type label
    for note in all_notes:
        if note.client_id:
            note.type_label = 'Client'
        else:
            note.type_label = 'Project'
            note.type_name = note.project.name

    return render(request, 'clients/partials/profile_notes_table.html', {
        'notes': all_notes,
        'client': client,
    })


@login_required
@require_POST
def client_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    client = get_object_or_404(Client, pk=pk)
    client.delete()
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = '/clients/'
        return response
    return redirect('client_list')
