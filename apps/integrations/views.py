import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from .github import (
    process_webhook_push,
    process_webhook_issue,
    process_webhook_pull_request,
)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature or not secret:
        return False
    expected = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def github_webhook(request):
    """Handle GitHub webhook events."""
    signature = request.headers.get('X-Hub-Signature-256', '')
    event = request.headers.get('X-GitHub-Event', '')

    webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')

    if webhook_secret and not verify_signature(request.body, signature, webhook_secret):
        return HttpResponse('Invalid signature', status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    repo_url = payload.get('repository', {}).get('html_url', '')
    if not repo_url:
        return HttpResponse('No repository URL', status=400)

    try:
        project = Project.objects.get(
            github_repo_url__icontains=repo_url.replace('https://github.com/', ''),
            github_sync_enabled=True
        )
    except Project.DoesNotExist:
        return HttpResponse('Project not found or sync disabled', status=404)

    if event == 'push':
        process_webhook_push(payload, project)
    elif event == 'issues':
        process_webhook_issue(payload, project)
    elif event == 'pull_request':
        process_webhook_pull_request(payload, project)

    return HttpResponse('OK')


@login_required
@require_POST
def github_sync(request, project_pk):
    """Manually trigger GitHub sync for a project."""
    project = get_object_or_404(Project, pk=project_pk)

    if not project.github_repo_url:
        return JsonResponse({'error': 'No GitHub repo configured'}, status=400)

    if not request.user.github_token:
        return JsonResponse({'error': 'GitHub token not configured'}, status=400)

    import asyncio
    from .github import sync_issues_from_github

    asyncio.run(sync_issues_from_github(project, request.user.github_token))

    return JsonResponse({'status': 'synced'})
