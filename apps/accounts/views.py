import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .decorators import require_admin, require_permission
from .models import User
from .permissions import PERMISSION_KEYS, PermissionPreset

TEAM_MEMBERS_PER_PAGE = 20


def _lock_active_admins():
    """Lock every active admin row and return them, for last-admin guards.

    ``select_for_update().count()`` does not lock anything — Django drops the
    FOR UPDATE clause on aggregate queries, so two concurrent demotions could
    both read a count of 2 and both succeed. Materialising the rows is what
    actually takes the locks.

    Always call this *before* locking the target user so that concurrent
    transactions take the locks in the same order and cannot deadlock.
    """
    return list(
        User.objects.filter(role='admin', is_active=True)
        .order_by('pk')
        .select_for_update()
    )


@login_required
@require_permission('access_dashboard')
def dashboard(request):
    context = {
        'client_count': 0,
        'project_count': 0,
        'my_task_count': 0,
        'recent_tasks': [],
        'recent_todos': [],
        'todo_count': 0,
    }

    if request.user.has_app_permission('access_clients'):
        from apps.clients.models import Client
        context['client_count'] = Client.objects.count()

    if request.user.has_app_permission('access_projects'):
        from apps.projects.models import Project
        if request.user.is_admin:
            context['project_count'] = Project.objects.count()
        else:
            context['project_count'] = Project.objects.filter(members__user=request.user).count()

    if request.user.has_app_permission('access_tasks'):
        from apps.tasks.models import Task
        context['my_task_count'] = Task.objects.filter(assignee=request.user).active().count()
        context['recent_tasks'] = Task.objects.filter(assignee=request.user).select_related(
            'project', 'status'
        ).order_by('-updated_at')[:5]

    if request.user.has_app_permission('access_todos'):
        from apps.todos.models import Todo
        context['recent_todos'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).select_related('client')[:5]
        context['todo_count'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).count()

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
@require_admin
def user_create(request):
    """Create a team member from inside the app, with an admin-set password.

    Signup is closed and application admins are not necessarily Django staff,
    so the Django admin add-user form is not reachable for them.
    """
    presets = PermissionPreset.objects.all()

    if request.method != 'POST':
        return render(request, 'accounts/partials/user_create_drawer.html', {
            'presets': presets,
        })

    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    role = request.POST.get('role', '').strip()
    preset_id = request.POST.get('preset_id', '').strip()
    password1 = request.POST.get('password1', '')
    password2 = request.POST.get('password2', '')

    if role not in dict(User.ROLE_CHOICES):
        role = 'member'

    errors = {}

    if not name:
        errors['name'] = 'Name is required.'
    if not email:
        errors['email'] = 'Email is required.'
    elif User.objects.filter(email=email).exists():
        errors['email'] = 'This email is already in use.'

    preset = None
    if preset_id:
        preset = (
            PermissionPreset.objects.filter(pk=preset_id).first()
            if preset_id.isdigit()
            else None
        )
        if preset is None:
            errors['preset_id'] = 'Select a valid permission preset.'

    if not password1:
        errors['password1'] = 'Password is required.'
    elif password1 != password2:
        errors['password2'] = 'Passwords do not match.'
    else:
        try:
            validate_password(password1, User(email=email, name=name, role=role))
        except ValidationError as exc:
            errors['password1'] = ' '.join(exc.messages)

    def render_drawer(drawer_errors):
        """Re-render the drawer with the typed values; passwords are not echoed."""
        return render(request, 'accounts/partials/user_create_drawer.html', {
            'presets': presets,
            'errors': drawer_errors,
            'form_data': {
                'name': name,
                'email': email,
                'role': role,
                'preset_id': preset_id,
            },
        })

    if errors:
        return render_drawer(errors)

    try:
        with transaction.atomic():
            User.objects.create_user(
                email=email,
                password=password1,
                name=name,
                role=role,
                permission_preset=preset,
                is_active=True,
            )
    except IntegrityError:
        # Lost the race between the uniqueness pre-check and the insert.
        return render_drawer({'email': 'This email is already in use.'})

    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({
        'closeSlideOver': True,
        'refreshTeamList': True,
    })
    return response


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
@transaction.atomic
def user_update(request, pk):
    """Update a user's name, email, role, and preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    active_admins = _lock_active_admins()
    user_obj = get_object_or_404(User.objects.select_for_update(), pk=pk)
    presets = PermissionPreset.objects.all()

    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    role = request.POST.get('role', '').strip()
    preset_id = request.POST.get('preset_id', '').strip()

    errors = {}

    if not name:
        errors['name'] = 'Name is required.'
    if not email:
        errors['email'] = 'Email is required.'
    elif User.objects.filter(email=email).exclude(pk=pk).exists():
        errors['email'] = 'This email is already in use.'

    if role not in ('admin', 'member'):
        role = user_obj.role

    # Last-admin guard: prevent demoting if last active admin
    if user_obj.role == 'admin' and role == 'member' and len(active_admins) <= 1:
        errors['role'] = 'Cannot demote the last active admin.'

    if errors:
        return render(request, 'accounts/partials/user_detail_drawer.html', {
            'user_obj': user_obj,
            'presets': presets,
            'errors': errors,
            'form_data': {'name': name, 'email': email, 'role': role, 'preset_id': preset_id},
        })

    user_obj.name = name
    user_obj.email = email
    user_obj.role = role

    if preset_id:
        preset = get_object_or_404(PermissionPreset, pk=preset_id)
        user_obj.permission_preset = preset
    else:
        user_obj.permission_preset = None

    try:
        with transaction.atomic():
            user_obj.save()
    except IntegrityError:
        return render(request, 'accounts/partials/user_detail_drawer.html', {
            'user_obj': user_obj,
            'presets': presets,
            'errors': {'email': 'This email is already in use.'},
            'form_data': {'name': name, 'email': email, 'role': role, 'preset_id': preset_id},
        })

    response = render(request, 'accounts/partials/user_row.html', {'user': user_obj})
    response['HX-Retarget'] = f'#user-{user_obj.pk}'
    response['HX-Reswap'] = 'outerHTML'
    response['HX-Trigger'] = 'closeSlideOver'
    return response


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

        try:
            PermissionPreset.objects.create(
                name=name,
                description=description,
                **{key: key in request.POST for key in PERMISSION_KEYS},
            )
        except IntegrityError:
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'error': f'A preset named "{name}" already exists.',
                'form_name': name,
                'form_description': description,
            })

        response = HttpResponse('')
        response['HX-Trigger'] = json.dumps({
            'closeSlideOver': True,
            'refreshPresetList': True,
        })
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
            new_name = request.POST.get('name', '').strip() or preset.name
            if new_name != preset.name and PermissionPreset.objects.filter(name=new_name).exists():
                return render(request, 'accounts/partials/preset_form_drawer.html', {
                    'preset': preset,
                    'error': f'A preset named "{new_name}" already exists.',
                })
            preset.name = new_name
        preset.description = request.POST.get('description', '').strip()
        for key in PERMISSION_KEYS:
            setattr(preset, key, key in request.POST)
        try:
            preset.save()
        except IntegrityError:
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'preset': preset,
                'error': 'A preset with this name already exists.',
            })

        response = HttpResponse('')
        response['HX-Trigger'] = json.dumps({
            'closeSlideOver': True,
            'refreshPresetList': True,
        })
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
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({'refreshPresetList': True})
    return response


@login_required
@require_permission('access_team')
@require_POST
@transaction.atomic
def user_deactivate(request, pk):
    """Toggle a user's active status."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    active_admins = _lock_active_admins()
    user_obj = get_object_or_404(User.objects.select_for_update(), pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot deactivate yourself.', status=400)

    # If deactivating (not reactivating), check last-admin guard
    if user_obj.is_active and user_obj.role == 'admin' and len(active_admins) <= 1:
        return HttpResponse('Cannot deactivate the last active admin.', status=400)

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=['is_active'])

    response = render(request, 'accounts/partials/user_row.html', {'user': user_obj})
    response['HX-Trigger'] = 'closeSlideOver'
    return response



@login_required
@require_permission('access_team')
def user_delete_confirm(request, pk):
    """Return deletion confirmation partial with cascade counts."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot delete yourself.', status=400)

    from apps.notes.models import Note
    from apps.projects.models import ProjectMember
    from apps.salaries.models import EmployeeSalary, Payment, SalaryMonth
    from apps.tasks.models import Attachment, Task, TaskActivity
    from apps.todos.models import Todo

    counts = {
        'todos': Todo.objects.filter(owner=user_obj).count(),
        'notes': Note.objects.filter(Q(created_by=user_obj) | Q(modified_by=user_obj)).count(),
        'comments': TaskActivity.objects.filter(user=user_obj, activity_type='comment').count(),
        'attachments': Attachment.objects.filter(uploaded_by=user_obj).count(),
        'project_memberships': ProjectMember.objects.filter(user=user_obj).count(),
        'tasks_unassigned': Task.objects.filter(assignee=user_obj).count(),
    }

    try:
        salary = EmployeeSalary.objects.get(user=user_obj)
        salary_months = SalaryMonth.objects.filter(employee_salary=salary)
        counts['salary'] = True
        counts['salary_months'] = salary_months.count()
        counts['payments'] = Payment.objects.filter(salary_month__in=salary_months).count()
    except EmployeeSalary.DoesNotExist:
        counts['salary'] = False
        counts['salary_months'] = 0
        counts['payments'] = 0

    counts['has_data'] = any([
        counts['todos'], counts['notes'], counts['comments'],
        counts['attachments'], counts['project_memberships'],
        counts['salary'], counts['tasks_unassigned'],
    ])

    return render(request, 'accounts/partials/user_delete_confirm.html', {
        'user_obj': user_obj,
        'counts': counts,
    })


@login_required
@require_permission('access_team')
@require_POST
@transaction.atomic
def user_delete(request, pk):
    """Permanently delete a user and all associated data."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    active_admins = _lock_active_admins()
    user_obj = get_object_or_404(User.objects.select_for_update(), pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot delete yourself.', status=400)

    if user_obj.role == 'admin' and user_obj.is_active and len(active_admins) <= 1:
        return HttpResponse('Cannot delete the last active admin.', status=400)

    from apps.salaries.models import EmployeeSalary
    if EmployeeSalary.objects.filter(user=user_obj).exists():
        return HttpResponse('Cannot delete user with salary records.', status=400)

    user_obj.delete()
    return HttpResponse('')
