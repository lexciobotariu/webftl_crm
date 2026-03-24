from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from apps.clients.models import Client
from apps.projects.models import Project, can_access_project
from .models import Note, can_view_note, can_create_note, can_modify_note


@login_required
def client_notes_list(request, client_pk):
    """Render notes table for client detail page"""
    client = get_object_or_404(Client, pk=client_pk)

    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    notes = client.note_objects.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    can_create = can_create_note(request.user, client=client)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': client,
        'parent_type': 'client',
        'can_create_note': can_create,
    })


@login_required
def project_notes_list(request, project_pk):
    """Render notes table for project detail page"""
    project = get_object_or_404(Project, pk=project_pk)

    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("Access denied")

    notes = project.note_objects.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    can_create = can_create_note(request.user, project=project)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': project,
        'parent_type': 'project',
        'can_create_note': can_create,
    })


@login_required
def note_create_drawer(request, client_pk=None, project_pk=None):
    """Create new note drawer"""
    parent = None
    parent_type = None

    if client_pk:
        parent = get_object_or_404(Client, pk=client_pk)
        parent_type = 'client'
        if not request.user.is_admin:
            return HttpResponseForbidden("Admin access required")
    elif project_pk:
        parent = get_object_or_404(Project, pk=project_pk)
        parent_type = 'project'
        if not can_create_note(request.user, project=parent):
            return HttpResponseForbidden("Access denied")

    if request.method == 'POST':
        note = Note(
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            is_private=request.POST.get('is_private') == 'on',
            created_by=request.user,
            modified_by=request.user
        )

        if parent_type == 'client':
            note.client = parent
        else:
            note.project = parent

        note.save()

        # Return updated list partial
        notes = parent.note_objects.select_related('created_by', 'modified_by').all()
        notes = [n for n in notes if can_view_note(request.user, n)]

        can_create = can_create_note(
            request.user,
            client=parent if parent_type == 'client' else None,
            project=parent if parent_type == 'project' else None
        )

        response = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': parent_type,
            'can_create_note': can_create,
        })
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'notes/partials/note_create_drawer.html', {
        'parent': parent,
        'parent_type': parent_type
    })


@login_required
def note_detail_drawer(request, pk):
    """Read-only note view"""
    note = get_object_or_404(Note.objects.select_related('created_by', 'modified_by'), pk=pk)

    if not can_view_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    return render(request, 'notes/partials/note_detail_drawer.html', {
        'note': note,
        'can_modify': can_modify_note(request.user, note)
    })


@login_required
def note_edit_drawer(request, pk):
    """Edit existing note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    if request.method == 'POST':
        note.title = request.POST.get('title')
        note.description = request.POST.get('description', '')
        note.is_private = request.POST.get('is_private') == 'on'
        note.modified_by = request.user
        note.save()

        # Return to read-only view
        response = render(request, 'notes/partials/note_detail_drawer.html', {
            'note': note,
            'can_modify': True
        })

        # Also update the list
        parent = note.client or note.project
        notes = parent.note_objects.select_related('created_by', 'modified_by').all()
        notes = [n for n in notes if can_view_note(request.user, n)]

        parent_type = 'client' if note.client else 'project'
        can_create = can_create_note(
            request.user,
            client=parent if parent_type == 'client' else None,
            project=parent if parent_type == 'project' else None
        )

        list_html = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': parent_type,
            'can_create_note': can_create,
        }).content.decode()

        # Use out-of-band swap to update both drawer and list
        response['HX-Trigger'] = 'noteUpdated'
        return HttpResponse(
            response.content.decode() +
            f'<div id="notes-list" hx-swap-oob="true">{list_html}</div>'
        )

    return render(request, 'notes/partials/note_edit_drawer.html', {'note': note})


@login_required
@require_POST
def note_delete(request, pk):
    """Delete a note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    parent = note.client or note.project
    parent_type = 'client' if note.client else 'project'
    note.delete()

    response = HttpResponse('')
    response['HX-Trigger'] = 'notesChanged, closeSlideOver'
    return response
