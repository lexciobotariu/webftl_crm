from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .decorators import require_permission
from .models import User

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
    users_qs = User.objects.all().order_by('name')

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
@require_POST
def toggle_role(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user = get_object_or_404(User, pk=pk)
    if user != request.user:
        user.role = 'member' if user.role == 'admin' else 'admin'
        user.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user})
