# Security Audit: Integrations App

**Date:** 2025-12-31
**Auditor:** Claude Code
**Files Reviewed:** `apps/integrations/models.py`, `apps/integrations/views.py`

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| Medium | 2 | Open |
| Low | 1 | Open |

---

## Findings

### MEDIUM: Optional Webhook Secret Allows Bypass

**Location:** `apps/integrations/views.py:39-42`

```python
webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')

if webhook_secret and not verify_signature(request.body, signature, webhook_secret):
    return HttpResponse('Invalid signature', status=401)
```

**Risk:**
- If `GITHUB_WEBHOOK_SECRET` is not set, signature verification is skipped
- Anyone can send fake webhook events
- Attacker could inject malicious data into the system

**Recommendation:** Require secret in production:

```python
webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')

if not webhook_secret:
    if not settings.DEBUG:
        return HttpResponse('Webhook secret not configured', status=500)
elif not verify_signature(request.body, signature, webhook_secret):
    return HttpResponse('Invalid signature', status=401)
```

---

### MEDIUM: Loose Repository URL Matching

**Location:** `apps/integrations/views.py:53-59`

```python
try:
    project = Project.objects.get(
        github_repo_url__icontains=repo_url.replace('https://github.com/', ''),
        github_sync_enabled=True
    )
except Project.DoesNotExist:
    return HttpResponse('Project not found or sync disabled', status=404)
```

**Risk:**
- `icontains` matches partial strings
- `https://github.com/acme/app` would match a project with URL `https://github.com/acme/app-admin`
- Could cause webhooks to update wrong projects

**Recommendation:** Use exact matching with URL normalization:

```python
def normalize_github_url(url):
    """Normalize GitHub URL for comparison."""
    url = url.lower().rstrip('/')
    url = url.replace('https://github.com/', '')
    url = url.replace('http://github.com/', '')
    return url

normalized_repo = normalize_github_url(repo_url)
project = Project.objects.filter(
    github_sync_enabled=True
).extra(
    where=["LOWER(TRIM(TRAILING '/' FROM REPLACE(github_repo_url, 'https://github.com/', ''))) = %s"],
    params=[normalized_repo]
).first()
```

Or add a dedicated normalized field to the model.

---

### LOW: Async in Sync View

**Location:** `apps/integrations/views.py:82-88`

```python
@login_required
@require_POST
def github_sync(request, project_pk):
    ...
    import asyncio
    from .github import sync_issues_from_github

    asyncio.run(sync_issues_from_github(project, request.user.github_token))

    return JsonResponse({'status': 'synced'})
```

**Risk:**
- `asyncio.run()` in a sync view blocks the thread
- Could cause timeout issues for long sync operations
- Multiple concurrent syncs could exhaust worker threads

**Recommendation:** Use background task (Celery) or async view:

```python
# Option 1: Celery task
@shared_task
def sync_github_issues(project_id, token):
    project = Project.objects.get(pk=project_id)
    asyncio.run(sync_issues_from_github(project, token))

def github_sync(request, project_pk):
    sync_github_issues.delay(project_pk, request.user.github_token)
    return JsonResponse({'status': 'sync_started'})

# Option 2: Async view (Django 4.1+)
async def github_sync(request, project_pk):
    project = await Project.objects.aget(pk=project_pk)
    await sync_issues_from_github(project, request.user.github_token)
    return JsonResponse({'status': 'synced'})
```

---

## Positive Security Observations

1. **Good: HMAC Signature Verification**
   - Uses SHA-256 with timing-safe comparison (`hmac.compare_digest`)
   - Properly verifies GitHub webhook signatures

2. **Good: CSRF Exempt on Webhook Only**
   - Only `@csrf_exempt` on external webhook endpoint
   - `github_sync` still requires CSRF token

3. **Good: Login Required for Manual Sync**
   - `github_sync` requires authentication
   - Validates user has GitHub token configured

4. **Good: POST Required**
   - Both endpoints require POST method

5. **Good: Token Validation**
   - Checks if user has GitHub token before sync
   - Returns appropriate error if not configured

---

## Next Steps

1. [ ] Make webhook secret required in production
2. [ ] Implement exact URL matching for webhook routing
3. [ ] Move sync to background task or async view
4. [ ] Add rate limiting to prevent sync abuse
5. [ ] Consider adding webhook event logging for audit trail
