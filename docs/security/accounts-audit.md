# Security Audit: Accounts App

**Date:** 2025-12-31
**Auditor:** Claude Code
**Files Reviewed:** `apps/accounts/models.py`, `apps/accounts/views.py`

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 1 | Open |
| Medium | 1 | Open |
| Low | 1 | Open |

---

## Findings

### CRITICAL: GitHub Token Stored in Plain Text

**Location:** `apps/accounts/models.py:16`

```python
github_token = models.CharField(max_length=255, blank=True)
```

**Risk:** If the database is compromised, all GitHub tokens are exposed in plain text. These tokens can be used to:
- Access private repositories
- Modify code
- Create/delete repositories
- Access organization data

**Recommendation:** Encrypt tokens using `django-fernet-fields` or similar:

```python
from fernet_fields import EncryptedCharField

github_token = EncryptedCharField(max_length=255, blank=True)
```

**Priority:** Fix before production deployment

---

### MEDIUM: No Rate Limiting on toggle_role

**Location:** `apps/accounts/views.py:58-67`

```python
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
```

**Risk:** No protection against:
- Brute-force role toggling attacks
- Automated scripts rapidly changing user roles
- Denial of service for admin operations

**Recommendation:** Add rate limiting using `django-ratelimit`:

```python
from django_ratelimit.decorators import ratelimit

@login_required
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def toggle_role(request, pk):
    ...
```

---

### LOW: Broad Exception Handling

**Location:** `apps/accounts/views.py:22-37`

```python
try:
    from apps.clients.models import Client
    context['client_count'] = Client.objects.count()
except (ImportError, Exception):
    pass
```

**Risk:**
- Silently catches ALL exceptions including security-related ones
- Hides potential bugs and security issues
- Makes debugging difficult

**Recommendation:** Be more specific about exceptions:

```python
try:
    from apps.clients.models import Client
    context['client_count'] = Client.objects.count()
except ImportError:
    pass  # App not installed
except OperationalError:
    pass  # Database not ready
```

---

## Positive Security Observations

1. **Password Handling:** Uses Django's built-in password hashing via `AbstractBaseUser`
2. **Admin Check:** `toggle_role` properly checks `is_admin` before allowing role changes
3. **Self-Protection:** Admin cannot toggle their own role (prevents lockout)
4. **POST Required:** Role toggle requires POST method (CSRF protection)
5. **Login Required:** All views protected with `@login_required`

---

## Next Steps

1. [ ] Implement token encryption before production
2. [ ] Add rate limiting to sensitive endpoints
3. [ ] Replace broad exception handling with specific exceptions
4. [ ] Consider audit logging for role changes
