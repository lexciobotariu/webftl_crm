# Security Audit: Clients App

**Date:** 2025-12-31
**Auditor:** Claude Code
**Files Reviewed:** `apps/clients/models.py`, `apps/clients/views.py`, `apps/clients/forms.py`

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 1 | Open |
| Medium | 2 | Open |
| Low | 1 | Open |

---

## Findings

### CRITICAL: No Authorization Checks on Client CRUD

**Location:** `apps/clients/views.py:26-57`

```python
@login_required
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            ...
```

**Risk:** Any logged-in user can:
- Create, view, edit, and delete any client
- Access sensitive client data (notes, contact info)
- Modify or delete other users' work

Only `client_delete` has admin-only protection.

**Recommendation:** Implement authorization model:

```python
# Option 1: Admin-only for write operations
@login_required
def client_create(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    ...

# Option 2: Client ownership model
class Client(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    ...
```

---

### MEDIUM: Direct POST Data Access Without Form Validation

**Location:** `apps/clients/views.py:60-76`

```python
@login_required
def client_edit_drawer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.name = request.POST.get('name', client.name)
        client.email = request.POST.get('email', '') or None  # ⚠️
        client.phone = request.POST.get('phone', '') or None  # ⚠️
        client.address = request.POST.get('address', '') or None  # ⚠️
        client.save()
```

**Risk:**
- Bypasses Django form validation
- No email format validation
- `or None` causes issues (EmailField doesn't accept None)
- Potential for malformed data injection

**Recommendation:** Use ClientForm for validation:

```python
def client_edit_drawer(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            ...
```

---

### MEDIUM: Nullable Fields Set to None on EmailField

**Location:** `apps/clients/views.py:66-68`

```python
client.email = request.POST.get('email', '') or None
client.phone = request.POST.get('phone', '') or None
client.address = request.POST.get('address', '') or None
```

**Risk:**
- EmailField with `blank=True` should use empty string `''`, not `None`
- Can cause database integrity issues depending on configuration
- Inconsistent data representation

**Recommendation:** Use empty strings for blank CharField/EmailField:

```python
client.email = request.POST.get('email', '').strip()
client.phone = request.POST.get('phone', '').strip()
client.address = request.POST.get('address', '').strip()
```

---

### LOW: No Input Length Validation in client_edit_notes

**Location:** `apps/clients/views.py:80-89`

```python
@login_required
def client_edit_notes(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.notes = request.POST.get('notes', '') or None
        client.save()
```

**Risk:**
- No maximum length check on notes field
- Large payloads could cause performance issues
- Potential for resource exhaustion

**Recommendation:** Add size limit:

```python
notes = request.POST.get('notes', '')[:10000]  # Limit to 10k chars
client.notes = notes.strip() if notes else ''
```

---

## Positive Security Observations

1. **Delete Protection:** `client_delete` properly checks `is_admin`
2. **CSRF Protection:** All forms use Django's CSRF protection
3. **Login Required:** All views protected with `@login_required`
4. **XSS Protection:** Django templates auto-escape output
5. **SQL Injection:** Uses Django ORM (parameterized queries)

---

## Next Steps

1. [ ] Implement authorization model for client access
2. [ ] Replace direct POST access with form validation
3. [ ] Fix nullable field handling (use empty strings)
4. [ ] Add input length validation for notes
5. [ ] Consider audit logging for client modifications
