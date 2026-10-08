import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.projects.models import visible_projects
from apps.projects.services import with_task_counts

from .forms import ClientContactForm, ClientDrawerForm, ClientForm
from .models import Client, ClientContact, visible_clients

CLIENTS_PER_PAGE = 20


def _visible_projects(user, client):
    """Projects on this client from the same queryset as the project list."""
    return visible_projects(user).filter(client=client)


def _visible_client_or_404(user, pk):
    """A client outside ``visible_clients`` is a 404, including a known address."""
    return get_object_or_404(visible_clients(user), pk=pk)


def _save_new_client(form, user):
    client = form.save(commit=False)
    client.created_by = user
    client.save()
    return client


@login_required
@require_permission('access_clients')
def client_list(request):
    """Active clients by default; ``?archived=1`` lists the archived ones instead."""
    visible = visible_clients(request.user)
    show_archived = request.GET.get('archived') == '1'
    query = request.GET.get('q', '').strip()[:100]
    if query:
        # The client's name, or the name or email of one of its contacts, as in the search palette.
        matching = Q(name__icontains=query) | Q(contacts__name__icontains=query) | Q(contacts__email__icontains=query)
        visible = visible.filter(pk__in=visible.filter(matching).values('pk'))
    clients_qs = visible.filter(archived_at__isnull=not show_archived)
    clients_qs = clients_qs.annotate(num_projects=Count('projects', distinct=True)).order_by('name')
    paginator = Paginator(clients_qs, CLIENTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'clients/client_list.html', {
        'clients': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'show_archived': show_archived,
        'query': query,
        'archived_count': None if show_archived else visible.filter(archived_at__isnull=False).count(),
    })


@login_required
@require_permission('access_clients')
def client_create(request):
    if not request.user.has_app_permission('clients_create'):
        return HttpResponseForbidden("Permission required to create clients")

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = _save_new_client(form, request.user)
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form})


@login_required
@require_permission('access_clients')
def client_create_drawer(request):
    """Create client via drawer (HTMX)."""
    if not request.user.has_app_permission('clients_create'):
        return HttpResponseForbidden("Permission required to create clients")

    if request.method == 'POST':
        form = ClientDrawerForm(request.POST)
        if form.is_valid():
            _save_new_client(form, request.user)
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
    client = _visible_client_or_404(request.user, pk)

    # Determine active tab from URL
    url_name = request.resolver_match.url_name
    tab_mapping = {
        'client_detail_profile': 'profile',
        'client_detail_todos': 'todos',
        'client_detail_projects': 'projects',
        'client_detail_notes': 'notes',
        'client_detail_invoices': 'invoices',
    }
    active_tab = tab_mapping.get(url_name, 'overview')
    if active_tab == 'invoices' and not request.user.has_app_permission('access_invoices'):
        return HttpResponseForbidden("You don't have access to this section")

    from apps.invoices.models import visible_invoices
    from apps.notes.models import notes_visible_to_user
    from apps.todos.models import Todo
    todos_qs = Todo.objects.filter(owner=request.user, client=client, is_completed=False).select_related('client')
    todo_count = todos_qs.count()

    notes_count = notes_visible_to_user(request.user, client.note_objects.all()).count()
    projects = with_task_counts(_visible_projects(request.user, client), request.user)
    client_invoices = []
    invoice_count = 0
    if request.user.has_app_permission('access_invoices'):
        client_invoices = visible_invoices(request.user).filter(client=client)
        invoice_count = client_invoices.count()

    overview = None
    if active_tab == 'overview':
        from .overview import client_overview
        overview = client_overview(request.user, client)

    return render(request, 'clients/client_detail.html', {
        'client': client,
        'overview': overview,
        'projects': projects,
        'project_count': projects.count(),
        'todo_count': todo_count,
        'todos': todos_qs,
        'notes_count': notes_count,
        'client_invoices': client_invoices,
        'invoice_count': invoice_count,
        # Delete is offered only where it can succeed: invoices and logged time protect a client.
        'can_delete': not client_delete_blocker(client),
        'show_completed': False,
        'today': timezone.localdate(),
        'active_tab': active_tab,
    })


@login_required
@require_permission('access_clients')
def client_edit(request, pk):
    client = _visible_client_or_404(request.user, pk)
    if not request.user.has_app_permission('clients_edit'):
        return HttpResponseForbidden("Permission required to edit clients")
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
    client = _visible_client_or_404(request.user, pk)
    if not request.user.has_app_permission('clients_edit'):
        return HttpResponseForbidden("Permission required to edit clients")

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
    """Create a new project for this client via drawer (HTMX).

    Same visibility as the client page and the same validation as
    ``ProjectForm``. An archived client takes no new projects.
    """
    if not request.user.has_app_permission('projects_create'):
        return HttpResponseForbidden("You can't create projects")

    from apps.projects.forms import ClientProjectForm
    from apps.projects.models import ProjectAccess

    client = _visible_client_or_404(request.user, pk)
    if client.is_archived:
        return HttpResponse('This client is archived. Restore it to add a project.', status=400)

    if request.method == 'POST':
        form = ClientProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.client = client
            project.save()
            ProjectAccess.objects.create(project=project, user=request.user)
            response = HttpResponse('')
            response['HX-Redirect'] = reverse('project_tasks', args=[project.pk])
            return response
        return render(request, 'projects/partials/project_create_drawer.html', {
            'client': client,
            'error': next(iter(form.errors.values()))[0],
            'form_name': form.data.get('name', ''),
            'form_description': form.data.get('description', ''),
            'form_github_repo_url': form.data.get('github_repo_url', ''),
            'form_start_date': form.data.get('start_date', ''),
            'form_deadline': form.data.get('deadline', ''),
        })

    return render(request, 'projects/partials/project_create_drawer.html', {'client': client})


@login_required
@require_permission('access_clients')
def client_profile_notes(request, pk):
    """Unified notes table for the client profile (this client and its projects).

    The rows are ``notes_visible_to_user``, the same rules as the notes list
    and opening a note by id.
    """
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
    """Delete a client that was never invoiced. One with invoices is archived instead."""
    # Visibility first: a hidden client is 404, not 403, even when the caller knows the address.
    client = _visible_client_or_404(request.user, pk)
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    blocker = client_delete_blocker(client)
    if blocker:
        return HttpResponse(blocker, status=400)
    try:
        client.delete()
    except ProtectedError:
        # An invoice or logged time arrived after the check.
        return HttpResponse(client_delete_blocker(client) or 'This client cannot be deleted. Archive it instead.', status=400)
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = '/clients/'
        return response
    return redirect('client_list')


def client_delete_blocker(client):
    """Why ``client`` cannot be deleted, or ''. Such a client is archived instead."""
    from apps.tasks.models import TimeEntry

    if client.invoices.exists():
        return 'This client has invoices, so it cannot be deleted. Archive it instead.'
    if TimeEntry.objects.filter(task__project__client=client).exists():
        return 'This client has logged time on its projects, so it cannot be deleted. Archive it instead.'
    return ''


@login_required
@require_permission('access_clients')
@require_POST
def client_archive(request, pk):
    """Archive or restore (``restore=1``) a client. Needs ``clients_edit``; nothing is deleted."""
    client = _visible_client_or_404(request.user, pk)
    if not request.user.has_app_permission('clients_edit'):
        return HttpResponseForbidden("Permission required to edit clients")
    client.archived_at = None if request.POST.get('restore') == '1' else timezone.now()
    client.save(update_fields=['archived_at', 'updated_at'])
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('client_detail', args=[client.pk])
        return response
    return redirect('client_detail', pk=client.pk)


def _editable_client_or_error(user, pk):
    """The client for a contact change, or the response refusing it."""
    client = _visible_client_or_404(user, pk)
    if not user.has_app_permission('clients_edit'):
        return client, HttpResponseForbidden("Permission required to edit clients")
    return client, None


def _contacts_changed():
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({'closeSlideOver': True, 'profileChanged': True})
    return response


@transaction.atomic
def save_contact(form, client):
    """Save a contact; marking it primary or billing takes that mark from the others."""
    contact = form.save(commit=False)
    contact.client = client
    others = client.contacts.exclude(pk=contact.pk)
    if contact.is_primary:
        others.filter(is_primary=True).update(is_primary=False)
    if contact.is_billing:
        others.filter(is_billing=True).update(is_billing=False)
    contact.save()
    return contact


def _contact_drawer(request, client, form, contact=None):
    return render(request, 'clients/partials/contact_drawer.html', {
        'client': client, 'form': form, 'contact': contact,
    })


@login_required
@require_permission('access_clients')
def client_contact_create(request, pk):
    client, refused = _editable_client_or_error(request.user, pk)
    if refused:
        return refused
    if request.method == 'POST':
        form = ClientContactForm(request.POST)
        if form.is_valid():
            save_contact(form, client)
            return _contacts_changed()
        return _contact_drawer(request, client, form)
    # The first contact starts as the primary one.
    return _contact_drawer(request, client, ClientContactForm(initial={'is_primary': not client.contacts.exists()}))


@login_required
@require_permission('access_clients')
def client_contact_edit(request, pk, contact_pk):
    client, refused = _editable_client_or_error(request.user, pk)
    if refused:
        return refused
    contact = get_object_or_404(ClientContact, pk=contact_pk, client=client)
    if request.method == 'POST':
        form = ClientContactForm(request.POST, instance=contact)
        if form.is_valid():
            save_contact(form, client)
            return _contacts_changed()
        return _contact_drawer(request, client, form, contact)
    return _contact_drawer(request, client, ClientContactForm(instance=contact), contact)


@login_required
@require_permission('access_clients')
@require_POST
def client_contact_delete(request, pk, contact_pk):
    client, refused = _editable_client_or_error(request.user, pk)
    if refused:
        return refused
    get_object_or_404(ClientContact, pk=contact_pk, client=client).delete()
    return _contacts_changed()
