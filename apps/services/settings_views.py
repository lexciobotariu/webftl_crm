"""Settings > Services > Service types (admins). A type fills in a new service of that kind."""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_admin
from apps.crm.views import _render, _saved

from .forms import ServiceTypeForm
from .models import ServiceType

SECTION = 'settings_service_types'


def _page(request, error='', status=200):
    types = ServiceType.objects.annotate(service_count=Count('services'))
    return _render(request, 'service_types.html', SECTION, {'service_types': types, 'error': error}, status=status)


@login_required
@require_admin
def settings_service_types(request):
    return _page(request)


def _form(request, form, kind=None, status=200):
    return _render(request, 'service_type_form.html', SECTION, {'form': form, 'kind': kind}, status=status)


@login_required
@require_admin
def service_type_add(request):
    if request.method == 'POST':
        form = ServiceTypeForm(request.POST)
        if form.is_valid():
            kind = form.save(commit=False)
            kind.position = (ServiceType.objects.count() or 0) + 1
            kind.save()
            _saved(request, f'{kind.name} added.')
            return redirect(SECTION)
        return _form(request, form, status=400)
    return _form(request, ServiceTypeForm())


@login_required
@require_admin
def service_type_edit(request, pk):
    kind = get_object_or_404(ServiceType, pk=pk)
    if request.method == 'POST':
        form = ServiceTypeForm(request.POST, instance=kind)
        if form.is_valid():
            form.save()
            _saved(request, f'{kind.name} saved.')
            return redirect(SECTION)
        return _form(request, form, kind, status=400)
    return _form(request, ServiceTypeForm(instance=kind), kind)


@login_required
@require_admin
@require_POST
def service_type_delete(request, pk):
    kind = get_object_or_404(ServiceType, pk=pk)
    try:
        kind.delete()
    except ProtectedError:
        return _page(request, error=f'{kind.name} is used by a service, so it stays.', status=400)
    _saved(request, f'{kind.name} deleted.')
    return redirect(SECTION)
