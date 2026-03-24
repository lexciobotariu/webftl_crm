from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .decorators import require_permission
from .models import User
from .permissions import PermissionPreset, PERMISSION_KEYS

TEAM_MEMBERS_PER_PAGE = 20


@login_required
def dashboard(request):
    # Stats will work once models exist, for now use safe defaults
    context = {
        'client_count': 0,
        'project_count': 0,
        'my_task_count': 0,
        'recent_tasks': [],
        'recent_todos': [],
        'todo_count': 0,
    }
    # Try to get real counts if models exist
    try:
        from apps.clients.models import Client
        context['client_count'] = Client.objects.count()
    except (ImportError, Exception):
        pass
    try:
        from apps.projects.models import Project
        context['project_count'] = Project.objects.count()
    except (ImportError, Exception):
        pass
    try:
        from apps.tasks.models import Task
        context['my_task_count'] = Task.objects.filter(assignee=request.user).exclude(status__name='Done').count()
        context['recent_tasks'] = Task.objects.filter(assignee=request.user).select_related('project', 'status').order_by('-updated_at')[:5]
    except (ImportError, Exception):
        pass
    try:
        from apps.todos.models import Todo
        context['recent_todos'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).select_related('client')[:5]
        context['todo_count'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).count()
    except (ImportError, Exception):
        pass
    return render(request, 'accounts/dashboard.html', context)


@login_required
@require_permission('access_team')
def team_list(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    users_qs = User.objects.select_related('permission_preset').order_by('name')

    paginator = Paginator(users_qs, TEAM_MEMBERS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/team_list.html', {
        'users': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
    })


@login_required
@require_permission('access_team')
def user_detail_drawer(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user_obj = get_object_or_404(User, pk=pk)
    presets = PermissionPreset.objects.all()
    return render(request, 'accounts/partials/user_detail_drawer.html', {
        'user_obj': user_obj,
        'presets': presets,
    })


@login_required
@require_permission('access_team')
@require_POST
def update_preset(request, pk):
    """Update a user's permission preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user_obj = get_object_or_404(User, pk=pk)
    preset_id = request.POST.get('preset_id', '').strip()
    if preset_id:
        preset = get_object_or_404(PermissionPreset, pk=preset_id)
        user_obj.permission_preset = preset
    else:
        user_obj.permission_preset = None
    user_obj.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user_obj})


@login_required
@require_permission('access_team')
def preset_list(request):
    """List all permission presets."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    presets = PermissionPreset.objects.annotate(
        user_count=models.Count('users')
    ).order_by('name')
    return render(request, 'accounts/preset_list.html', {
        'presets': presets,
    })


@login_required
@require_permission('access_team')
def preset_create(request):
    """Create a new permission preset via drawer."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'error': 'Name is required.',
            })

        if PermissionPreset.objects.filter(name=name).exists():
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'error': f'A preset named "{name}" already exists.',
                'form_name': name,
                'form_description': description,
            })

        preset = PermissionPreset.objects.create(
            name=name,
            description=description,
            **{key: key in request.POST for key in PERMISSION_KEYS},
        )
        preset.user_count = 0  # For template rendering
        response = render(request, 'accounts/partials/preset_item.html', {'preset': preset})
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'accounts/partials/preset_form_drawer.html', {})


@login_required
@require_permission('access_team')
def preset_edit(request, pk):
    """Edit a permission preset via drawer."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    preset = get_object_or_404(PermissionPreset, pk=pk)

    if request.method == 'POST':
        if not preset.is_system:
            preset.name = request.POST.get('name', '').strip() or preset.name
        preset.description = request.POST.get('description', '').strip()
        for key in PERMISSION_KEYS:
            setattr(preset, key, key in request.POST)
        preset.save()

        from django.db.models import Count
        preset = PermissionPreset.objects.annotate(user_count=Count('users')).get(pk=pk)
        response = render(request, 'accounts/partials/preset_item.html', {'preset': preset})
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'accounts/partials/preset_form_drawer.html', {'preset': preset})


@login_required
@require_permission('access_team')
@require_POST
def preset_delete(request, pk):
    """Delete a permission preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    preset = get_object_or_404(PermissionPreset, pk=pk)

    if preset.is_system:
        return HttpResponse('Cannot delete system presets', status=400)

    if preset.users.exists():
        return HttpResponse('Cannot delete preset with assigned users', status=400)

    preset.delete()
    return HttpResponse('')


@login_required
@require_permission('access_team')
@require_POST
def toggle_role(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user = get_object_or_404(User, pk=pk)
    if user != request.user:
        user.role = 'member' if user.role == 'admin' else 'admin'
        user.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user})
