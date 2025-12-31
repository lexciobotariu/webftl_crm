# Security Issues Summary - WebFTL CRM

**Last Updated:** 2026-01-01
**Total Issues:** 15 (~~4 Critical~~ **0 Critical**, 3 High, 6 Medium, 2 Low)

> **Status:** All 4 critical issues have been fixed. See commit `c4c5b90`.

---

## Quick Reference

| Priority | Issue | Location | Impact | Status |
|----------|-------|----------|--------|--------|
| ~~CRITICAL~~ | ~~GitHub token plain text~~ | ~~accounts/models.py:16~~ | ~~Data breach~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~File upload no validation~~ | ~~tasks/views.py:206~~ | ~~RCE, XSS~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~No client authorization~~ | ~~clients/views.py~~ | ~~Data exposure~~ | ✅ FIXED |
| ~~CRITICAL~~ | ~~JSON parsing crash~~ | ~~projects/views.py:106~~ | ~~DoS~~ | ✅ FIXED |
| HIGH | No project authorization | projects/views.py | Data exposure | Medium |
| HIGH | No task authorization | tasks/views.py | Data exposure | Medium |
| MEDIUM | Optional webhook secret | integrations/views.py:39 | Data injection | Low |
| MEDIUM | Loose URL matching | integrations/views.py:53 | Wrong project update | Low |
| MEDIUM | Status order race condition | projects/views.py:151 | Data corruption | Low |
| MEDIUM | Task move race condition | tasks/views.py:124 | Lost updates | Low |
| MEDIUM | Subtask order race condition | tasks/views.py:149 | Data corruption | Low |
| MEDIUM | Direct POST without validation | clients/views.py:60 | Invalid data | Low |
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

## High Priority Issues

### 5. No Authorization on Project Operations

**Location:** `apps/projects/views.py:38-73`

**Impact:**
- Any user can view, edit, delete any project
- Project settings (GitHub integration, labels) exposed
- No multi-tenant isolation

**Fix:** Implement ProjectMember model
```python
class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[
        ('viewer', 'Viewer'),
        ('editor', 'Editor'),
        ('admin', 'Admin'),
    ])

    class Meta:
        unique_together = ['project', 'user']

# Helper function
def can_access_project(user, project, required_role='viewer'):
    if user.is_admin:
        return True
    try:
        member = ProjectMember.objects.get(project=project, user=user)
        roles = {'viewer': 0, 'editor': 1, 'admin': 2}
        return roles.get(member.role, 0) >= roles.get(required_role, 0)
    except ProjectMember.DoesNotExist:
        return False
```

---

### 6. No Authorization on Task Operations

**Location:** `apps/tasks/views.py` (multiple views)

**Impact:**
- Any user can edit/delete any task across all projects
- Task assignments can be changed by anyone
- Comments and attachments accessible to all

**Fix:** Add project membership check to all task views
```python
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project, required_role='editor'):
        return HttpResponseForbidden("Access denied")
    # ... existing code
```

---

## Medium Priority Issues

### 7. Optional Webhook Secret

**Location:** `apps/integrations/views.py:39-42`

**Impact:** Without secret configured, anyone can send fake GitHub webhooks

**Fix:**
```python
webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')

if not webhook_secret:
    if not settings.DEBUG:
        return HttpResponse('Webhook secret not configured', status=500)
elif not verify_signature(request.body, signature, webhook_secret):
    return HttpResponse('Invalid signature', status=401)
```

---

### 8. Loose Repository URL Matching

**Location:** `apps/integrations/views.py:53-59`

**Impact:** `acme/app` matches `acme/app-admin` due to `icontains`

**Fix:** Use exact matching after normalization
```python
def normalize_github_url(url):
    return url.lower().rstrip('/').replace('https://github.com/', '').replace('http://github.com/', '')

normalized_repo = normalize_github_url(repo_url)
project = Project.objects.filter(
    github_sync_enabled=True
).annotate(
    normalized_url=Lower(Replace(F('github_repo_url'), Value('https://github.com/'), Value('')))
).filter(normalized_url=normalized_repo).first()
```

---

### 9-11. Race Conditions in Ordering

**Locations:**
- Status creation: `apps/projects/views.py:151`
- Subtask creation: `apps/tasks/views.py:149`
- Task move: `apps/tasks/views.py:124`

**Impact:** Concurrent requests get duplicate order values, causing UI sorting issues

**Fix:** Use `select_for_update()` or `Max()` aggregation
```python
from django.db.models import Max
from django.db import transaction

@transaction.atomic
def status_create(request, pk):
    project = Project.objects.select_for_update().get(pk=pk)
    max_order = project.statuses.aggregate(Max('order'))['order__max'] or -1
    status.order = max_order + 1
    status.save()
```

---

### 12. Direct POST Without Form Validation

**Location:** `apps/clients/views.py:60-76`

**Impact:** Bypasses email format validation, allows malformed data

**Fix:** Use ClientForm for all updates
```python
def client_edit_drawer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
```

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
