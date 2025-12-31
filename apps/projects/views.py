import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .forms import ProjectForm, StatusForm, LabelForm
from .models import Project, Status
from apps.clients.models import Client
from apps.tasks.models import Label

PROJECTS_PER_PAGE = 20


@login_required
def project_list(request):
    projects_qs = Project.objects.select_related('client').all().order_by('name')
    client_filter = request.GET.get('client')
    if client_filter:
        projects_qs = projects_qs.filter(client_id=client_filter)

    paginator = Paginator(projects_qs, PROJECTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    clients = Client.objects.all().order_by('name')
    return render(request, 'projects/project_list.html', {
        'projects': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'clients': clients,
        'client_filter': client_filter,
    })


@login_required
def project_create(request):
    initial = {}
    if request.GET.get('client'):
        initial['client'] = request.GET.get('client')

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_board', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)
    return render(request, 'projects/project_form.html', {'form': form})


@login_required
def project_board(request, pk):
    project = get_object_or_404(Project, pk=pk)
    # Return just the board content for HTMX requests
    if request.htmx:
        return render(request, 'projects/partials/kanban_board.html', {'project': project})
    return render(request, 'projects/project_board.html', {'project': project})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return redirect('project_board', pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/project_form.html', {'form': form, 'project': project})


@login_required
@require_POST
def project_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    project = get_object_or_404(Project, pk=pk)
    project.delete()
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = '/projects/'
        return response
    return redirect('project_list')


@login_required
def manage_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = StatusForm(request.POST)
        if form.is_valid():
            status = form.save(commit=False)
            status.project = project
            status.order = project.statuses.count()
            status.save()
            return render(request, 'projects/partials/kanban_column.html', {'status': status, 'project': project})
    return render(request, 'projects/manage_statuses.html', {'project': project})


@login_required
@require_POST
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)

    try:
        data = json.loads(request.body)
        order = data.get('order', [])
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    if not isinstance(order, list):
        return HttpResponse('order must be a list', status=400)

    for i, status_id in enumerate(order):
        Status.objects.filter(pk=status_id, project=project).update(order=i)
    return HttpResponse(status=204)


@login_required
def project_settings(request, pk):
    """Unified project settings page with statuses and labels."""
    project = get_object_or_404(Project, pk=pk)
    status_form = StatusForm()
    label_form = LabelForm()
    return render(request, 'projects/project_settings.html', {
        'project': project,
        'status_form': status_form,
        'label_form': label_form,
    })


@login_required
@require_POST
def label_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = LabelForm(request.POST)
    if form.is_valid():
        label = form.save(commit=False)
        label.project = project
        label.save()
        return render(request, 'projects/partials/label_item.html', {'label': label, 'project': project})
    return HttpResponse(status=400)


@login_required
@require_POST
def label_delete(request, pk, label_pk):
    project = get_object_or_404(Project, pk=pk)
    label = get_object_or_404(Label, pk=label_pk, project=project)
    label.delete()
    return HttpResponse('')


@login_required
@require_POST
def status_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        status = form.save(commit=False)
        status.project = project
        status.order = project.statuses.count()
        status.save()
        return render(request, 'projects/partials/status_item.html', {'status': status, 'project': project})
    return HttpResponse(status=400)


@login_required
@require_POST
def status_delete(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    status = get_object_or_404(Status, pk=status_pk, project=project)

    # Prevent deleting status with tasks
    if status.task_count > 0:
        return HttpResponse('Cannot delete status with tasks', status=400)

    status.delete()
    return HttpResponse('')
