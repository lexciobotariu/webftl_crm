from pathlib import Path


def version(request):
    """Make app version available to all templates."""
    version_file = Path(__file__).resolve().parent.parent / 'VERSION'
    try:
        return {'app_version': version_file.read_text().strip()}
    except FileNotFoundError:
        return {'app_version': 'dev'}


def permissions(request):
    """Make user's permission map and running timer available to all templates.

    Authenticated page renders also close timers that have been open for
    12 hours. There is no job queue; this is one of the two places that
    update runs (the other is the time views, plus a management command).
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'perms_map': {}}

    from apps.accounts.permissions import PERMISSION_KEYS
    from apps.tasks.models import TimeEntry
    from apps.tasks.services import close_expired_timers

    close_expired_timers()
    running_timer = (
        TimeEntry.objects.filter(user=request.user, ended_at__isnull=True)
        .select_related('task', 'task__project')
        .first()
    )
    return {
        'perms_map': {
            key: request.user.has_app_permission(key)
            for key in PERMISSION_KEYS
        },
        'running_timer': running_timer,
    }
