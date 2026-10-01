import re
from datetime import datetime

import httpx

from apps.projects.models import Project, Status
from apps.tasks.models import Task

from .models import GitHubCommit, GitHubPullRequest

GITHUB_TIMEOUT = httpx.Timeout(30.0)


def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Extract owner and repo from GitHub URL."""
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', url)
    if match:
        return match.group(1), match.group(2).rstrip('.git')
    return None


def get_github_headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def sync_issues_from_github(project: Project, token: str):
    """Sync issues from GitHub to tasks."""
    repo_info = parse_repo_url(project.github_repo_url)
    if not repo_info:
        return

    owner, repo = repo_info
    url = f'https://api.github.com/repos/{owner}/{repo}/issues'

    with httpx.Client(timeout=GITHUB_TIMEOUT) as client:
        response = client.get(url, headers=get_github_headers(token))
        if response.status_code != 200:
            return

        issues = response.json()
        backlog = project.statuses.first()

        for issue in issues:
            if 'pull_request' in issue:
                continue

            Task.objects.update_or_create(
                project=project,
                github_issue_id=issue['id'],
                defaults={
                    'github_issue_number': issue['number'],
                    'title': issue['title'],
                    'description': issue['body'] or '',
                    'status': backlog,
                }
            )


def create_github_issue(task: Task, token: str):
    """Create GitHub issue from task."""
    if not task.project.github_repo_url:
        return None

    repo_info = parse_repo_url(task.project.github_repo_url)
    if not repo_info:
        return None

    owner, repo = repo_info
    url = f'https://api.github.com/repos/{owner}/{repo}/issues'

    with httpx.Client(timeout=GITHUB_TIMEOUT) as client:
        response = client.post(
            url,
            headers=get_github_headers(token),
            json={
                'title': task.title,
                'body': task.description,
            }
        )
        if response.status_code == 201:
            data = response.json()
            task.github_issue_id = data['id']
            task.github_issue_number = data['number']
            task.save()
            return data
    return None


LEGACY_TASK_REF = re.compile(r'#TASK-(\d+)')


def find_referenced_task(message: str, project: Project) -> Task | None:
    """The task on ``project`` that a commit or PR text points at.

    ``CUST-12`` with this project's exact key, as a whole word, or the older
    ``#TASK-<pk>`` form, which links written before task numbers still use.
    """
    message = message or ''
    match = re.search(rf'\b{re.escape(project.key)}-(\d{{1,9}})\b', message) if project.key else None
    if match:
        task = Task.objects.filter(project=project, number=int(match.group(1))).first()
        if task:
            return task
    match = LEGACY_TASK_REF.search(message)
    if match:
        return Task.objects.filter(project=project, pk=int(match.group(1))).first()
    return None


def process_webhook_push(payload: dict, project: Project):
    """Process push webhook and link commits to tasks."""
    for commit in payload.get('commits', []):
        task = find_referenced_task(commit['message'], project)
        if task is None:
            continue
        GitHubCommit.objects.update_or_create(
            sha=commit['id'],
            defaults={
                'task': task,
                'message': commit['message'],
                'author': commit['author']['name'],
                'url': commit['url'],
                'created_at': datetime.fromisoformat(commit['timestamp'].replace('Z', '+00:00')),
            }
        )


def process_webhook_issue(payload: dict, project: Project):
    """Process issue webhook events."""
    action = payload.get('action')
    issue = payload.get('issue', {})

    if action == 'opened':
        backlog = project.statuses.first()
        Task.objects.update_or_create(
            project=project,
            github_issue_id=issue['id'],
            defaults={
                'github_issue_number': issue['number'],
                'title': issue['title'],
                'description': issue['body'] or '',
                'status': backlog,
            }
        )
    elif action == 'closed':
        try:
            task = Task.objects.get(project=project, github_issue_id=issue['id'])
            done_status = project.statuses.filter(category=Status.COMPLETED).first()
            if done_status:
                task.status = done_status
                task.save()
        except Task.DoesNotExist:
            pass
    elif action == 'edited':
        try:
            task = Task.objects.get(project=project, github_issue_id=issue['id'])
            task.title = issue['title']
            task.description = issue['body'] or ''
            task.save()
        except Task.DoesNotExist:
            pass


def process_webhook_pull_request(payload: dict, project: Project):
    """Process PR webhook and link to tasks."""
    pr = payload.get('pull_request', {})
    body = pr.get('body', '') or ''

    task = find_referenced_task(body, project) or find_referenced_task(pr.get('title', ''), project)
    if task is None:
        return

    status = 'merged' if pr.get('merged') else pr.get('state', 'open')
    GitHubPullRequest.objects.update_or_create(
        task=task,
        number=pr['number'],
        defaults={
            'title': pr['title'],
            'status': status,
            'url': pr['html_url'],
            'created_at': datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')),
            'updated_at': datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00')),
        }
    )
