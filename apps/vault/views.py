"""The client's Vault tab: list, add, edit, delete, and show or copy a secret (logged)."""
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission

from .forms import VaultEntryForm
from .models import VaultAccess, VaultEntry

HISTORY = 10


def _client_or_404(user, pk):
    from apps.clients.views import _visible_client_or_404

    return _visible_client_or_404(user, pk)


def _entry_or_404(user, pk):
    entry = get_object_or_404(VaultEntry.objects.select_related('client'), pk=pk)
    _client_or_404(user, entry.client_id)
    return entry


def client_tab_context(client):
    """What the client page's Vault tab shows."""
    entries = list(client.vault_entries.all())
    history = {}
    for access in VaultAccess.objects.filter(entry__client=client).select_related('user'):
        items = history.setdefault(access.entry_id, [])
        if len(items) < HISTORY:
            items.append(access)
    return {'vault_rows': [{'entry': entry, 'history': history.get(entry.pk, [])} for entry in entries]}


def _list(request, client):
    return render(request, 'vault/partials/entries.html', {'client': client, **client_tab_context(client)})


def _changed(message):
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({
        'closeSlideOver': True, 'vaultChanged': {'target': 'body'},
        'infoToast': {'target': 'body', 'message': message},
    })
    return response


@login_required
@require_permission('access_vault')
def vault_list(request, client_pk):
    return _list(request, _client_or_404(request.user, client_pk))


@login_required
@require_permission('access_vault')
def vault_create(request, client_pk):
    client = _client_or_404(request.user, client_pk)
    if request.method == 'POST':
        form = VaultEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.client = client
            entry.created_by = entry.updated_by = request.user
            entry.save()
            return _changed(f'Saved in the vault: {entry.title}')
    else:
        form = VaultEntryForm(initial={'kind': request.GET.get('kind') or VaultEntry.LOGIN})
    return render(request, 'vault/partials/entry_drawer.html', {'form': form, 'client': client, 'entry': None})


@login_required
@require_permission('access_vault')
def vault_edit(request, pk):
    entry = _entry_or_404(request.user, pk)
    if request.method == 'POST':
        form = VaultEntryForm(request.POST, instance=entry)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.updated_by = request.user
            entry.save()
            return _changed(f'Saved: {entry.title}')
    else:
        form = VaultEntryForm(instance=entry)
        if entry.has_secret:
            # The form holds the password and notes, so opening it counts as showing them.
            VaultAccess.objects.create(entry=entry, user=request.user, action=VaultAccess.SHOW)
    response = render(request, 'vault/partials/entry_drawer.html', {'form': form, 'client': entry.client, 'entry': entry})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_permission('access_vault')
@require_POST
def vault_delete(request, pk):
    entry = _entry_or_404(request.user, pk)
    title = entry.title
    entry.delete()
    return _changed(f'Deleted from the vault: {title}')


@login_required
@require_permission('access_vault')
def vault_reveal(request, pk):
    """The entry's password and notes, shown only when asked for, and logged."""
    entry = _entry_or_404(request.user, pk)
    VaultAccess.objects.create(entry=entry, user=request.user, action=VaultAccess.SHOW)
    response = render(request, 'vault/partials/secret.html', {'entry': entry})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_permission('access_vault')
@require_POST
def vault_copy(request, pk):
    """The password alone, as text, for the Copy button. Logged."""
    entry = _entry_or_404(request.user, pk)
    VaultAccess.objects.create(entry=entry, user=request.user, action=VaultAccess.COPY)
    response = HttpResponse(entry.password, content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'no-store'
    return response
