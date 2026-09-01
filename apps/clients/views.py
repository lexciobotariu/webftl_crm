import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission

from .forms import ClientDrawerForm, ClientForm
from .models import Client

CLIENTS_PER_PAGE = 20


@login_required
@require_permission('access_clients')
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
@require_permission('access_clients')
def client_create(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to create clients")

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form})


@login_required
@require_permission('access_clients')
def client_create_drawer(request):
    """Create client via drawer (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to create clients")

    if request.method == 'POST':
        form = ClientDrawerForm(request.POST)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            response['HX-Trigger'] = json.dumps({
                'closeSlideOver': True,
                'refreshClientList': True,
            })
            return response
        return render(request, 'clients/partials/create_drawer.html', {'form': form})

    return render(request, 'clients/partials/create_drawer.html', {'form': ClientDrawerForm()})


@login_required
@require_permission('access_clients')
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

    from apps.notes.models import notes_visible_to_user
    from apps.todos.models import Todo
    todos_qs = Todo.objects.filter(owner=request.user, client=client, is_completed=False).select_related('client')
    todo_count = todos_qs.count()

    notes_count = notes_visible_to_user(request.user, client.note_objects.all()).count()

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
@require_permission('access_clients')
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
@require_permission('access_clients')
def client_edit_drawer(request, pk):
    """Edit client profile via drawer (HTMX)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required to edit clients")

    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        form = ClientDrawerForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            response['HX-Trigger'] = json.dumps({
                'closeSlideOver': True,
                'updateClientName': True,
                'profileChanged': True,
            })
            return response
        return render(request, 'clients/partials/edit_drawer.html', {'client': client, 'form': form})

    return render(request, 'clients/partials/edit_drawer.html', {
        'client': client,
        'form': ClientDrawerForm(instance=client),
    })


@login_required
@require_permission('access_clients')
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

        if not name:
            return render(request, 'clients/partials/project_create_drawer.html', {
                'client': client,
                'error': 'Project name is required.',
                'form_name': name,
                'form_description': description,
                'form_github_repo_url': github_repo_url,
            })

        project = Project.objects.create(
            client=client,
            name=name,
            description=description,
            github_repo_url=github_repo_url,
        )

        from django.urls import reverse
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('project_board', args=[project.pk])
        return response

    return render(request, 'clients/partials/project_create_drawer.html', {'client': client})


@login_required
@require_permission('access_clients')
def client_profile_notes(request, pk):
    """Return unified notes table for client profile (client + project notes)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    client = get_object_or_404(Client, pk=pk)

    from apps.notes.models import Note, notes_visible_to_user

    # Get client notes
    client_notes = list(
        notes_visible_to_user(
            request.user,
            Note.objects.filter(client=client).select_related('created_by', 'modified_by')
        )
    )

    # Get notes from all client's projects
    project_ids = client.projects.values_list('pk', flat=True)
    project_notes = list(
        notes_visible_to_user(
            request.user,
            Note.objects.filter(project_id__in=project_ids).select_related(
                'created_by', 'modified_by', 'project'
            )
        )
    )

    # Merge, sort by most recent
    all_notes = client_notes + project_notes
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
@require_permission('access_clients')
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
