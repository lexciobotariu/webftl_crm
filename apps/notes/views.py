import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import Client
from apps.projects.models import Project, can_access_project

from .forms import NoteForm
from .models import Note, can_create_note, can_modify_note, can_view_note, notes_visible_to_user


def _note_triggers_response(*, close=False):
    """Return empty HTMX response with notes list refresh triggers."""
    triggers = {'notesChanged': True}
    if close:
        triggers['closeSlideOver'] = True
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps(triggers)
    return response


@login_required
@require_permission('access_notes')
def client_notes_list(request, client_pk):
    """Render notes table for client detail page"""
    client = get_object_or_404(Client, pk=client_pk)

    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    notes = notes_visible_to_user(
        request.user,
        client.note_objects.select_related('created_by', 'modified_by')
    )

    can_create = can_create_note(request.user, client=client)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': client,
        'parent_type': 'client',
        'can_create_note': can_create,
    })


@login_required
@require_permission('access_notes')
def project_notes_list(request, project_pk):
    """Render notes table for project detail page"""
    project = get_object_or_404(Project, pk=project_pk)

    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("Access denied")

    notes = notes_visible_to_user(
        request.user,
        project.note_objects.select_related('created_by', 'modified_by')
    )

    can_create = can_create_note(request.user, project=project)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': project,
        'parent_type': 'project',
        'can_create_note': can_create,
    })


@login_required
@require_permission('access_notes')
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

    parent_kwargs = {'client': parent} if parent_type == 'client' else {'project': parent}

    if request.method == 'POST':
        form = NoteForm(request.POST, **parent_kwargs)
        if form.is_valid():
            note = form.save(commit=False)
            note.created_by = request.user
            note.modified_by = request.user
            note.save()
            return _note_triggers_response(close=True)

        return render(request, 'notes/partials/note_create_drawer.html', {
            'parent': parent,
            'parent_type': parent_type,
            'form': form,
        })

    return render(request, 'notes/partials/note_create_drawer.html', {
        'parent': parent,
        'parent_type': parent_type,
        'form': NoteForm(**parent_kwargs),
    })


@login_required
@require_permission('access_notes')
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
@require_permission('access_notes')
def note_edit_drawer(request, pk):
    """Edit existing note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    if request.method == 'POST':
        form = NoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save(commit=False)
            note.modified_by = request.user
            note.save()
            return _note_triggers_response(close=True)

        return render(request, 'notes/partials/note_edit_drawer.html', {
            'note': note,
            'form': form,
        })

    return render(request, 'notes/partials/note_edit_drawer.html', {
        'note': note,
        'form': NoteForm(instance=note),
    })


@login_required
@require_permission('access_notes')
@require_POST
def note_delete(request, pk):
    """Delete a note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    note.delete()
    return _note_triggers_response(close=True)
