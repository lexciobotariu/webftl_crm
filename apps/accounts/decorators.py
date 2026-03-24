from functools import wraps

from django.http import HttpResponseForbidden


def require_permission(permission_key):
    """
    View decorator that checks the user's permission preset for the given key.
    Admins always pass. Returns 403 if denied.
    Assumes @login_required is applied separately.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.has_app_permission(permission_key):
                return HttpResponseForbidden("You don't have access to this section")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
