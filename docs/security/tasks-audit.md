# Security Audit: Tasks App

**Date:** 2025-12-31
**Auditor:** Claude Code
**Files Reviewed:** `apps/tasks/models.py`, `apps/tasks/views.py`

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 1 | Open |
| High | 1 | Open |
| Medium | 3 | Open |
| Low | 1 | Open |

---

## Findings

### CRITICAL: File Upload Without Validation

**Location:** `apps/tasks/views.py:206-219`

```python
@login_required
@require_POST
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.FILES.get('file'):
        file = request.FILES['file']
        attachment = Attachment.objects.create(
            task=task,
            file=file,
            filename=file.name,
            uploaded_by=request.user
        )
```

**Risk:**
- **No file type validation:** Accepts any file type including executables (.exe, .sh)
- **XSS via SVG:** Uploaded SVG files can contain JavaScript
- **Path traversal:** Filename could contain `../` sequences
- **No size limit:** Large files could cause disk exhaustion
- **No malware scanning**

**Recommendation:**

```python
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.txt'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    file = request.FILES.get('file')
    if file:
        # Check extension
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return HttpResponse('File type not allowed', status=400)
        # Check size
        if file.size > MAX_FILE_SIZE:
            return HttpResponse('File too large', status=400)
        # Sanitize filename
        safe_filename = get_valid_filename(file.name)
        ...
```

---

### HIGH: No Authorization Checks on Task Operations

**Location:** `apps/tasks/views.py` (multiple views)

```python
@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)  # Any user can edit any task
    ...

@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)  # Any user can delete any task
    ...
```

**Risk:**
- Any logged-in user can view/edit/delete any task
- No project membership verification
- Task assignment can be changed by anyone

**Recommendation:** Add authorization check:

```python
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not can_access_project(request.user, task.project):
        return HttpResponseForbidden("Access denied")
    ...
```

---

### MEDIUM: Race Condition in task_move

**Location:** `apps/tasks/views.py:124-133`

```python
@login_required
@require_POST
def task_move(request):
    task_id = request.POST.get('task_id')
    status_id = request.POST.get('status_id')
    task = get_object_or_404(Task, pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()
```

**Risk:**
- No locking during status update
- Concurrent moves can cause lost updates
- Task could end up in unexpected state

**Recommendation:** Use `select_for_update`:

```python
with transaction.atomic():
    task = Task.objects.select_for_update().get(pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()
```

---

### MEDIUM: XSS Risk in Comment Content

**Location:** `apps/tasks/views.py:190-203`

```python
@login_required
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    content = request.POST.get('content', '').strip()
    if content:
        activity = TaskActivity.objects.create(
            task=task,
            user=request.user,
            activity_type='comment',
            content=content  # Stored as-is
        )
```

**Risk:**
- Comment content stored without sanitization
- Relies entirely on template escaping
- If templates use `|safe` filter, XSS is possible

**Note:** Django auto-escapes by default. Verify templates don't use `|safe` on user content.

---

### MEDIUM: Subtask Order Race Condition

**Location:** `apps/tasks/views.py:149-163`

```python
@login_required
@require_POST
def subtask_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = SubtaskForm(request.POST)
    if form.is_valid():
        subtask = form.save(commit=False)
        subtask.task = task
        subtask.order = task.subtasks.count()  # ⚠️ Race condition
        subtask.save()
```

**Risk:**
- Concurrent subtask creation gets same `count()` value
- Results in duplicate order values
- Affects subtask display order

---

### LOW: No Input Length Validation on Comments

**Location:** `apps/tasks/views.py:190-203`

```python
content = request.POST.get('content', '').strip()
if content:
    activity = TaskActivity.objects.create(
        ...
        content=content  # No length limit
    )
```

**Risk:**
- Very large comments could cause performance issues
- Database storage concerns
- UI rendering problems

**Recommendation:** Add max length check:

```python
content = request.POST.get('content', '').strip()[:10000]  # Limit to 10k chars
```

---

## Positive Security Observations

1. **Task-Status Validation:** `task_move` verifies status belongs to task's project
2. **CSRF Protection:** All POST views protected
3. **Login Required:** All views require authentication
4. **SQL Injection Safe:** Uses Django ORM
5. **Empty Content Check:** Comment creation checks for non-empty content

---

## Next Steps

1. [ ] **CRITICAL:** Implement file upload validation (type, size, filename)
2. [ ] Implement project-level authorization for task operations
3. [ ] Add transaction locking for task moves
4. [ ] Verify templates don't use `|safe` on user content
5. [ ] Fix subtask ordering race condition
6. [ ] Add input length validation for comments
