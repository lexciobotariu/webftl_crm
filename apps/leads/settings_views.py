"""Settings > Leads: the board's statuses and the list of sources. Admins only, like all settings."""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_admin
from apps.crm.views import _render, _saved

from .forms import LeadSourceForm, LeadStatusForm
from .models import LeadSource, LeadStatus


def _statuses_page(request, form=None, error='', edit_form=None, status=200):
    statuses = LeadStatus.objects.annotate(lead_count=Count('leads'))
    return _render(request, 'lead_statuses.html', 'settings_lead_statuses', {
        'statuses': statuses,
        'form': form or LeadStatusForm(initial={'position': statuses.count()}),
        'edit_form': edit_form,
        'status_error': error,
    }, status=status)


@login_required
@require_admin
def settings_lead_statuses(request):
    return _statuses_page(request)


@login_required
@require_admin
@require_POST
def lead_status_add(request):
    form = LeadStatusForm(request.POST)
    if form.is_valid():
        status = form.save()
        _saved(request, f'{status.name} added.')
        return redirect('settings_lead_statuses')
    return _statuses_page(request, form=form, status=400)


@login_required
@require_admin
@require_POST
def lead_status_edit(request, pk):
    status = get_object_or_404(LeadStatus, pk=pk)
    form = LeadStatusForm(request.POST, instance=status, prefix=f's{pk}')
    if form.is_valid():
        form.save()
        _saved(request, f'{status.name} saved.')
        return redirect('settings_lead_statuses')
    return _statuses_page(request, edit_form=form, status=400)


@login_required
@require_admin
@require_POST
def lead_status_delete(request, pk):
    status = get_object_or_404(LeadStatus, pk=pk)
    if status.kind != LeadStatus.OPEN and not LeadStatus.objects.filter(kind=status.kind).exclude(pk=pk).exists():
        return _statuses_page(request, error=f'Keep one {status.get_kind_display()} status.', status=400)
    if not LeadStatus.objects.exclude(pk=pk).filter(kind=LeadStatus.OPEN).exists():
        return _statuses_page(request, error='Keep one Open status: new leads start there.', status=400)
    try:
        status.delete()
    except ProtectedError:
        return _statuses_page(request, error=f'Leads are in {status.name}. Move them first.', status=400)
    _saved(request, f'{status.name} deleted.')
    return redirect('settings_lead_statuses')


def _sources_page(request, form=None, error='', edit_form=None, status=200):
    return _render(request, 'lead_sources.html', 'settings_lead_sources', {
        'sources': LeadSource.objects.annotate(lead_count=Count('leads')),
        'form': form or LeadSourceForm(initial={'position': LeadSource.objects.count()}),
        'edit_form': edit_form,
        'source_error': error,
    }, status=status)


@login_required
@require_admin
def settings_lead_sources(request):
    return _sources_page(request)


@login_required
@require_admin
@require_POST
def lead_source_add(request):
    form = LeadSourceForm(request.POST)
    if form.is_valid():
        source = form.save()
        _saved(request, f'{source.name} added.')
        return redirect('settings_lead_sources')
    return _sources_page(request, form=form, status=400)


@login_required
@require_admin
@require_POST
def lead_source_edit(request, pk):
    source = get_object_or_404(LeadSource, pk=pk)
    form = LeadSourceForm(request.POST, instance=source, prefix=f's{pk}')
    if form.is_valid():
        form.save()
        _saved(request, f'{source.name} saved.')
        return redirect('settings_lead_sources')
    return _sources_page(request, edit_form=form, status=400)


@login_required
@require_admin
@require_POST
def lead_source_delete(request, pk):
    """Leads from a deleted source keep everything else; their source becomes Unknown."""
    source = get_object_or_404(LeadSource, pk=pk)
    source.delete()
    _saved(request, f'{source.name} deleted.')
    return redirect('settings_lead_sources')
