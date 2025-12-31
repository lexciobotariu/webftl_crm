# Security Audit: Projects App

**Date:** 2025-12-31
**Auditor:** Claude Code
**Files Reviewed:** `apps/projects/models.py`, `apps/projects/views.py`

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 1 | Open |
| High | 1 | Open |
| Medium | 2 | Open |
| Low | 1 | Open |

---

## Findings

### CRITICAL: JSON Body Parsing Without Exception Handling

**Location:** `apps/projects/views.py:106-111`

```python
@login_required
@require_POST
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    order = json.loads(request.body).get('order', [])  # ⚠️ No try/except
    for i, status_id in enumerate(order):
        Status.objects.filter(pk=status_id, project=project).update(order=i)
    return HttpResponse(status=204)
```

**Risk:**
- `json.loads()` throws `JSONDecodeError` on malformed JSON
- Server returns 500 error exposing internal details
- Potential for denial of service via malformed requests

**Recommendation:**

```python
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    try:
        data = json.loads(request.body)
        order = data.get('order', [])
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)
    ...
```

---

### HIGH: No Authorization on Project CRUD

**Location:** `apps/projects/views.py:38-73`

```python
@login_required
def project_create(request):
    ...  # Any logged-in user can create

@login_required
def project_edit(request, pk):
    ...  # Any logged-in user can edit ANY project
```

**Risk:**
- Any user can view/edit/manage any project
- Sensitive project data exposed
- No project membership model

**Recommendation:** Implement project access control:

```python
class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(choices=[('viewer', 'Viewer'), ('editor', 'Editor')])
```

---

### MEDIUM: Race Condition in status_create

**Location:** `apps/projects/views.py:151-160`

```python
@login_required
@require_POST
def status_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        status = form.save(commit=False)
        status.project = project
        status.order = project.statuses.count()  # ⚠️ Race condition
        status.save()
```

**Risk:**
- Concurrent requests can get same `count()` value
- Results in duplicate order values
- Causes UI sorting inconsistencies

**Recommendation:** Use database sequence or F() expression:

```python
from django.db.models import Max

max_order = project.statuses.aggregate(Max('order'))['order__max'] or -1
status.order = max_order + 1
```

Or use `select_for_update()`:

```python
with transaction.atomic():
    project.statuses.select_for_update()
    status.order = project.statuses.count()
    status.save()
```

---

### MEDIUM: No Validation on Status Name

**Location:** `apps/projects/views.py:151-160`

```python
form = StatusForm(request.POST)
if form.is_valid():
    status = form.save(commit=False)
```

**Risk:**
- StatusForm may allow empty or whitespace-only names
- Duplicate status names in same project
- UI confusion with unnamed statuses

**Recommendation:** Add validation in StatusForm:

```python
class StatusForm(forms.ModelForm):
    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError("Status name cannot be empty")
        return name
```

---

### LOW: Delete Cascade Without Confirmation Detail

**Location:** `apps/projects/views.py:76-88`

```python
@login_required
@require_POST
def project_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    project = get_object_or_404(Project, pk=pk)
    project.delete()  # Cascades to statuses, tasks, etc.
```

**Risk:**
- Cascade delete removes all related data
- User may not understand full impact
- No soft-delete option for recovery

**Note:** Template does show confirmation dialog with warning text.

---

## Positive Security Observations

1. **Admin Delete Protection:** `project_delete` requires admin role
2. **Status-Task Protection:** Cannot delete status with tasks (`status_delete` checks `task_count`)
3. **CSRF Protection:** All POST views protected
4. **Login Required:** All views require authentication
5. **SQL Injection Safe:** Uses Django ORM

---

## Next Steps

1. [ ] Add try/except for JSON parsing in reorder_statuses
2. [ ] Implement project membership/authorization model
3. [ ] Fix race condition in status ordering
4. [ ] Add status name validation
5. [ ] Consider soft-delete for projects
