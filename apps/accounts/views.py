from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .models import User


@login_required
def dashboard(request):
    # Stats will work once models exist, for now use safe defaults
    context = {
        'client_count': 0,
        'project_count': 0,
        'my_task_count': 0,
        'recent_tasks': [],
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
    return render(request, 'accounts/dashboard.html', context)


@login_required
def team_list(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    users = User.objects.all().order_by('name')
    return render(request, 'accounts/team_list.html', {'users': users})


@login_required
@require_POST
def toggle_role(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user = get_object_or_404(User, pk=pk)
    if user != request.user:
        user.role = 'member' if user.role == 'admin' else 'admin'
        user.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user})
