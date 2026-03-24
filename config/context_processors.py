from pathlib import Path


def version(request):
    """Make app version available to all templates."""
    version_file = Path(__file__).resolve().parent.parent / 'VERSION'
    try:
        return {'app_version': version_file.read_text().strip()}
    except FileNotFoundError:
        return {'app_version': 'dev'}


def permissions(request):
    """Make user's permission map available to all templates."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'perms_map': {}}

    from apps.accounts.permissions import PERMISSION_KEYS
    return {
        'perms_map': {
            key: request.user.has_app_permission(key)
            for key in PERMISSION_KEYS
        }
    }
