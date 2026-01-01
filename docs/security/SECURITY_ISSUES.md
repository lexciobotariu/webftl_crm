# Security Issues Summary - WebFTL CRM

**Last Updated:** 2026-01-01
**Total Issues:** 15 (~~4 Critical~~ **0 Critical**, ~~3 High~~ **0 High**, ~~6 Medium~~ **0 Medium**, 2 Low)

> **Status:** All critical, high, and medium priority issues have been fixed.

---

## Quick Reference

| Priority | Issue | Location | Impact | Status |
|----------|-------|----------|--------|--------|
| ~~CRITICAL~~ | ~~GitHub token plain text~~ | ~~accounts/models.py:16~~ | ~~Data breach~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~File upload no validation~~ | ~~tasks/views.py:206~~ | ~~RCE, XSS~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~No client authorization~~ | ~~clients/views.py~~ | ~~Data exposure~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~JSON parsing crash~~ | ~~projects/views.py:106~~ | ~~DoS~~ | ✅ FIXED |
| ~~HIGH~~ | ~~No project authorization~~ | ~~projects/views.py~~ | ~~Data exposure~~ | ✅ FIXED |
| ~~HIGH~~ | ~~No task authorization~~ | ~~tasks/views.py~~ | ~~Data exposure~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Optional webhook secret~~ | ~~integrations/views.py~~ | ~~Data injection~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Loose URL matching~~ | ~~integrations/views.py~~ | ~~Wrong project update~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Status order race condition~~ | ~~projects/views.py~~ | ~~Data corruption~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Task move race condition~~ | ~~tasks/views.py~~ | ~~Lost updates~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Subtask order race condition~~ | ~~tasks/views.py~~ | ~~Data corruption~~ | ✅ FIXED |
| ~~MEDIUM~~ | ~~Direct POST without validation~~ | ~~clients/views.py~~ | ~~Invalid data~~ | ✅ FIXED (earlier) |
| LOW | No rate limiting | accounts/views.py:58 | Abuse | Low |
| LOW | Broad exception handling | accounts/views.py:22 | Hidden errors | Low |

---

## Critical Issues (Fix Before Production)

### 1. GitHub Token Stored in Plain Text

**Location:** `apps/accounts/models.py:16`

```python
github_token = models.CharField(max_length=255, blank=True)
```

**Impact:**
- If database is compromised, all GitHub tokens are immediately exposed
- Attackers can access private repositories, modify code, delete repos
- Violates security best practices and compliance requirements (SOC2, GDPR)

**Business Risk:** HIGH - Could lead to source code theft, supply chain attacks

**Fix:**
```bash
pip install django-fernet-fields
```

```python
from fernet_fields import EncryptedCharField

github_token = EncryptedCharField(max_length=255, blank=True)
```

**Migration Required:** Yes - data migration to encrypt existing tokens

---

### 2. File Upload Without Validation

**Location:** `apps/tasks/views.py:206-219`

```python
def attachment_upload(request, pk):
    if request.FILES.get('file'):
        file = request.FILES['file']
        attachment = Attachment.objects.create(
            task=task,
            file=file,
            filename=file.name,  # No sanitization
            uploaded_by=request.user
        )
```

**Impact:**
- **Remote Code Execution:** Executable files (.exe, .sh, .py) can be uploaded
- **XSS via SVG:** SVG files can contain embedded JavaScript
- **Path Traversal:** Filenames with `../` can write outside upload directory
- **Disk Exhaustion:** No size limit allows multi-GB uploads
- **Malware Distribution:** Platform could host malicious files

**Business Risk:** CRITICAL - Server compromise, malware liability

**Fix:**
```python
import os
from django.utils.text import get_valid_filename

ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.txt'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    file = request.FILES.get('file')

    if not file:
        return HttpResponse('No file provided', status=400)

    # Validate extension
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return HttpResponse('File type not allowed', status=400)

    # Validate size
    if file.size > MAX_FILE_SIZE:
        return HttpResponse('File too large (max 10MB)', status=400)

    # Sanitize filename
    safe_filename = get_valid_filename(file.name)

    attachment = Attachment.objects.create(
        task=task,
        file=file,
        filename=safe_filename,
        uploaded_by=request.user
    )
```

---

### 3. No Authorization on Client CRUD

**Location:** `apps/clients/views.py:26-57`

**Impact:**
- Any authenticated user can create, read, update clients
- Sensitive client data (contact info, notes) exposed to all users
- One malicious employee could export entire client database
- Only delete is admin-protected

**Business Risk:** HIGH - Data privacy violation, potential GDPR fines

**Fix Options:**

**Option A: Admin-only write operations**
```python
@login_required
def client_create(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    # ... existing code
```

**Option B: Ownership model (preferred for multi-tenant)**
```python
# models.py
class Client(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    # ... existing fields

# views.py
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if client.created_by != request.user and not request.user.is_admin:
        return HttpResponseForbidden("Access denied")
```

---

### 4. JSON Parsing Without Exception Handling

**Location:** `apps/projects/views.py:106-111`

```python
def reorder_statuses(request, pk):
    order = json.loads(request.body).get('order', [])  # Crashes on invalid JSON
```

**Impact:**
- Malformed JSON causes 500 Internal Server Error
- Error page may expose stack traces and internal paths
- Easy denial of service by sending invalid payloads
- Makes debugging harder (generic 500 vs descriptive 400)

**Business Risk:** MEDIUM - Service disruption, information disclosure

**Fix:**
```python
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)

    try:
        data = json.loads(request.body)
        order = data.get('order', [])
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    if not isinstance(order, list):
        return HttpResponse('order must be a list', status=400)

    # ... existing code
```

---

## High Priority Issues (All Fixed)

### 5. ~~No Authorization on Project Operations~~ ✅ FIXED

**Location:** `apps/projects/views.py`

**Status:** Fixed - Implemented `ProjectMember` model with role-based access control (viewer/editor/manager).

**Implementation:**
- Created `ProjectMember` model with unique constraint on project+user
- Added `can_access_project()` helper function with role hierarchy
- Added authorization checks to all project views:
  - `project_list`: Filters to user's memberships (admins see all)
  - `project_board`: Requires viewer role
  - `project_edit`, `manage_statuses`, `project_settings`: Requires manager role
  - `project_create`, `project_delete`: Requires admin

---

### 6. ~~No Authorization on Task Operations~~ ✅ FIXED

**Location:** `apps/tasks/views.py`

**Status:** Fixed - All task views now require project membership with appropriate role.

**Implementation:**
- `task_detail`, `task_full_page`, `comment_create`: Requires viewer role
- `task_create`, `task_edit`, `task_delete`, `task_move`, subtask operations, attachment upload, property updates: Requires editor role

---

## Medium Priority Issues (All Fixed)

### 7. ~~Optional Webhook Secret~~ ✅ FIXED

**Location:** `apps/integrations/views.py`

**Status:** Fixed - Webhook secret is now required in production (non-DEBUG mode).

**Implementation:**
- In DEBUG mode, webhook secret check is skipped for development
- In production, returns 500 error if secret is not configured
- Valid signature required when secret is configured

---

### 8. ~~Loose Repository URL Matching~~ ✅ FIXED

**Location:** `apps/integrations/views.py`

**Status:** Fixed - Uses exact matching with URL normalization.

**Implementation:**
- Added `normalize_github_url()` function that:
  - Lowercases the URL
  - Removes protocol prefix (http/https)
  - Removes github.com prefix
  - Removes .git suffix
- Compares normalized URLs for exact match

---

### 9-11. ~~Race Conditions in Ordering~~ ✅ FIXED

**Locations:**
- `apps/projects/views.py:status_create`
- `apps/tasks/views.py:subtask_create`
- `apps/tasks/views.py:task_move`

**Status:** Fixed - All ordering operations now use atomic transactions with row locking.

**Implementation:**
- Added `@transaction.atomic` decorator
- Use `select_for_update()` on parent object
- Use `Max()` aggregation to safely get next order value

---

### 12. ~~Direct POST Without Form Validation~~ ✅ FIXED (earlier)

**Location:** `apps/clients/views.py`

**Status:** Fixed in earlier commit - Client edit now uses ClientForm for validation.

---

## Low Priority Issues

### 13. No Rate Limiting on Sensitive Endpoints

**Location:** `apps/accounts/views.py:58` (toggle_role)

**Fix:**
```bash
pip install django-ratelimit
```

```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key='user', rate='10/m', method='POST', block=True)
def toggle_role(request, pk):
    # ... existing code
```

---

### 14. Broad Exception Handling

**Location:** `apps/accounts/views.py:22-37`

**Fix:** Be specific about exceptions
```python
except ImportError:
    pass  # App not installed
except OperationalError:
    pass  # Database not ready
```

---

## Implementation Priority

### Phase 1: Pre-Production (Required)
1. Encrypt GitHub tokens
2. Add file upload validation
3. Fix JSON parsing exception handling

### Phase 2: Post-Launch Sprint 1
4. Implement authorization model (clients, projects, tasks)
5. Make webhook secret required
6. Fix URL matching

### Phase 3: Post-Launch Sprint 2
7. Fix race conditions
8. Add rate limiting
9. Replace direct POST with form validation

### Phase 4: Maintenance
10. Replace broad exceptions
11. Add audit logging
12. Consider async sync operations

---

## Testing Coverage

All issues have corresponding tests in the test suite:
- Security tests marked with `@pytest.mark.security`
- Race condition tests marked with `@pytest.mark.race`

Run security-focused tests:
```bash
pytest -m security -v
pytest -m race -v
```

---

## Questions?

Review the detailed audit files in `docs/security/`:
- `accounts-audit.md`
- `clients-audit.md`
- `projects-audit.md`
- `tasks-audit.md`
- `integrations-audit.md`
